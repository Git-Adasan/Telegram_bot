"""Обработчики администратора: рассылка, статистика, баны, помощники, /update_books, /sort_other."""

import asyncio
import logging
import os
import re
import shutil
import sqlite3
from aiogram import F
from aiogram import types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton
from aiogram.types import InlineKeyboardMarkup

from admin_tools import _show_helpers, admin_keyboard, apply_helper_commands, clear_helper_commands, send_banlist, send_broadcast_one
from books import BOOKS_DB, _load_sort_overrides, _save_sort_overrides, replace_books_db
from catalog import _refresh_catalog_names, _sort_card, _sort_move, _sort_send_files, _sort_skipped, apply_sort_overrides, build_dynamic_catalog
from core import ADMIN_ID, API_HASH, API_ID, BASE_DIR, CHANNEL, DB_PATH, _telethon_lock, bot, dp
from database import _ENV_HELPERS, add_helper, ban_user, compact_stats, count_bot_blocked, get_broadcast_user_ids, get_detailed_stats, get_extra_stats, get_lang, get_monthly_activity, get_users_list, helper_ids, is_owner, is_staff, remove_helper, resolve_user, top_misses, unban_user, vacuum_db
from keyboards import main_menu_keyboard
from search_engine import _is_english_filename
from series import inherit_series_covers, normalize_existing_catalog, propagate_series_covers
from subjects import SUBJECTS, find_subject
from wishes import notify_wishes


# =========================
# КОМАНДА — рассылка (только админ)
# =========================
@dp.message(Command("broadcast"))
async def broadcast_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Рұқсат жоқ!")
        return
    text = message.text.replace("/broadcast", "", 1).strip()
    if not text:
        await message.answer(
            "📢 Использование:\n/broadcast Ваш текст сообщения\n\nПример:\n/broadcast 📚 Жаңа кітаптар қосылды!"
        )
        return
    user_ids, skipped = get_broadcast_user_ids()      # без тех, кто уже заблокировал бота
    sent = blocked = failed = 0
    note = f", пропущено {skipped} — заблокировали бота" if skipped else ""
    await message.answer(f"⏳ Рассылка начата... ({len(user_ids)} пользователей{note})")
    for uid in user_ids:
        status = await send_broadcast_one(uid, f"📢 Adasan Bot\n\n{text}")
        if status == "sent":
            sent += 1
        elif status == "blocked":
            blocked += 1
        else:
            failed += 1
        await asyncio.sleep(0.05)  # Anti-flood
    lines = [f"✅ Рассылка завершена!\n\n✔️ Отправлено: {sent}"]
    if blocked:
        lines.append(f"🚫 Заблокировали бота (больше не получат): {blocked}")
    if failed:
        lines.append(f"❌ Не доставлено (ошибка): {failed}")
    if skipped:
        lines.append(f"⏭ Пропущено заранее (блок бота): {skipped}")
    await message.answer("\n".join(lines))

# =========================
# КОМАНДА — детальная статистика (только админ)
# =========================
@dp.message(Command("stats"))
async def stats_command(message: types.Message):
    if not is_staff(message.from_user.id):
        await message.answer("❌ Рұқсат жоқ!")
        return
    total_users, total_searches, top_subjects, daily, new_users, top_books = get_detailed_stats()
    emoji_map = {"gistologiya":"🔬","anatomiya":"🦴","biohimiya":"🧪","fiziologiya":"⚡",
                 "ishki":"🏥","patfiz":"🔥","farmakologiya":"💊","mikrobiologiya":"🦠",
                 "genetika":"🧬","tarih":"📜","hirurgiya":"✂️","biofizika":"⚗️"}
    text = (
        "📊 ДЕТАЛЬНАЯ СТАТИСТИКА\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Барлық пайдаланушылар: {total_users}\n"
        f"🆕 Жаңа (7 күн): {new_users}\n"
        f"🚫 Ботты бұғаттағандар: {count_bot_blocked()}\n"
        f"🔍 Барлық іздеулер: {total_searches}\n\n"
        "🏆 Танымал пәндер:\n"
    )
    for i, (subj, cnt) in enumerate(top_subjects, 1):
        em = emoji_map.get(subj, "📚")
        text += f"  {i}. {em} {subj}: {cnt}\n"
    text += "\n📅 Белсенділік (7 күн):\n"
    for day, cnt in daily:
        bar = "█" * min(cnt, 20)
        text += f"  {day}: {bar} {cnt}\n"
    monthly, joined = get_monthly_activity()
    if monthly:
        text += "\n🗓 Барлық уақыт, айлар бойынша (іздеу | белсенді | жаңа):\n"
        for m, n_search, n_active in monthly[-24:]:
            text += f"  {m}: 🔍{n_search} | 👤{n_active} | 🆕{joined.get(m, 0)}\n"
    if top_books:
        text += "\n📖 Танымал кітаптар:\n"
        for i, (bname, cnt) in enumerate(top_books, 1):
            text += f"  {i}. {bname[:30]}: {cnt} рет\n"
    top_opens, top_rated, subs = get_extra_stats()
    if top_opens:
        text += "\n🔥 Ашылу саны (есептегіш):\n"
        for i, (bname, cnt) in enumerate(top_opens, 1):
            text += f"  {i}. {bname[:30]}: {cnt}\n"
    if top_rated:
        text += "\n👍👎 Рейтинг:\n"
        for i, (bname, up, down) in enumerate(top_rated, 1):
            text += f"  {i}. {bname[:30]}: 👍{up} 👎{down}\n"
    if subs:
        text += (
            "\n📤 Студент материалдары:\n"
            f"  ⏳ күтуде: {subs.get('pending', 0)} | ✅ қабылданды: {subs.get('approved', 0)} | ❌ қайтарылды: {subs.get('rejected', 0)}\n"
        )
    await message.answer(text)

# =========================
# КОМАНДА — что ищут и не находят (админ и помощники)
# =========================
@dp.message(Command("missing"))
async def missing_command(message: types.Message):
    if not is_staff(message.from_user.id):
        await message.answer("❌ Рұқсат жоқ!")
        return
    rows = top_misses(20)
    if not rows:
        await message.answer("✅ Ненайденных запросов пока нет.")
        return
    lines = ["🔎 Чего ищут и не находят\n(человек · раз · 🔔 ждут уведомления)\n"]
    for i, (_mid, sample, n, people, wishers) in enumerate(rows, 1):
        bell = f" · 🔔{wishers}" if wishers else ""
        lines.append(f"{i}. «{sample[:60]}» — 👤{people} · {n}×{bell}")
    lines.append("\nДобавили книги в канал? Запустите /update_books — ждущие получат уведомление.")
    await message.answer("\n".join(lines))

# =========================
# КОМАНДА — сжать старую статистику (только владелец)
# =========================
@dp.message(Command("compact"))
async def compact_command(message: types.Message):
    """Свернуть старые поиски в архив и вернуть место на диске. Счётчики в /stats не меняются."""
    if not is_owner(message.from_user.id):
        await message.answer("❌ Рұқсат жоқ!")
        return
    size_before = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
    moved = await asyncio.to_thread(compact_stats)
    await asyncio.to_thread(vacuum_db)
    size_after = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
    await message.answer(
        f"🧹 Статистика сжата\n\n"
        f"Свёрнуто строк: {moved}\n"
        f"Файл базы: {size_before / 1048576:.1f} МБ → {size_after / 1048576:.1f} МБ\n\n"
        "Счётчики в /stats и /users остались прежними."
    )

# =========================
# КОМАНДА — бан пользователя (только админ)
# =========================
@dp.message(Command("users"))
async def users_command(message: types.Message):
    """Админ: список всех пользователей бота (кто пользуется)."""
    if not is_staff(message.from_user.id):
        await message.answer("❌ Рұқсат жоқ!")
        return
    rows = get_users_list()
    if not rows:
        await message.answer("Пока нет пользователей.")
        return
    from html import escape
    header = f"👥 <b>Пайдаланушылар: {len(rows)}</b>\n\n"
    lines = []
    for i, (uid, uname, fname, lang, joined, n) in enumerate(rows, 1):
        name = escape((fname or "—").strip() or "—")
        if uname:
            link = f'<a href="https://t.me/{escape(uname)}">@{escape(uname)}</a>'
        else:
            link = f'<a href="tg://user?id={uid}">профиль</a>'
        lines.append(f"{i}. {name} — {link}")
    chunk = header
    for line in lines:
        if len(chunk) + len(line) + 1 > 3800:   # лимит Telegram 4096
            await message.answer(chunk, parse_mode="HTML", disable_web_page_preview=True)
            chunk = ""
        chunk += line + "\n"
    if chunk.strip():
        await message.answer(chunk, parse_mode="HTML", disable_web_page_preview=True)

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    """Админ/помощник: кнопки внизу экрана — не нужно печатать команды."""
    if not is_staff(message.from_user.id):
        await message.answer("❌ Рұқсат жоқ!")
        return
    await message.answer("🛠 Админ-панель", reply_markup=admin_keyboard(message.from_user.id))

@dp.message(F.text == "👥 Пользователи", F.from_user.id.func(is_staff))
async def admin_users_button(message: types.Message):
    await users_command(message)

@dp.message(F.text == "📊 Статистика", F.from_user.id.func(is_staff))
async def admin_stats_button(message: types.Message):
    await stats_command(message)

@dp.message(F.text == "🚫 Баны", F.from_user.id.func(is_staff))
async def admin_bans_button(message: types.Message):
    await message.answer("🚫 Управление банами", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список банов / разбан", callback_data="admin_bans_list")],
        [InlineKeyboardButton(text="🚫 Забанить по ID", callback_data="admin_ban_help")],
        [InlineKeyboardButton(text="🔓 Разбанить по ID", callback_data="admin_unban_help")],
        [InlineKeyboardButton(text="✖ Закрыть", callback_data="admin_bans_close")],
    ]))

@dp.callback_query(lambda c: c.data in {"admin_bans_list", "admin_ban_help", "admin_unban_help", "admin_bans_close"})
async def admin_bans_callback(callback: types.CallbackQuery):
    if not is_staff(callback.from_user.id):
        await callback.answer("❌ Рұқсат жоқ!", show_alert=True)
        return
    if callback.data == "admin_bans_list":
        await send_banlist(callback.message)
    elif callback.data == "admin_bans_close":
        await callback.message.edit_reply_markup(reply_markup=None)
    elif callback.data == "admin_ban_help":
        await callback.message.answer("Отправьте: /ban ID причина\nПример: /ban 123456789 Спам")
    else:
        await callback.message.answer("Отправьте: /unban ID")
    await callback.answer()

@dp.message(Command("admins"))
async def admins_command(message: types.Message):
    if not is_owner(message.from_user.id):
        await message.answer("❌ Рұқсат жоқ!")
        return
    await _show_helpers(message)

@dp.message(Command("addadmin"))
async def addadmin_command(message: types.Message):
    if not is_owner(message.from_user.id):
        await message.answer("❌ Только владелец может назначать помощников.")
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Использование: /addadmin @username или /addadmin 123456789")
        return
    uid, name = resolve_user(parts[1])
    if not uid:
        await message.answer("❌ Не найден. Человек должен хотя бы раз запустить бота, "
                             "либо укажите его числовой ID.")
        return
    if is_owner(uid):
        await message.answer("Вы и так владелец 👑")
        return
    if uid in helper_ids():
        await message.answer(f"{name} уже помощник.")
        return
    add_helper(uid, message.from_user.id)
    unban_user(uid)   # помощник не должен быть в бане
    await apply_helper_commands(uid)
    try:
        await bot.send_message(uid, "🛡 Вас назначили помощником админа.\nОтправьте /admin — появятся кнопки.")
    except Exception:
        pass
    await message.answer(f"✅ {name} теперь помощник админа.")

@dp.message(Command("removeadmin"))
async def removeadmin_command(message: types.Message):
    if not is_owner(message.from_user.id):
        await message.answer("❌ Только владелец может снимать помощников.")
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Использование: /removeadmin @username или /removeadmin 123456789")
        return
    uid, name = resolve_user(parts[1])
    if not uid or uid not in helper_ids():
        await message.answer("❌ Такого помощника нет. Список: /admins")
        return
    remove_helper(uid)
    await clear_helper_commands(uid)
    try:
        await bot.send_message(uid, "Вы больше не помощник админа.",
                               reply_markup=main_menu_keyboard(get_lang(uid)))
    except Exception:
        pass
    note = ""
    if uid in _ENV_HELPERS:
        note = "\n⚠️ Он указан в EXTRA_ADMIN_IDS на хостинге — удалите его и оттуда."
    await message.answer(f"✅ {name} больше не помощник.{note}")

@dp.message(Command("ban"))
async def ban_command(message: types.Message):
    if not is_staff(message.from_user.id):
        await message.answer("❌ Рұқсат жоқ!")
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer(
            "Использование:\n"
            "/ban @username [причина]\n"
            "/ban 123456789 [причина]\n\n"
            "Пример:\n/ban @vasya Спам"
        )
        return
    target_input = parts[1]
    reason = parts[2] if len(parts) > 2 else "Без причины"
    target_id = None
    target_name = target_input
    if target_input.startswith("@"):
        username = target_input.lstrip("@")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT user_id, first_name FROM users WHERE username=?", (username,))
        row = c.fetchone()
        conn.close()
        if row:
            target_id = row[0]
            target_name = f"{row[1]} ({target_input})"
        else:
            await message.answer(
                f"❌ Пайдаланушы табылмады: {target_input}\n\n"
                f"⚠️ Пайдаланушы ботты кем дегенде бір рет қолданған болуы керек."
            )
            return
    else:
        try:
            target_id = int(target_input)
        except ValueError:
            await message.answer("❌ @username немесе ID (сан) жазыңыз!")
            return
    if is_owner(target_id):
        await message.answer("❌ Владельца заблокировать нельзя.")
        return
    if is_staff(target_id) and not is_owner(message.from_user.id):
        await message.answer("❌ Помощника админа может заблокировать только владелец.")
        return
    ban_user(target_id, reason)
    try:
        await bot.send_message(
            target_id,
            f"🚫 Сіз бұғатталдыңыз / Вы заблокированы администратором.\n\n"
            f"📝 Себеп / Причина: {reason}\n\n"
            f"Егер қате болса / Если это ошибка:\n"
            f"👉 @Tg_Adasan"
        )
    except Exception:
        pass
    await message.answer(
        f"✅ Пайдаланушы бұғатталды!\n\n"
        f"👤 Кім: {target_name}\n"
        f"🆔 ID: {target_id}\n"
        f"📝 Себеп: {reason}"
    )

@dp.message(Command("unban"))
async def unban_command(message: types.Message):
    if not is_staff(message.from_user.id):
        await message.answer("❌ Рұқсат жоқ!")
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Использование: /unban <user_id>")
        return
    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("❌ user_id должен быть числом!")
        return
    unban_user(target_id)
    try:
        await bot.send_message(target_id, "✅ Сіздің бұғатыңыз алынды / Ваша блокировка снята.")
    except Exception:
        pass
    await message.answer(f"✅ Пайдаланушы бұғаттан шығарылды! ID: {target_id}")

@dp.message(Command("banlist"))
async def banlist_command(message: types.Message):
    if not is_staff(message.from_user.id):
        await message.answer("❌ Рұқсат жоқ!")
        return
    await send_banlist(message)

@dp.callback_query(lambda c: c.data and c.data.startswith("unban_"))
async def unban_callback(callback: types.CallbackQuery):
    if not is_staff(callback.from_user.id):
        await callback.answer("❌ Рұқсат жоқ!", show_alert=True)
        return
    target_id = int(callback.data.replace("unban_", ""))
    unban_user(target_id)
    try:
        await bot.send_message(target_id, "✅ Сіздің бұғатыңыз алынды / Ваша блокировка снята.")
    except Exception:
        pass
    await callback.answer(f"✅ {target_id} бұғаттан шығарылды!", show_alert=True)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await send_banlist(callback.message)

@dp.callback_query(lambda c: c.data == "noop")
async def noop_callback(callback: types.CallbackQuery):
    await callback.answer()

# =========================
# КОМАНДА — обновить базу книг (только админ)
# =========================
@dp.message(Command("update_books"))
async def update_books_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Рұқсат жоқ!")
        return

    if _telethon_lock.locked():
        await message.answer("⏳ Обновление уже идёт, подождите.")
        return
    await message.answer("⏳ Канал оқылуда... 2-5 минут күтіңіз")

    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto
        import json as _json2
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _telethon_client(session):
            """Подключается БЕЗ интерактивного входа.

            `async with TelegramClient(...)` вызывает start(), а он при неавторизованной
            сессии сам просит телефон/код через input() — на сервере это зависает и
            Telegram шлёт «лишние» коды. Здесь только connect() + проверка авторизации.
            """
            client = TelegramClient(
                session, API_ID, API_HASH,
                lang_code="ru", system_lang_code="ru-RU",
            )
            await client.connect()
            try:
                if not await client.is_user_authorized():
                    raise RuntimeError(
                        "Telethon-сессия не авторизована. Создайте новую: "
                        "python create_telethon_string.py (вход по QR), затем задайте "
                        "TELETHON_SESSION_STRING."
                    )
                yield client
            finally:
                await client.disconnect()

        HASHTAG_MAP = {
            "#гистология": "gistologiya", "#анатомия": "anatomiya",
            "#анат": "anatomiya", "#anat": "anatomiya", "#anatom": "anatomiya", "#anatomy": "anatomiya",
            "#биохимия": "biohimiya", "#биохим": "biohimiya", "#биох": "biohimiya", "#бхим": "biohimiya", "#бх": "biohimiya", "#bkh": "biohimiya", "#biochem": "biohimiya", "#biochemistry": "biohimiya",
            "#физиология": "fiziologiya",
            "#ішкіаурулар": "ishki", "#ішкі": "ishki",
            "#пропедевтика": "ishki", "#пропедевтики": "ishki", "#пропед": "ishki",
            "#внутренниеболезни": "ishki", "#внутренние": "ishki",
            "#патфиз": "patfiz", "#патанат": "patanat",
            "#топанат": "toanat", "#фармакология": "farmakologiya",
            "#фарма": "farmakologiya", "#фармо": "farmakologiya", "#фармако": "farmakologiya",
            "#pharmacology": "farmakologiya", "#pharmaco": "farmakologiya", "#pharma": "farmakologiya",
            "#микробиология": "mikrobiologiya", "#хирургия": "hirurgiya",
            "#генетика": "genetika", "#биофизика": "biofizika",
            "#тарих": "tarih",
        }
        SUBJECT_KW = {
            "anatomiya":      ["анатом","anatom","нетт","netter","синельник","сапин","билич","гайворон"],
            "gistologiya":    ["гистол","histol","цитол","эмбриол","ажаев","афанас","аяпов","тұңғыш"],
            "biohimiya":      ["биохим","биохи","биоким","biochem","biochemistry","bkh","северин","harper"],
            "fiziologiya":    ["физиол","physiol","гайтон","судаков"],
            "ishki":          ["ішкі","ishki","внутренн","терапи","пропедевт","пропед","неотложн"],
            "patfiz":         ["патофиз","patofiz","патфиз"],
            "patanat":        ["патанат","патологич","роббинс","струков"],
            "toanat":         ["топограф","топка","оперативн"],
            "farmakologiya":  ["фармакол","фарма","фармо","фармако","pharmacology","pharmaco","pharmac","pharma","катцунг","харкевич"],
            "hirurgiya":      ["хирург","hirurg"],
            "mikrobiologiya": ["микробиол","microbiol"],
            "genetika":       ["генет","genet"],
            "biofizika":      ["биофиз","biofiz"],
            "tarih":          ["тарих","tarih"],
        }
        LANG_KW = {
            "kaz": ["қаз","каз","қазақ","кітап","оқу","адам","жалпы","медициналық"],
            "eng": ["eng","english","netter","sobotta","gray","high-yield","textbook"],
        }

        def detect_subj(text):
            tl = text.lower().replace("ё", "е")
            # Проверяем каждый реальный хэштег отдельно и сначала сводим алиасы к предмету.
            # Например, #анат и #анатомия дают один код, а #патанат не путается с #анат.
            tag_tokens = ["#" + tag for tag in re.findall(r"(?<!\w)#(\w+)", tl)]
            tag_codes = list(dict.fromkeys(HASHTAG_MAP[tag] for tag in tag_tokens if tag in HASHTAG_MAP))
            if len(tag_codes) == 1:
                return tag_codes[0]
            if len(tag_codes) > 1:
                text_without_tags = re.sub(r"#\w+", " ", tl)
                best_tag_code, best_tag_len = None, 0
                for subj, kws in SUBJECT_KW.items():
                    for kw in kws:
                        kw = kw.lower()
                        if kw in text_without_tags and len(kw) > best_tag_len:
                            best_tag_code, best_tag_len = subj, len(kw)
                return best_tag_code or tag_codes[0]
            # составные названия
            if "патолог" in tl and "физиол" in tl:
                return "patfiz"
            if "патолог" in tl and "анатом" in tl:
                return "patanat"
            if "топограф" in tl and "анатом" in tl:
                return "toanat"
            # обычные ключевые слова: самое длинное совпадение
            best, best_len = None, 0
            for subj, kws in SUBJECT_KW.items():
                for kw in kws:
                    kw = kw.lower()
                    if kw in tl and len(kw) > best_len:
                        best, best_len = subj, len(kw)
            if best:
                return best
            # Последний общий разбор использует те же короткие/многоязычные синонимы,
            # что и поиск предмета (например, «БХ», «Биохим», «pharma»).
            alias_code = find_subject(text)
            return alias_code if alias_code in SUBJECTS.values() else "other"

        def detect_lang(text):
            tl = text.lower()
            for lang, kws in LANG_KW.items():
                for kw in kws:
                    if re.search(r"(?<!\w)" + re.escape(kw.lower()), tl):   # «eng» не ловит «length», «каз» — «указ»
                        return lang
            return "rus"

        def get_fname(doc):
            for attr in doc.attributes:
                if hasattr(attr, "file_name") and attr.file_name:
                    return attr.file_name
            return "unknown"

        result = {"new_db": {}, "total": 0, "covers": 0, "error": None}

        async def collect():
            try:
                new_db = {}
                total = 0
                timeline = []       # (id, фото, документ, дата, id_альбома) — посты канала
                book_entries = []   # (запись_книги, id_поста, дата, id_альбома)
                session_string = os.getenv("TELETHON_SESSION_STRING", "").strip()
                if session_string:
                    session = StringSession(session_string)
                else:
                    session_path = os.getenv(
                        "TELETHON_SESSION_PATH",
                        os.path.join(BASE_DIR, "update_session"),
                    )
                    if not os.path.isfile(session_path + ".session"):
                        raise RuntimeError(
                            "Для обновления каталога задайте TELETHON_SESSION_STRING "
                            "в переменных хостинга или подключите защищённый файл "
                            "сессии через TELETHON_SESSION_PATH."
                        )
                    session = session_path
                async with _telethon_client(session) as client:
                    async for msg in client.iter_messages(CHANNEL, limit=None):
                        is_document = bool(msg.media and isinstance(msg.media, MessageMediaDocument))
                        is_photo = bool(msg.media and isinstance(msg.media, MessageMediaPhoto))
                        if is_document and getattr(msg.media.document, "mime_type", "").startswith("image/"):
                            is_photo, is_document = True, False
                        grouped_id = getattr(msg, "grouped_id", None)
                        timeline.append((msg.id, is_photo, is_document, msg.date, grouped_id))
                        if not (msg.media and isinstance(msg.media, MessageMediaDocument)):
                            continue
                        doc = msg.media.document
                        fname = get_fname(doc)
                        mime = getattr(doc, "mime_type", "")
                        is_book = (
                            mime in ["application/pdf", "application/epub+zip"] or
                            any(fname.endswith(ext) for ext in [".pdf", ".djvu", ".epub"])
                        )
                        if not is_book:
                            continue
                        caption = msg.text or ""
                        subj = detect_subj(fname + " " + caption)
                        lang = detect_lang(fname + " " + caption)
                        if lang == "rus" and _is_english_filename(fname):
                            lang = "eng"
                        if subj not in new_db:
                            new_db[subj] = {"rus": [], "kaz": [], "eng": []}
                        entry = {
                            "message_id": msg.id,
                            "file_name":  fname,
                            "caption":    caption[:300],
                            "url":        f"https://t.me/library_adasan/{msg.id}",
                        }
                        new_db[subj][lang].append(entry)
                        book_entries.append((entry, msg.id, msg.date, grouped_id))
                        total += 1

                # Берём ближайший фото-пост перед файлом (до 10 минут), даже если
                # между обложкой и PDF стоит короткое текстовое сообщение. Через другой
                # документ обложку не переносим, чтобы не прикрепить чужое фото.
                timeline.sort(key=lambda t: t[0])
                entries_by_id = {mid: (entry, mdate, grouped_id)
                                 for entry, mid, mdate, grouped_id in book_entries}
                album_photo = {}
                for mid, is_photo, _is_document, _mdate, grouped_id in timeline:
                    if is_photo and grouped_id:
                        album_photo.setdefault(grouped_id, mid)
                covers = 0
                for entry, _mid, _mdate, grouped_id in book_entries:
                    if grouped_id and grouped_id in album_photo:
                        entry["photo_message_id"] = album_photo[grouped_id]
                        covers += 1

                last_photo = None
                last_document_id = 0
                for mid, is_photo, is_document, mdate, _grouped_id in timeline:
                    if is_photo:
                        last_photo = (mid, mdate)
                    if not is_document:
                        continue
                    book_item = entries_by_id.get(mid)
                    if book_item:
                        entry, book_date, _book_group = book_item
                        if (not entry.get("photo_message_id") and last_photo and
                                last_photo[0] > last_document_id and
                                0 <= (book_date - last_photo[1]).total_seconds() <= 600):
                            entry["photo_message_id"] = last_photo[0]
                            covers += 1
                    last_document_id = mid
                result["covers"] = covers
                result["new_db"] = new_db
                result["total"]  = total
            except Exception as e:
                result["error"] = str(e)

        # Telethon асинхронный — отдельный поток не нужен (раньше t.join() замораживал весь бот).
        async with _telethon_lock:
            try:
                await asyncio.wait_for(collect(), timeout=900)
            except asyncio.TimeoutError:
                await message.answer("❌ Таймаут: канал не успел прочитаться. База книг НЕ изменена.")
                return

        if result["error"]:
            await message.answer(f"❌ Қате: {result['error'][:300]}")
            return

        new_db = result["new_db"]
        total  = result["total"]
        old_total = sum(len(v) for langs in BOOKS_DB.values() for v in langs.values())
        if total == 0 or (old_total >= 20 and total < old_total * 0.5):
            await message.answer(
                f"❌ Подозрительный результат: найдено {total} книг, в базе сейчас {old_total}.\n"
                "База НЕ изменена. Проверьте сессию Telethon и повторите."
            )
            return
        normalize_existing_catalog(new_db)  # синонимы и тома одной серии без ручной сортировки
        inherit_series_covers(new_db)   # у следующих томов — обложка серии
        propagate_series_covers(new_db)   # одна обложка на все тома серии (любой язык/предмет)
        build_dynamic_catalog(new_db)   # разделы из хэштегов (#пропедевтика и т.д.)
        apply_sort_overrides(new_db)   # ручная сортировка из /sort_other не сбрасывается
        _refresh_catalog_names(new_db)

        db_path = os.path.join(BASE_DIR, "books_db.json")
        if os.path.isfile(db_path):                     # копия на случай ошибки
            shutil.copyfile(db_path, db_path + ".bak")
        tmp_path = db_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            _json2.dump(new_db, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, db_path)                   # запись целиком или никак

        replace_books_db(new_db)

        stats_text = "\n".join([
            f"  📚 {s}: {len(l.get('rus',[]))} рус | {len(l.get('kaz',[]))} қаз | {len(l.get('eng',[]))} eng"
            for s, l in sorted(new_db.items()) if s != "other"
        ])

        await message.answer(
            f"✅ Жаңартылды!\n\n"
            f"📖 Барлығы: {total} кітап\n"
            f"🖼 Мұқабасы бар / С обложкой: {result['covers']}\n\n"
            f"{stats_text}"
        )

        # Кто искал книги, которых раньше не было, и просил сообщить — уведомляем (ошибки сюда не попадают)
        try:
            closed, notified = await notify_wishes()
            if closed:
                await message.answer(f"🔔 Нашлись книги из ненайденных запросов: {closed}. Уведомлено людей: {notified}.")
        except Exception as e:
            logging.warning(f"Уведомления о новых книгах не отправлены: {e}")

    except ImportError:
        await message.answer("❌ telethon орнатылмаған!\npip install telethon")
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logging.error(tb)
        print(tb)
        await message.answer(f"❌ Қате: {str(e)[:300]}")

@dp.message(Command("sort_other"))
async def sort_other_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Рұқсат жоқ!")
        return
    text, kb = _sort_card()
    await message.answer(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)

@dp.callback_query(lambda c: c.data and c.data.startswith("srt_"))
async def sort_other_callback(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Рұқсат жоқ!", show_alert=True)
        return
    try:
        _, code, mid_s = callback.data.split("_", 2)
        mid = int(mid_s)
    except ValueError:
        await callback.answer("Қате / Ошибка данных")
        return

    if code == "files":
        await callback.answer("💾 Отправляю файлы")
        await _sort_send_files()
        return
    if code == "skip":
        _sort_skipped.add(mid)
        note = "⏭ Пропущено"
    elif code == "keep":
        ov = _load_sort_overrides()
        ov[str(mid)] = "other"
        _save_sort_overrides(ov)
        note = "📦 Остаётся в other"
    elif code in SUBJECTS.values():
        note = f"✅ → {code}" if _sort_move(mid, code) else "⚠️ Книга уже перенесена"
    else:
        await callback.answer("Неизвестный предмет")
        return

    await callback.answer(note)
    text, kb = _sort_card()
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb,
                                         disable_web_page_preview=True)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb,
                                      disable_web_page_preview=True)
    if kb is None:               # разбор закончен — сразу присылаем файлы
        await _sort_send_files()
