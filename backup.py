"""Резервные копии базы в Telegram и восстановление."""

import asyncio
import csv
import hashlib
import io
import os
import shutil
import sqlite3
import tempfile
import zipfile
from aiogram import types
from datetime import datetime

from core import ADMIN_ID, BASE_DIR, DB_PATH, bot, logger
from database import get_top_books, init_db, reload_helpers, reset_user_caches
from top5 import TOP5_PATH


BACKUP_INTERVAL_H = float(os.getenv("BACKUP_INTERVAL_HOURS", "3"))

_backup_state = {"hash": None, "blocked": False}

_backup_lock = asyncio.Lock()

def _db_counts():
    conn = sqlite3.connect(DB_PATH)
    try:
        def one(sql):
            try:
                return conn.execute(sql).fetchone()[0] or 0
            except sqlite3.Error:
                return 0
        return {
            "users": one("SELECT COUNT(*) FROM users"),
            "favorites": one("SELECT COUNT(*) FROM favorites"),
            "opens": one("SELECT COALESCE(SUM(opens),0) FROM book_stats"),
            "votes": one("SELECT COUNT(*) FROM book_ratings"),
        }
    finally:
        conn.close()

def _build_backup():
    """(zip_bytes, counts, digest). Выполняется в потоке. Снимок SQLite — через backup API, он целостный."""
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        src = sqlite3.connect(DB_PATH)
        dst = sqlite3.connect(tmp)
        src.backup(dst)
        src.close()
        counts = _db_counts()
        buf, sha = io.BytesIO(), hashlib.sha256()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            with open(tmp, "rb") as f:
                z.writestr("adasan.db", f.read())
            tables = [r[0] for r in dst.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
            for t in tables:                                   # читаемые таблицы для вас
                cur = dst.execute(f'SELECT * FROM "{t}"')
                out = io.StringIO()
                w = csv.writer(out)
                w.writerow([d[0] for d in cur.description])
                for row in cur:
                    w.writerow(row)
                text = out.getvalue()
                sha.update(t.encode() + text.encode("utf-8"))
                z.writestr(f"readable/{t}.csv", "﻿" + text)       # BOM — чтобы Excel открыл кириллицу
            dst.close()
            top = ""
            try:
                top = "\n".join(f"{i}. {n} — {o}" for i, (_u, n, o) in enumerate(get_top_books(10), 1))
            except Exception:
                pass
            z.writestr("readable/summary.txt",
                       f"Резервная копия {datetime.now():%Y-%m-%d %H:%M}\n"
                       f"Пользователей: {counts['users']}\nИзбранных книг: {counts['favorites']}\n"
                       f"Открытий книг: {counts['opens']}\nОценок: {counts['votes']}\n\nТоп-10 книг:\n{top}\n")
            for name in ("top5.json", "books_db.json"):
                path = os.path.join(BASE_DIR, name)
                if os.path.isfile(path) and os.path.getsize(path) < 30_000_000:
                    with open(path, "rb") as f:
                        data = f.read()
                    sha.update(name.encode() + data)
                    z.writestr(name, data)
        return buf.getvalue(), counts, sha.hexdigest()
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass

async def make_backup(force=False):
    """Шлёт владельцу копию и закрепляет её. True — отправлено. Пустую базу не бэкапим (не затираем хорошую копию)."""
    if _backup_state["blocked"] and not force:
        return False
    async with _backup_lock:
        data, counts, digest = await asyncio.to_thread(_build_backup)
        if counts["users"] == 0 and counts["favorites"] == 0:
            return False
        if not force and digest == _backup_state["hash"]:
            return False                                       # ничего не изменилось
        name = f"adasan_backup_{datetime.now():%Y%m%d_%H%M}.zip"
        msg = await bot.send_document(
            ADMIN_ID, types.BufferedInputFile(data, filename=name), disable_notification=True,
            caption=(f"💾 Резервная копия\n👥 {counts['users']} польз. · ⭐ {counts['favorites']} избр. · "
                     f"📖 {counts['opens']} открытий · 👍 {counts['votes']} оценок\n"
                     "Внутри: база и читаемые таблицы (readable/*.csv). После деплоя бот восстановится сам."))
        try:
            await bot.pin_chat_message(ADMIN_ID, msg.message_id, disable_notification=True)
        except Exception as e:
            logger.warning(f"Не удалось закрепить копию: {e}")
        _backup_state["hash"] = digest
        _backup_state["blocked"] = False
        return True

def _restore_from_zip(data):
    """Проверяет zip и подменяет базу и top5.json. Возвращает счётчики. Исключение — если архив негодный."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = set(z.namelist())
        if "adasan.db" not in names:
            raise ValueError("в архиве нет adasan.db")
        db_bytes = z.read("adasan.db")
        top5 = z.read("top5.json") if "top5.json" in names else None
    if not db_bytes:
        raise ValueError("файл adasan.db в архиве пустой")
    fd, tmp = tempfile.mkstemp(suffix=".db", dir=os.path.dirname(DB_PATH) or None)
    os.close(fd)
    try:
        with open(tmp, "wb") as f:
            f.write(db_bytes)
        conn = sqlite3.connect(tmp)
        ok = conn.execute("PRAGMA integrity_check").fetchone()[0]
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        if ok != "ok" or not {"users", "favorites", "book_stats"} <= tables:
            raise ValueError("база в архиве повреждена или не от этого бота")
        if os.path.isfile(DB_PATH):
            shutil.copyfile(DB_PATH, DB_PATH + ".before_restore")
        # SQLite may have left sidecar files from the old database. Remove them
        # only after the replacement snapshot has passed integrity validation.
        for suffix in ("-wal", "-shm"):
            sidecar = DB_PATH + suffix
            if os.path.isfile(sidecar):
                os.remove(sidecar)
        os.replace(tmp, DB_PATH)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    init_db()                                                  # досоздаёт таблицы, если схема новее
    if top5:
        t = TOP5_PATH + ".tmp"
        with open(t, "wb") as f:
            f.write(top5)
        os.replace(t, TOP5_PATH)
    reload_helpers()
    reset_user_caches()                                        # язык, бан, подписка — из восстановленной базы
    return _db_counts()

async def auto_restore_if_fresh():
    """Запуск с пустой базой (диск обнулился): тянем закреплённую копию из чата с владельцем."""
    try:
        if _db_counts()["users"] > 0:
            return
        chat = await bot.get_chat(ADMIN_ID)
        doc = chat.pinned_message.document if getattr(chat, "pinned_message", None) else None
        if not doc or not (doc.file_name or "").startswith("adasan_backup_"):
            logger.info("База пустая, закреплённой копии нет — это первый запуск.")
            return
        buf = io.BytesIO()
        await bot.download(doc, destination=buf)
        c = await asyncio.to_thread(_restore_from_zip, buf.getvalue())
        logger.info(f"♻️ База восстановлена из копии: {c}")
        await bot.send_message(ADMIN_ID, f"♻️ После перезапуска база восстановлена из копии: "
                                         f"{c['users']} польз., {c['favorites']} избранных, {c['opens']} открытий.")
    except Exception as e:
        _backup_state["blocked"] = True                        # не затираем старую копию пустой базой
        logger.error(f"Автовосстановление не удалось: {e}")
        try:
            await bot.send_message(ADMIN_ID, f"⚠️ Не удалось восстановить базу: {e}\n"
                                             "Автокопии остановлены, чтобы не затереть старую. "
                                             "Перешлите zip боту с подписью /restore.")
        except Exception:
            pass

async def backup_loop():
    await asyncio.sleep(300)
    while True:
        try:
            await make_backup()
        except Exception as e:
            logger.warning(f"Автокопия не удалась: {e}")
        await asyncio.sleep(max(0.25, BACKUP_INTERVAL_H) * 3600)

async def _restore_command_impl(message: types.Message, doc):
    if not doc:
        await message.answer("Перешлите zip-копию боту с подписью /restore или ответьте на неё командой /restore."); return
    try:
        buf = io.BytesIO()
        await bot.download(doc, destination=buf)
        if not zipfile.is_zipfile(io.BytesIO(buf.getvalue())):
            raise ValueError("файл не является ZIP-архивом")
        c = await asyncio.to_thread(_restore_from_zip, buf.getvalue())
    except Exception as e:
        await message.answer(f"❌ Не восстановлено: {e}"); return
    _backup_state["blocked"] = False
    await message.answer(f"♻️ Готово: {c['users']} польз., {c['favorites']} избранных, {c['opens']} открытий.\n"
                         "Старая база сохранена как adasan.db.before_restore.")
