"""Обработчики для пользователей: команды, кнопки, меню предметов, книги, избранное, история."""

import asyncio
import os
from aiogram import types
from aiogram.filters import Command
from aiogram.types import FSInputFile
from aiogram.types import InlineKeyboardButton
from aiogram.types import InlineKeyboardMarkup

from buttons import is_button
from book_cards import (booklist_header, booklist_inline, lang_inline, send_book_card, send_subject_menu,
                        subject_book_count)
from books import BOOKS_DB, _find_by_message_id
from catalog import send_catalog
from core import BASE_DIR, bot, dp, logger
from database import (_mid_from_url, add_favorite, add_user, clear_book_history, get_book_history, get_favorites,
                      get_lang, remove_favorite_by_id, save_lang)
from keyboards import (BOT_INFO, CHANNEL_URL, anat_video_inline, back_menu_row, coming_soon_inline,
                       lang_select_keyboard, main_menu_keyboard, menu_button, start_inline, subscribe_keyboard)
from middlewares import check_subscription
from series import _plain_name
from subjects import SUBJECTS, SUBJECT_PHOTOS, subject_title
from texts import LANG_FLAGS, esc, help_text, tl, tr, user_lang, welcome_text
from views import render_favorites_image, send_favorites, send_popular

LOGO = os.path.join(BASE_DIR, "adasan.jpg")

CHOOSE_LANG_TEXT = "🌐 <b>Тілді таңдаңыз</b>\nВыберите язык · Choose language"


# =========================
# ОБЩИЕ ПОМОЩНИКИ
# =========================
async def _safe_delete(message):
    try:
        await message.delete()
    except Exception:
        pass


async def _edit(message, text, keyboard):
    """Меняет подпись фото или текст сообщения (смотря что это за сообщение). HTML-разметка."""
    try:
        if message.photo or message.document:
            await message.edit_caption(caption=text, parse_mode="HTML", reply_markup=keyboard)
        else:
            await message.edit_text(text=text, parse_mode="HTML", reply_markup=keyboard)
        return True
    except Exception as e:
        if "message is not modified" in str(e).lower():
            return True
        logger.debug("Не удалось изменить сообщение: %s", e)
        return False


async def send_welcome(chat_id, user, with_keyboard=False):
    """Главный экран: логотип + приветствие + кнопки. with_keyboard — заодно обновить нижнее меню."""
    lang = user_lang(user.id)
    await bot.send_photo(chat_id=chat_id, photo=FSInputFile(LOGO), caption=welcome_text(lang, user.first_name),
                         parse_mode="HTML", reply_markup=start_inline(lang))
    if with_keyboard:
        await bot.send_message(chat_id, tl(lang, "keyboard_ready"), reply_markup=main_menu_keyboard(lang))


async def ask_language(chat_id):
    await bot.send_photo(chat_id=chat_id, photo=FSInputFile(LOGO), caption=CHOOSE_LANG_TEXT,
                         parse_mode="HTML", reply_markup=lang_select_keyboard())


def _int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# =========================
# КОМАНДЫ
# =========================
@dp.message(Command("start"))
async def start(message: types.Message):
    user = message.from_user
    is_new = add_user(user.id, user.username, user.first_name)
    if not await check_subscription(user.id):
        await message.answer_photo(
            photo=FSInputFile(LOGO),
            caption=("👋 <b>Сәлем! Привет! Hello!</b>\n\n"
                     "🔒 Ботты пайдалану үшін арнаға жазылыңыз.\n"
                     "Чтобы пользоваться ботом, подпишитесь на канал.\n"
                     "Subscribe to the channel to use the bot.\n\n"
                     "👇"),
            parse_mode="HTML",
            reply_markup=subscribe_keyboard(),
        )
        return
    if message.chat.type != "private":
        await send_welcome(message.chat.id, user)
        return
    # Новичок выбирает язык. Раньше язык спрашивали при КАЖДОМ /start — теперь сразу открываем меню.
    if is_new:
        await ask_language(message.chat.id)
    else:
        await send_welcome(message.chat.id, user, with_keyboard=True)


@dp.message(Command("menu"))
@dp.message(is_button("menu"))
async def menu_command(message: types.Message):
    await send_welcome(message.chat.id, message.from_user)


@dp.message(Command("lang"))
@dp.message(is_button("lang"))
async def lang_command(message: types.Message):
    """Смена языка без /start (не нужно заново проходить проверку подписки)."""
    await message.answer(CHOOSE_LANG_TEXT, parse_mode="HTML", reply_markup=lang_select_keyboard())


@dp.message(Command("help"))
@dp.message(is_button("help"))
async def help_command(message: types.Message):
    lang = user_lang(message.from_user.id)
    await message.answer(
        help_text(lang, BOT_INFO["username"]),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[menu_button(lang)]]),
    )


@dp.message(Command("channel", "chanel"))
async def channel(message: types.Message):
    lang = user_lang(message.from_user.id)
    await message.answer(
        "📌 <b>Adasan Library</b>\n\n👉 @library_adasan\n\n"
        + {"kz": "Барлық кітаптар мен материалдар сонда! 📚",
           "ru": "Все книги и материалы — там! 📚",
           "en": "All books and materials are there! 📚"}[lang],
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=tl(lang, "btn_channel"), url=CHANNEL_URL)],
        ]),
    )


@dp.message(Command("favorites", "fav"))
@dp.message(is_button("favorites"))
async def favorites_command(message: types.Message):
    await send_favorites(message)


@dp.callback_query(lambda c: c.data and c.data.startswith("fav_del_id_"))
async def fav_del_handler(callback: types.CallbackQuery):
    uid = callback.from_user.id
    lang = user_lang(uid)
    favorite_id = _int(callback.data.rsplit("_", 1)[-1])
    if favorite_id is None or not any(row[0] == favorite_id for row in get_favorites(uid)):
        await callback.answer(tl(lang, "fav_stale"), show_alert=True)
        return
    remove_favorite_by_id(uid, favorite_id)
    await callback.answer(tl(lang, "fav_removed"))
    favs = get_favorites(uid)
    if not favs:
        if not await _edit(callback.message, tl(lang, "fav_empty"),
                           InlineKeyboardMarkup(inline_keyboard=[[menu_button(lang)]])):
            await _safe_delete(callback.message)
            await callback.message.answer(tl(lang, "fav_empty"), parse_mode="HTML")
        return

    from views import favorites_keyboard                      # одна клавиатура для списка и после удаления
    keyboard = favorites_keyboard(favs, lang)
    caption = tl(lang, "fav_caption", n=len(favs))
    try:
        png = await asyncio.to_thread(render_favorites_image, [{"title": row[4]} for row in favs])
        media = types.InputMediaPhoto(media=types.BufferedInputFile(png, filename="my_favorite_books.png"),
                                      caption=caption, parse_mode="HTML")
        await callback.message.edit_media(media=media, reply_markup=keyboard)
    except Exception as exc:
        logger.warning("Не удалось обновить карточку избранного: %s", exc)
        await _edit(callback.message, caption, keyboard)


# =========================
# CALLBACK — выбор языка, подписка
# =========================
@dp.callback_query(lambda c: c.data and c.data.startswith("setlang_"))
async def setlang_handler(callback: types.CallbackQuery):
    lang = callback.data.replace("setlang_", "")
    if lang not in ("kz", "ru", "en"):                    # защита от подделанной кнопки
        await callback.answer()
        return
    save_lang(callback.from_user.id, lang)
    await callback.answer(tl(lang, "lang_saved"))
    await _safe_delete(callback.message)
    await send_welcome(callback.message.chat.id, callback.from_user, with_keyboard=True)


@dp.callback_query(lambda c: c.data == "check_sub")
async def check_sub_handler(callback: types.CallbackQuery):
    if await check_subscription(callback.from_user.id, force=True):
        await callback.answer("✅")
        await _safe_delete(callback.message)
        await ask_language(callback.message.chat.id)
    else:
        await callback.answer("❌ Сіз әлі жазылмадыңыз! / Вы ещё не подписались! / Not subscribed yet!",
                              show_alert=True)


# =========================
# CALLBACK — Главное меню и быстрые действия
# =========================
@dp.callback_query(lambda c: c.data == "go_main_menu")
async def go_main_menu(callback: types.CallbackQuery):
    await callback.answer()
    await send_welcome(callback.message.chat.id, callback.from_user)
    await _safe_delete(callback.message)


@dp.callback_query(lambda c: c.data == "go_popular")
async def go_popular(callback: types.CallbackQuery):
    await callback.answer()
    await send_popular(callback.message)


@dp.callback_query(lambda c: c.data == "go_fav")
async def go_fav(callback: types.CallbackQuery):
    await callback.answer()
    await send_favorites(callback.message, uid=callback.from_user.id)


@dp.callback_query(lambda c: c.data == "go_lang")
async def go_lang(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer(CHOOSE_LANG_TEXT, parse_mode="HTML", reply_markup=lang_select_keyboard())


@dp.callback_query(lambda c: c.data == "open_subjects")
async def open_subjects(callback: types.CallbackQuery):
    """Старая кнопка из прежних версий меню — теперь просто открывает каталог."""
    await callback.answer()
    await send_catalog(callback.message)


# =========================
# CALLBACK — предмет и его разделы
# =========================
@dp.callback_query(lambda c: c.data and c.data.startswith("subject_"))
async def back_to_subject(callback: types.CallbackQuery):
    code = callback.data.replace("subject_", "", 1)
    await callback.answer()
    await send_subject_menu(callback.message.chat.id, code, uid=callback.from_user.id)
    await _safe_delete(callback.message)


async def _coming_soon(callback, code, section_key):
    lang = user_lang(callback.from_user.id)
    text = tl(lang, "coming_soon", name=esc(subject_title(code, lang)), section=tl(lang, section_key))
    if not await _edit(callback.message, text, coming_soon_inline(code, lang)):
        await callback.message.answer(text, parse_mode="HTML", reply_markup=coming_soon_inline(code, lang))
    await callback.answer()


async def _section_screen(callback, code, section_key, body, keyboard, photo=None):
    """Экран раздела (силлабус, лекции, препараты, видео): фото предмета + описание + кнопки."""
    lang = user_lang(callback.from_user.id)
    caption = tl(lang, "section_card", section=tl(lang, section_key),
                 name=esc(subject_title(code, lang)), body=body)
    photo_path = os.path.join(BASE_DIR, photo or SUBJECT_PHOTOS.get(code, "adasan.jpg"))
    if not os.path.exists(photo_path):
        photo_path = LOGO
    await bot.send_photo(chat_id=callback.message.chat.id, photo=FSInputFile(photo_path), caption=caption,
                         parse_mode="HTML", reply_markup=keyboard)
    await _safe_delete(callback.message)
    await callback.answer()


def _link_keyboard(lang, label, url, back_code):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, url=url)],
        back_menu_row(lang, f"subject_{back_code}"),
    ])


@dp.callback_query(lambda c: c.data and c.data.startswith("books_"))
async def books_handler(callback: types.CallbackQuery):
    code = callback.data.replace("books_", "", 1)
    uid = callback.from_user.id
    lang = user_lang(uid)
    total = subject_book_count(code)
    if total == 0:
        await _coming_soon(callback, code, "btn_books")
        return
    caption = tl(lang, "books_choose_lang", name=esc(subject_title(code, lang)), n=total)
    photo_path = os.path.join(BASE_DIR, SUBJECT_PHOTOS.get(code, "adasan.jpg"))
    if not os.path.exists(photo_path):
        photo_path = LOGO
    await bot.send_photo(chat_id=callback.message.chat.id, photo=FSInputFile(photo_path), caption=caption,
                         parse_mode="HTML", reply_markup=lang_inline(code, uid))
    await _safe_delete(callback.message)
    await callback.answer()


SILABUS_URLS = {
    "gistologiya": "https://t.me/library_adasan/436",
    "fiziologiya": "https://t.me/library_adasan/437",
    "biofizika":   "https://t.me/library_adasan/437",
    "biohimiya":   "https://t.me/library_adasan/437",
    "anatomiya":   "https://t.me/library_adasan/437",
    "genetika":    "https://t.me/library_adasan/437",
}

LECTURES = {   # предмет -> (текст описания, ссылка, фото)
    "gistologiya": ("body_lecture_gist", "https://t.me/library_adasan/319", "gistologiya.jpg"),
    "tarih":       ("body_lecture_tarih", "https://t.me/library_adasan/471", None),
}

PREPARATY = {
    "gistologiya": ("body_preps", "https://t.me/library_adasan/268", "gistologiya.jpg"),
}


@dp.callback_query(lambda c: c.data and c.data.startswith("silabus_"))
async def silabus_handler(callback: types.CallbackQuery):
    code = callback.data.replace("silabus_", "", 1)
    if code not in SILABUS_URLS:
        await _coming_soon(callback, code, "btn_syllabus")
        return
    lang = user_lang(callback.from_user.id)
    await _section_screen(callback, code, "btn_syllabus", tl(lang, "body_syllabus"),
                          _link_keyboard(lang, tl(lang, "btn_download"), SILABUS_URLS[code], code))


@dp.callback_query(lambda c: c.data and c.data.startswith("lektsiya_"))
async def lektsiya_handler(callback: types.CallbackQuery):
    code = callback.data.replace("lektsiya_", "", 1)
    if code not in LECTURES:
        await _coming_soon(callback, code, "btn_lecture")
        return
    lang = user_lang(callback.from_user.id)
    body_key, url, photo = LECTURES[code]
    await _section_screen(callback, code, "btn_lecture", tl(lang, body_key),
                          _link_keyboard(lang, tl(lang, "btn_download"), url, code), photo=photo)


@dp.callback_query(lambda c: c.data and c.data.startswith("preparaty_"))
async def preparaty_handler(callback: types.CallbackQuery):
    code = callback.data.replace("preparaty_", "", 1)
    if code not in PREPARATY:
        await _coming_soon(callback, code, "btn_preps")
        return
    lang = user_lang(callback.from_user.id)
    body_key, url, photo = PREPARATY[code]
    await _section_screen(callback, code, "btn_preps", tl(lang, body_key),
                          _link_keyboard(lang, tl(lang, "btn_download"), url, code), photo=photo)


@dp.callback_query(lambda c: c.data and c.data.startswith("video_"))
async def video_handler(callback: types.CallbackQuery):
    code = callback.data.replace("video_", "", 1)
    lang = user_lang(callback.from_user.id)
    if code == "anatomiya":
        await _section_screen(callback, code, "btn_video", tl(lang, "body_video_anat"), anat_video_inline(lang))
    elif code == "hirurgiya":
        await _section_screen(callback, code, "btn_video", tl(lang, "body_video_surg"),
                              _link_keyboard(lang, tl(lang, "btn_channel"), CHANNEL_URL, code))
    else:
        await _coming_soon(callback, code, "btn_video")


# =========================
# CALLBACK — списки книг и карточка книги
# =========================
@dp.callback_query(lambda c: c.data and c.data.startswith(("bl_", "bp_")))
async def booklist_handler(callback: types.CallbackQuery):
    """bl_<предмет>_<язык> — первая страница, bp_<предмет>_<язык>_<страница> — листание.
    Разбираем с конца (rsplit): так не ломается, даже если в коде раздела окажется «_»."""
    uid = callback.from_user.id
    try:
        if callback.data.startswith("bl_"):
            subject_code, lang = callback.data[3:].rsplit("_", 1)
            page = 0
        else:
            subject_code, lang, page_raw = callback.data[3:].rsplit("_", 2)
            page = int(page_raw)
    except ValueError:
        await callback.answer(tr(uid, "book_nf_alert"), show_alert=True)
        return
    text = booklist_header(uid, subject_code, lang, page)
    keyboard = booklist_inline(subject_code, lang, page, uid)
    if not await _edit(callback.message, text, keyboard):
        await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard)
        await _safe_delete(callback.message)
    await callback.answer()


@dp.callback_query(lambda c: c.data and c.data.startswith(("bk_", "bm_")))
async def bookopen_handler(callback: types.CallbackQuery):
    """bk_<предмет>_<язык>_<индекс> — из свежих списков; bm_<message_id> — из избранного и истории
    (не ломается после /update_books и /sort_other, когда индексы книг сдвигаются)."""
    uid = callback.from_user.id
    loc = None
    if callback.data.startswith("bm_"):
        mid = _int(callback.data[3:])
        loc = _find_by_message_id(mid) if mid else None
    else:
        try:
            sc, lg, idx = callback.data[3:].rsplit("_", 2)
            loc = (sc, lg, int(idx))
        except ValueError:
            loc = None
    if not loc or not await send_book_card(callback.message.chat.id, uid, *loc):
        await callback.answer(tr(uid, "book_nf_alert"), show_alert=True)
        return
    await _safe_delete(callback.message)
    await callback.answer()


@dp.callback_query(lambda c: c.data and c.data.startswith("fav_add_"))
async def fav_add_handler(callback: types.CallbackQuery):
    uid = callback.from_user.id
    try:
        subject_code, lang, idx_raw = callback.data.replace("fav_add_", "", 1).rsplit("_", 2)
        book = BOOKS_DB.get(subject_code, {}).get(lang, [])[int(idx_raw)]
    except (ValueError, IndexError):
        await callback.answer(tr(uid, "book_nf_alert"), show_alert=True)
        return
    book_name = _plain_name(book.get("file_name", ""))[:50]
    added = add_favorite(uid, subject_code, lang, int(idx_raw), book_name, book["url"])
    await callback.answer(tr(uid, "fav_added" if added else "fav_exists"), show_alert=True)


# =========================
# ИСТОРИЯ
# =========================
def _history_screen(uid):
    lang = user_lang(uid)
    history = get_book_history(uid, limit=10)
    if not history:
        return tl(lang, "history_empty"), InlineKeyboardMarkup(inline_keyboard=[[menu_button(lang)]])
    rows = []
    for sc, lg, bi, bn, bu, opened_at in history:
        date_str = f"{opened_at[8:10]}.{opened_at[5:7]}" if opened_at and len(opened_at) >= 10 else ""
        flag = LANG_FLAGS.get(lg, "📖")
        rows.append([InlineKeyboardButton(text=f"{flag} {bn[:30]}  · {date_str}".rstrip(" ·"),
                                          callback_data=f"bm_{_mid_from_url(bu)}")])
    rows.append([InlineKeyboardButton(text=tl(lang, "btn_clear_history"), callback_data="hist_clear"),
                 menu_button(lang)])
    return tl(lang, "history_title", n=len(history)), InlineKeyboardMarkup(inline_keyboard=rows)


@dp.message(Command("history"))
@dp.message(is_button("history"))
async def history_command(message: types.Message):
    text, keyboard = _history_screen(message.from_user.id)
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@dp.callback_query(lambda c: c.data == "hist_clear")
async def history_clear(callback: types.CallbackQuery):
    uid = callback.from_user.id
    clear_book_history(uid)
    await callback.answer(tr(uid, "history_cleared"))
    text, keyboard = _history_screen(uid)
    await _edit(callback.message, text, keyboard)


# =========================
# КНОПКИ ПРЕДМЕТОВ НИЖНЕЙ КЛАВИАТУРЫ
# =========================
@dp.message(lambda m: m.text and m.text.lower() in SUBJECTS)
async def open_subject(message: types.Message):
    await send_subject_menu(message.chat.id, SUBJECTS[message.text.lower()], uid=message.from_user.id)


@dp.message(is_button("legacy_subjects"))
async def all_subjects_button(message: types.Message):
    """Кнопку «Все предметы» убрали из клавиатуры, но у части пользователей она ещё висит:
    показываем каталог и сразу подсовываем обновлённую клавиатуру."""
    await send_catalog(message)
    lang = get_lang(message.from_user.id)
    await message.answer(tl(user_lang(message.from_user.id), "keyboard_ready"), reply_markup=main_menu_keyboard(lang))
