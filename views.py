"""Готовые «экраны»: избранное и «Популярное» (картинка топ-5 с кэшем на 10 минут)."""

import asyncio
import os
import sqlite3
import time
from aiogram import types
from aiogram.types import InlineKeyboardButton
from aiogram.types import InlineKeyboardMarkup

from books import BOOKS_DB, find_book_by_url
from core import API_HASH, API_ID, BASE_DIR, CHANNEL, DB_PATH, TELETHON_READY, _telethon_lock, logger
from database import _mid_from_url, get_favorites, get_top_books, get_votes
from series import series_info
from keyboards import menu_button
from texts import LANG_FLAGS, tl, user_lang


def favorites_keyboard(favs, lang):
    """Строка на книгу: «📖 Название» (открыть) и «🗑» (удалить). Внизу — меню."""
    rows = []
    for favorite_id, sc, lg, bi, bn, bu in favs:
        rows.append([
            InlineKeyboardButton(text=f"{LANG_FLAGS.get(lg, '📖')} {bn[:34]}", callback_data=f"bm_{_mid_from_url(bu)}"),
            InlineKeyboardButton(text="🗑", callback_data=f"fav_del_id_{favorite_id}"),
        ])
    rows.append([menu_button(lang)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def send_favorites(message: types.Message, uid=None):
    """Показывает личную подборку пользователя, а не общий TOP библиотеки.
    uid нужен, когда вызываем из inline-кнопки: там message.from_user — это бот, а не пользователь."""
    uid = uid or message.from_user.id
    lang = user_lang(uid)
    favs = get_favorites(uid)
    if not favs:
        await message.answer(tl(lang, "fav_empty"), parse_mode="HTML",
                             reply_markup=InlineKeyboardMarkup(inline_keyboard=[[menu_button(lang)]]))
        return

    # Запись: id, subject_code, lang, book_idx, book_name, book_url
    entries = [{"title": row[4]} for row in favs]
    keyboard = favorites_keyboard(favs, lang)
    caption = tl(lang, "fav_caption", n=len(favs))
    try:
        png = await asyncio.to_thread(render_favorites_image, entries)
        await message.answer_photo(
            types.BufferedInputFile(png, filename="my_favorite_books.png"),
            caption=caption, parse_mode="HTML", reply_markup=keyboard,
        )
    except Exception as exc:
        logger.warning("Не удалось создать карточку избранного: %s", exc)
        await message.answer(caption, parse_mode="HTML", reply_markup=keyboard)

# ---------- Популярное ----------
def get_top_entries(limit=5):
    """Топ по открытиям. Тома одной серии объединяются; сохраняем ID настоящей обложки."""
    merged = {}
    for url, name, opens in get_top_books(500):
        loc = find_book_by_url(url)
        if not loc:
            continue
        sc, lg, bi = loc
        book = BOOKS_DB.get(sc, {}).get(lg, [])[bi]
        info = series_info(book.get("message_id"))
        key = info["id"] if info else url
        title = info["title"] if info and info["title"] else name
        cover_id = book.get("photo_message_id")
        # лайки серии хранятся на первом томе (там же ⭐ и 👍/👎 карточки серии)
        vote_url = info["members"][0]["book"]["url"] if info else url
        e = merged.setdefault(key, {
            "title": title, "opens": 0, "loc": loc,
            "cover_message_id": cover_id,
            "likes": get_votes(vote_url)[0],
        })
        e["opens"] += opens
        if not e.get("cover_message_id") and cover_id:
            e["cover_message_id"] = cover_id
    return sorted(merged.values(), key=lambda e: -e["opens"])[:limit]

def get_total_book_opens():
    """Общее число зарегистрированных открытий карточек книг за всё время."""
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute("SELECT COALESCE(SUM(opens), 0) FROM book_stats").fetchone()
        return int(row[0] or 0)
    finally:
        conn.close()

_cover_miss = set()      # посты без фото — повторно не запрашиваем

async def _cache_covers_impl(entries):
    """Скачивает настоящие фото обложек из канала в локальный кэш через Telethon.

    Требует уже авторизованную Telethon-сессию (TELETHON_SESSION_STRING либо
    TELETHON_SESSION_PATH). Если сессии нет, бот продолжит работу с аккуратной
    заглушкой вместо выдуманной обложки.
    """
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    cache_dir = os.path.join(BASE_DIR, "covers", "cache")
    os.makedirs(cache_dir, exist_ok=True)
    missing = [e for e in entries if e.get("cover_message_id")
               and e["cover_message_id"] not in _cover_miss and not any(
        os.path.isfile(os.path.join(cache_dir, f"{e['cover_message_id']}.{ext}"))
        for ext in ("jpg", "png", "webp")
    )]
    if not missing:
        return

    session_string = os.getenv("TELETHON_SESSION_STRING", "").strip()
    if session_string:
        session = StringSession(session_string)
    else:
        session = os.getenv("TELETHON_SESSION_PATH", os.path.join(BASE_DIR, "update_session"))
        if not os.path.isfile(str(session) + ".session"):
            logger.info("Обложки не загружены: авторизованная Telethon-сессия не найдена.")
            return

    client = TelegramClient(session, API_ID, API_HASH, lang_code="ru", system_lang_code="ru-RU")
    try:
        await client.connect()
        if not await client.is_user_authorized():
            logger.warning("Telethon-сессия не авторизована: обложки будут показаны при следующем запуске.")
            return
        for entry in missing:
            message_id = int(entry["cover_message_id"])
            try:
                msg = await client.get_messages(CHANNEL, ids=message_id)
                if not msg or not msg.media:
                    _cover_miss.add(entry["cover_message_id"])
                    continue
                target = os.path.join(cache_dir, f"{message_id}.jpg")
                saved = await client.download_media(msg, file=target)
                if saved and os.path.isfile(saved):
                    logger.info("Обложка книги сохранена: %s", message_id)
            except Exception as cover_error:
                logger.warning("Не удалось получить обложку %s: %s", message_id, cover_error)
    finally:
        await client.disconnect()

async def cache_popular_book_covers(entries):
    """Обёртка: не мешает /update_books (общая сессия) и не вешает /popular дольше 45 секунд."""
    if not TELETHON_READY or _telethon_lock.locked():
        return                                  # нет ключей Telethon или сейчас идёт обновление каталога — обложки в следующий раз
    async with _telethon_lock:
        await asyncio.wait_for(_cache_covers_impl(entries), timeout=45)

def render_top_image(entries, total_opens=None):
    """Premium PNG через Pillow; никаких ИИ API или внешней генерации."""
    from stats_render.premium import render_top_image as _render
    return _render(entries, get_total_book_opens() if total_opens is None else total_opens)

def render_favorites_image(entries):
    """Личная карточка избранного — только названия, без обложек книг."""
    from stats_render.premium import render_favorites_image as _render
    return _render(entries)

_POPULAR_TTL = 600                       # секунд: столько держим готовый топ-5

_popular_cache = {"ts": 0.0, "file_id": None, "keyboard": None}

_popular_lock = asyncio.Lock()           # одновременные /popular не рисуют картинку по нескольку раз

_POPULAR_CAPTION = "📚 Adasan Library · TOP-5\n📊 Статистика за всё время"

async def _send_popular_from_cache(message: types.Message) -> bool:
    """Шлёт готовый топ-5 по file_id (без запросов к базе, без обложек и без рендера)."""
    c = _popular_cache
    if not c["file_id"] or time.time() - c["ts"] >= _POPULAR_TTL:
        return False
    try:
        await message.answer_photo(c["file_id"], caption=_POPULAR_CAPTION)
        await message.answer("👇 Таңдаңыз / Выберите:", reply_markup=c["keyboard"])
        return True
    except Exception as e:
        logger.warning("Кэш топ-5 не сработал, строим заново: %s", e)
        c["file_id"] = None
        return False

async def send_popular(message: types.Message):
    if await _send_popular_from_cache(message):
        return
    async with _popular_lock:
        if await _send_popular_from_cache(message):      # пока ждали, кто-то уже обновил кэш
            return
        entries = get_top_entries(5)
        if not entries:
            await message.answer(
                "🔥 Әзірге танымал кітаптар жоқ / Пока нет популярных книг.\n\n"
                "Кітаптарды ашқан сайын тізім толады / Список наполнится, когда книги начнут открывать."
            )
            return

        photo_file_id = None
        try:
            # First run may fetch real cover photos from the existing Telegram channel.
            try:
                await cache_popular_book_covers(entries)
            except Exception as cover_error:
                logger.warning("Не удалось обновить кэш обложек: %s", cover_error)

            png = await asyncio.to_thread(render_top_image, entries, get_total_book_opens())
            sent = await message.answer_photo(
                types.BufferedInputFile(png, filename="adasan_library_top5.png"),
                caption=_POPULAR_CAPTION,
            )
            if sent.photo:
                photo_file_id = sent.photo[-1].file_id
        except Exception as e:
            logger.exception("Не удалось создать изображение рейтинга: %s", e)
            await message.answer("Не удалось сформировать изображение рейтинга. Попробуйте ещё раз позже.")

        buttons = []
        for e in entries:
            sc, lg, bi = e["loc"]
            buttons.append([InlineKeyboardButton(
                text=f"🔥 {e['opens']} · {e['title'][:30]}", callback_data=f"bk_{sc}_{lg}_{bi}")])
        buttons.append([menu_button()])
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await message.answer("👇 Таңдаңыз / Выберите:", reply_markup=keyboard)

        if photo_file_id:                                  # кэшируем только удачный результат
            _popular_cache.update(ts=time.time(), file_id=photo_file_id, keyboard=keyboard)
