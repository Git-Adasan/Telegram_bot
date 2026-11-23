"""Обработчики для пользователей: команды, кнопки, меню предметов, книги, избранное, история."""

import asyncio
import os
from aiogram import types
from aiogram.filters import Command
from aiogram.types import FSInputFile
from aiogram.types import InlineKeyboardButton
from aiogram.types import InlineKeyboardMarkup

from buttons import is_button
from book_cards import _list_entries, _send_series_card, book_card_keyboard, booklist_inline, lang_inline, send_subject_menu
from books import BOOKS_DB, _find_by_message_id
from catalog import send_catalog
from core import BASE_DIR, CHANNEL, bot, dp, logger
from database import _mid_from_url, add_book_history, add_favorite, add_user, get_book_history, get_favorites, get_lang, record_book_open, remove_favorite_by_id, save_lang
from keyboards import anat_video_inline, coming_soon_inline, lang_select_keyboard, main_menu_keyboard, menu_button, start_inline, subscribe_keyboard
from middlewares import check_subscription
from series import series_info
from subjects import SUBJECTS, SUBJECT_NAMES, SUBJECT_PHOTOS
from texts import HELP_TEXTS, WELCOME_TEXTS, tr
from views import render_favorites_image, send_favorites, send_popular


# =========================
# КОМАНДЫ
# =========================
@dp.message(Command("start"))
async def start(message: types.Message):
    add_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    is_subscribed = await check_subscription(message.from_user.id)
    if not is_subscribed:
        await message.answer_photo(
            photo=FSInputFile(os.path.join(BASE_DIR, "adasan.jpg")),
            caption=(
                "👋 Сәлем!\n\n"
                "🔒 Ботты пайдалану үшін\n"
                "біздің каналға жазылу керек!\n\n"
                "👇 Төмендегі батырманы басыңыз:"
            ),
            reply_markup=subscribe_keyboard()
        )
        return
    await message.answer_photo(
        photo=FSInputFile(os.path.join(BASE_DIR, "adasan.jpg")),
        caption="🌐 Тілді таңдаңыз\nВыберите язык\nChoose language:",
        reply_markup=lang_select_keyboard()
    )

@dp.message(Command("menu"))
@dp.message(is_button("menu"))
async def menu_command(message: types.Message):
    lang = get_lang(message.from_user.id)
    welcome = WELCOME_TEXTS.get(lang, WELCOME_TEXTS["kz"]).format(name=message.from_user.first_name)
    await message.answer_photo(
        photo=FSInputFile(os.path.join(BASE_DIR, "adasan.jpg")),
        caption=welcome,
        reply_markup=start_inline(lang)
    )

@dp.message(Command("lang"))
@dp.message(is_button("lang"))
async def lang_command(message: types.Message):
    """Смена языка без /start (не нужно заново проходить проверку подписки)."""
    await message.answer("🌐 Тілді таңдаңыз\nВыберите язык\nChoose language:", reply_markup=lang_select_keyboard())

@dp.message(Command("help"))
async def help_command(message: types.Message):
    lang = get_lang(message.from_user.id)
    await message.answer(
        HELP_TEXTS.get(lang, HELP_TEXTS["kz"]),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[menu_button()]])
    )

@dp.message(Command("chanel"))
async def channel(message: types.Message):
    await message.answer(
        "📌 Біздің кітапхана каналы:\n\n"
        "👉 @library_adasan\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Барлық кітаптар мен материалдар сонда! 📚",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📌 Каналға өту", url="https://t.me/library_adasan")],
        ])
    )

@dp.message(Command("favorites", "fav"))
async def favorites_command(message: types.Message):
    await send_favorites(message)

@dp.message(is_button("favorites"))
async def favorites_button(message: types.Message):
    await send_favorites(message)

@dp.callback_query(lambda c: c.data and c.data.startswith("fav_del_id_"))
async def fav_del_handler(callback: types.CallbackQuery):
    try:
        favorite_id = int(callback.data.rsplit("_", 1)[1])
    except (ValueError, IndexError):
        await callback.answer("Не удалось определить книгу.", show_alert=True)
        return
    before = get_favorites(callback.from_user.id)
    if not any(row[0] == favorite_id for row in before):
        await callback.answer("Книга уже удалена или список устарел. Откройте избранное заново.", show_alert=True)
        return
    remove_favorite_by_id(callback.from_user.id, favorite_id)
    await callback.answer("🗑 Удалено из любимых книг.")
    favs = get_favorites(callback.from_user.id)
    if not favs:
        try:
            await callback.message.edit_caption(
                caption="⭐ Мои любимые книги\n\nСписок пока пуст.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [menu_button()]
                ])
            )
        except Exception:
            try:
                await callback.message.delete()
            except Exception:
                pass
            await callback.message.answer("⭐ Мои любимые книги\n\nСписок пока пуст.")
        return

    entries = [{"title": row[4]} for row in favs]
    rows = []
    for fav_id, sc, lg, bi, bn, bu in favs:
        rows.append([
            InlineKeyboardButton(text=f"📖 {bn[:32]}", callback_data=f"bm_{_mid_from_url(bu)}"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"fav_del_id_{fav_id}"),
        ])
    rows.append([menu_button()])
    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    try:
        png = await asyncio.to_thread(render_favorites_image, entries)
        media = types.InputMediaPhoto(
            media=types.BufferedInputFile(png, filename="my_favorite_books.png"),
            caption=f"⭐ Мои любимые книги · {len(favs)}"
        )
        await callback.message.edit_media(media=media, reply_markup=keyboard)
    except Exception as exc:
        logger.warning("Не удалось обновить карточку избранного: %s", exc)
        try:
            await callback.message.edit_caption(
                caption=f"⭐ Мои любимые книги · {len(favs)}",
                reply_markup=keyboard
            )
        except Exception:
            try:                                   # карточка была обычным текстом, без картинки
                await callback.message.edit_text(f"⭐ Мои любимые книги · {len(favs)}", reply_markup=keyboard)
            except Exception:
                pass

# CALLBACK — выбор языка
# =========================
@dp.callback_query(lambda c: c.data and c.data.startswith("setlang_"))
async def setlang_handler(callback: types.CallbackQuery):
    lang = callback.data.replace("setlang_", "")
    save_lang(callback.from_user.id, lang)
    name = callback.from_user.first_name
    welcome = WELCOME_TEXTS.get(lang, WELCOME_TEXTS["kz"]).format(name=name)
    await callback.message.delete()
    await bot.send_photo(
        chat_id=callback.message.chat.id,
        photo=FSInputFile(os.path.join(BASE_DIR, "adasan.jpg")),
        caption=welcome,
        reply_markup=start_inline(lang)
    )
    await bot.send_message(chat_id=callback.message.chat.id, text="👇", reply_markup=main_menu_keyboard(lang))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "check_sub")
async def check_sub_handler(callback: types.CallbackQuery):
    if await check_subscription(callback.from_user.id, force=True):
        await callback.message.delete()
        await bot.send_photo(
            chat_id=callback.message.chat.id,
            photo=FSInputFile(os.path.join(BASE_DIR, "adasan.jpg")),
            caption="🌐 Тілді таңдаңыз\nВыберите язык\nChoose language:",
            reply_markup=lang_select_keyboard()
        )
    else:
        await callback.answer("❌ Сіз әлі жазылмадыңыз!", show_alert=True)

# =========================
# CALLBACK — Главное меню
# =========================
@dp.callback_query(lambda c: c.data == "go_main_menu")
async def go_main_menu(callback: types.CallbackQuery):
    lang = get_lang(callback.from_user.id)
    welcome = WELCOME_TEXTS.get(lang, WELCOME_TEXTS["kz"]).format(name=callback.from_user.first_name)
    await bot.send_photo(
        chat_id=callback.message.chat.id,
        photo=FSInputFile(os.path.join(BASE_DIR, "adasan.jpg")),
        caption=welcome,
        reply_markup=start_inline(lang)
    )
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()

# Кнопки быстрых действий под приветствием
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
    await callback.message.answer("🌐 Тілді таңдаңыз\nВыберите язык\nChoose language:", reply_markup=lang_select_keyboard())

@dp.callback_query(lambda c: c.data == "open_subjects")
async def open_subjects(callback: types.CallbackQuery):
    await callback.message.edit_caption(
        caption="📚 Пәнді таңдаңыз / Выберите предмет / Choose subject:",
        reply_markup=start_inline()
    )
    await callback.answer()

# =========================
# CALLBACK — предмет
# =========================
@dp.callback_query(lambda c: c.data and c.data.startswith("subject_"))
async def back_to_subject(callback: types.CallbackQuery):
    code = callback.data.replace("subject_", "")
    await send_subject_menu(callback.message.chat.id, code)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()

# =========================
# CALLBACK — Книги
# =========================
@dp.callback_query(lambda c: c.data and c.data.startswith("books_"))
async def books_handler(callback: types.CallbackQuery):
    code = callback.data.replace("books_", "")
    name = SUBJECT_NAMES.get(code, "📚 Другое")
    photo_path = os.path.join(BASE_DIR, SUBJECT_PHOTOS.get(code, "adasan.jpg"))
    langs = BOOKS_DB.get(code, {})
    total = sum(len(v) for v in langs.values())

    if total > 0:
        caption = (
            f"╔══════════════════════╗\n"
            f"       📚 КІТАПТАР — {name}\n"
            f"╚══════════════════════╝\n\n"
            f"📖 Барлығы: {total} кітап\n\n"
            f"👇 Тілді таңдаңыз / Выберите язык / Choose language:\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 @library_adasan"
        )
        await bot.send_photo(
            chat_id=callback.message.chat.id,
            photo=FSInputFile(photo_path),
            caption=caption,
            reply_markup=lang_inline(code, callback.from_user.id)
        )
        try:
            await callback.message.delete()
        except Exception:
            pass
    else:
        try:
            await callback.message.edit_caption(
                caption=f"{name} — Книги\n\n⏳ Скоро будет доступно!",
                reply_markup=coming_soon_inline(code)
            )
        except:
            await callback.message.edit_text(
                text=f"{name} — Книги\n\n⏳ Скоро будет доступно!",
                reply_markup=coming_soon_inline(code)
            )
    await callback.answer()

# =========================
# CALLBACK — Силлабус
# =========================
@dp.callback_query(lambda c: c.data and c.data.startswith("silabus_"))
async def silabus_handler(callback: types.CallbackQuery):
    code = callback.data.replace("silabus_", "")
    name = SUBJECT_NAMES.get(code, "📚 Другое")
    photo_path = os.path.join(BASE_DIR, SUBJECT_PHOTOS.get(code, "adasan.jpg"))
    SILABUS_URLS = {
        "gistologiya": "https://t.me/library_adasan/436",
        "fiziologiya": "https://t.me/library_adasan/437",
        "biofizika":   "https://t.me/library_adasan/437",
        "biohimiya":   "https://t.me/library_adasan/437",
        "anatomiya":   "https://t.me/library_adasan/437",
        "genetika":    "https://t.me/library_adasan/437",
    }
    if code in SILABUS_URLS:
        caption = (
            f"╔══════════════════════╗\n"
            f"      📋 СИЛЛАБУС — {name}\n"
            f"╚══════════════════════╝\n\n"
            f"📖 Пән: {name}\n"
            f"🎯 Силлабуста не бар:\n"
            f"    • Пәннің мақсаты мен міндеттері\n"
            f"    • Тақырыптар тізімі\n"
            f"    • Баға критерийлері\n"
            f"    • Әдебиеттер тізімі\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 @library_adasan"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📥 Силлабусты жүктеу / Скачать", url=SILABUS_URLS[code])],
            [InlineKeyboardButton(text="⬅ Артқа / Назад / Back", callback_data=f"subject_{code}")],
            [menu_button()],
        ])
        await bot.send_photo(chat_id=callback.message.chat.id,
                             photo=FSInputFile(photo_path), caption=caption, reply_markup=keyboard)
        try:
            await callback.message.delete()
        except Exception:
            pass
    else:
        try:
            await callback.message.edit_caption(
                caption=f"{name} — Силлабус\n\n⏳ Скоро будет доступно!",
                reply_markup=coming_soon_inline(code)
            )
        except:
            await callback.message.edit_text(
                f"{name} — Силлабус\n\n⏳ Скоро будет доступно!",
                reply_markup=coming_soon_inline(code)
            )
    await callback.answer()

# =========================
# CALLBACK — Лекция
# =========================
@dp.callback_query(lambda c: c.data and c.data.startswith("lektsiya_"))
async def lektsiya_handler(callback: types.CallbackQuery):
    code = callback.data.replace("lektsiya_", "")
    if code == "gistologiya":
        photo_path = os.path.join(BASE_DIR, "gistologiya.jpg")
        caption = (
            "╔══════════════════════╗\n"
            "       🎓 ЛЕКЦИЯ — ГИСТОЛОГИЯ\n"
            "╚══════════════════════╝\n\n"
            "📖 Пән: Гистология, Эмбриология, Цитология\n"
            "🎯 Лекцияда не бар:\n"
            "    • Толық лекция конспектілері\n"
            "    • Схемалар мен кестелер\n"
            "    • Сурет материалдары\n"
            "    • Емтиханға дайындық\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 @library_adasan"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📥 Лекцияны жүктеу / Скачать", url="https://t.me/library_adasan/319")],
            [InlineKeyboardButton(text="⬅ Артқа / Назад / Back", callback_data="subject_gistologiya")],
            [menu_button()],
        ])
        await bot.send_photo(chat_id=callback.message.chat.id,
                             photo=FSInputFile(photo_path), caption=caption, reply_markup=keyboard)
        try:
            await callback.message.delete()
        except Exception:
            pass
    elif code == "tarih":
        photo_path = os.path.join(BASE_DIR, SUBJECT_PHOTOS.get(code, "adasan.jpg"))
        caption = (
            "╔══════════════════════╗\n"
            "       📖 ЛЕКЦИЯ — ТАРИХ\n"
            "╚══════════════════════╝\n\n"
            "📚 1-тақырыптан 15-тақырыпқа дейін\n"
            "🎯 Барлық лекциялар қосылған\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 @library_adasan"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📖 Барлық лекциялар", url="https://t.me/library_adasan/471")],
            [InlineKeyboardButton(text="⬅ Артқа / Назад / Back", callback_data="subject_tarih")],
            [menu_button()],
        ])
        await bot.send_photo(chat_id=callback.message.chat.id,
                             photo=FSInputFile(photo_path), caption=caption, reply_markup=keyboard)
        try:
            await callback.message.delete()
        except Exception:
            pass
    else:
        name = SUBJECT_NAMES.get(code, "📚 Другое")
        try:
            await callback.message.edit_caption(
                caption=f"{name} — Лекция\n\n⏳ Скоро будет доступно!",
                reply_markup=coming_soon_inline(code)
            )
        except:
            await callback.message.edit_text(
                f"{name} — Лекция\n\n⏳ Скоро будет доступно!",
                reply_markup=coming_soon_inline(code)
            )
    await callback.answer()

# =========================
# CALLBACK — Препараты
# =========================
@dp.callback_query(lambda c: c.data and c.data.startswith("preparaty_"))
async def preparaty_handler(callback: types.CallbackQuery):
    code = callback.data.replace("preparaty_", "")
    if code == "gistologiya":
        photo_path = os.path.join(BASE_DIR, "gistologiya.jpg")
        caption = (
            "╔══════════════════════╗\n"
            "      🔬 ПРЕПАРАТЫ — ГИСТОЛОГИЯ\n"
            "╚══════════════════════╝\n\n"
            "📖 Пән: Гистология, Эмбриология, Цитология\n"
            "🎯 Препараттарда не бар:\n"
            "    • Микроскопиялық препараттар\n"
            "    • Атлас суреттері\n"
            "    • Препараттарды сипаттау\n"
            "    • Практикалық сабаққа дайындық\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 @library_adasan"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📥 Препараттарды жүктеу / Скачать", url="https://t.me/library_adasan/268")],
            [InlineKeyboardButton(text="⬅ Артқа / Назад / Back", callback_data="subject_gistologiya")],
            [menu_button()],
        ])
        await bot.send_photo(chat_id=callback.message.chat.id,
                             photo=FSInputFile(photo_path), caption=caption, reply_markup=keyboard)
        try:
            await callback.message.delete()
        except Exception:
            pass
    else:
        name = SUBJECT_NAMES.get(code, "📚 Другое")
        try:
            await callback.message.edit_caption(
                caption=f"{name} — Препараты\n\n⏳ Скоро будет доступно!",
                reply_markup=coming_soon_inline(code)
            )
        except:
            await callback.message.edit_text(
                f"{name} — Препараты\n\n⏳ Скоро будет доступно!",
                reply_markup=coming_soon_inline(code)
            )
    await callback.answer()

@dp.callback_query(lambda c: c.data and c.data.startswith("video_"))
async def video_handler(callback: types.CallbackQuery):
    code = callback.data.replace("video_", "")
    photo_path = os.path.join(BASE_DIR, SUBJECT_PHOTOS.get(code, "adasan.jpg"))
    if code == "anatomiya":
        caption = (
            "╔══════════════════════╗\n"
            "   🎬 БЕЙНЕСАБАҚ — АНАТОМИЯ\n"
            "╚══════════════════════╝\n\n"
            "📹 Тақырыптар:\n"
            "    🦴 Остеология\n"
            "    💀 Бас сүйек топографиясы\n"
            "    💪 Миология\n"
            "    🦵 Синдесмология\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 @library_adasan"
        )
        keyboard = anat_video_inline()
    elif code == "hirurgiya":
        caption = (
            "╔══════════════════════╗\n"
            "   🎬 БЕЙНЕСАБАҚ — ХИРУРГИЯ\n"
            "╚══════════════════════╝\n\n"
            "📹 Хирургиялық техникалар\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 @library_adasan"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📌 Каналдан қарау", url="https://t.me/library_adasan")],
            [InlineKeyboardButton(text="⬅ Артқа / Назад / Back", callback_data="subject_hirurgiya")],
            [menu_button()],
        ])
    else:
        await callback.answer("⏳ Скоро будет!")
        return
    await bot.send_photo(chat_id=callback.message.chat.id,
                         photo=FSInputFile(photo_path), caption=caption, reply_markup=keyboard)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()

@dp.callback_query(lambda c: c.data and c.data.startswith("bl_"))
async def booklang_handler(callback: types.CallbackQuery):
    _, subject_code, lang = callback.data.split("_", 2)
    count = len(_list_entries(subject_code, lang))     # тома одной книги считаются за одну
    name = SUBJECT_NAMES.get(subject_code, "📚 Другое")
    lang_name = {"rus": "🇷🇺 Русский", "kaz": "🇰🇿 Қазақша", "eng": "🇬🇧 English"}.get(lang, lang)
    uid = callback.from_user.id
    try:
        await callback.message.edit_caption(
            caption=tr(uid, "list_header", name=name, lang=lang_name, n=count),
            reply_markup=booklist_inline(subject_code, lang, 0, uid)
        )
    except:
        await callback.message.edit_text(
            text=tr(uid, "list_header", name=name, lang=lang_name, n=count),
            reply_markup=booklist_inline(subject_code, lang, 0, uid)
        )
    await callback.answer()

@dp.callback_query(lambda c: c.data and c.data.startswith("bp_"))
async def bookpage_handler(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    subject_code = parts[1]
    lang = parts[2]
    page = int(parts[3])
    name = SUBJECT_NAMES.get(subject_code, "📚 Другое")
    lang_name = {"rus": "🇷🇺 Русский", "kaz": "🇰🇿 Қазақша", "eng": "🇬🇧 English"}.get(lang, lang)
    count = len(_list_entries(subject_code, lang))
    uid = callback.from_user.id
    try:
        await callback.message.edit_caption(
            caption=tr(uid, "list_header", name=name, lang=lang_name, n=count),
            reply_markup=booklist_inline(subject_code, lang, page, uid)
        )
    except:
        await callback.message.edit_text(
            text=tr(uid, "list_header", name=name, lang=lang_name, n=count),
            reply_markup=booklist_inline(subject_code, lang, page, uid)
        )
    await callback.answer()

@dp.callback_query(lambda c: c.data and c.data.startswith(("bk_", "bm_")))
async def bookopen_handler(callback: types.CallbackQuery):
    """bk_<предмет>_<язык>_<индекс> — из свежих списков; bm_<message_id> — из избранного и истории
    (не ломается после /update_books и /sort_other, когда индексы книг сдвигаются)."""
    try:
        parts = callback.data.split("_")
        if parts[0] == "bm":
            loc = _find_by_message_id(int(parts[1]))
            if not loc:
                raise KeyError("book moved")
            subject_code, lang, idx = loc
        else:
            subject_code, lang, idx = parts[1], parts[2], int(parts[3])
    except (ValueError, IndexError, KeyError):
        await callback.answer(tr(callback.from_user.id, "book_nf_alert"), show_alert=True)
        return
    books_list = BOOKS_DB.get(subject_code, {}).get(lang, [])
    if idx >= len(books_list):
        await callback.answer(tr(callback.from_user.id, "book_nf_alert"), show_alert=True)
        return
    book = books_list[idx]
    # Том многотомной книги: открываем всю серию одной карточкой (избранное, история, популярное)
    series = series_info(book.get("message_id"))
    if series:
        await _send_series_card(callback, series)
        return
    name = book["file_name"].replace(".pdf","").replace(".djvu","").replace("_"," ")
    lang_name = {"rus": "🇷🇺 Русский", "kaz": "🇰🇿 Қазақша", "eng": "🇬🇧 English"}.get(lang, lang)
    subject_name = SUBJECT_NAMES.get(subject_code, "📚 Другое")
    caption = (
        f"╔══════════════════════╗\n"
        f"  📖 {name[:40]}\n"
        f"╚══════════════════════╝\n\n"
        f"📚 {tr(callback.from_user.id, 'card_subject')} {subject_name}\n"
        f"🌐 {tr(callback.from_user.id, 'card_lang')} {lang_name}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 @library_adasan"
    )
    keyboard = book_card_keyboard(subject_code, lang, idx, book["url"], callback.from_user.id)
    sent = False
    cover_id = book.get("photo_message_id")
    source_chat = f"@{CHANNEL.lstrip('@')}"
    if cover_id:
        # Сначала копируем обложку с карточкой. Если Telegram не разрешит копирование,
        # пробуем переслать исходное фото отдельным сообщением.
        try:
            await bot.copy_message(
                chat_id=callback.message.chat.id,
                from_chat_id=source_chat,
                message_id=int(cover_id),
                caption=caption,
                reply_markup=keyboard,
            )
            sent = True
        except Exception as e:
            logger.warning(f"Обложка не скопировалась (пост {cover_id}): {e}")
            try:
                await bot.forward_message(
                    chat_id=callback.message.chat.id,
                    from_chat_id=source_chat,
                    message_id=int(cover_id),
                )
                await bot.send_message(
                    chat_id=callback.message.chat.id,
                    text=caption,
                    reply_markup=keyboard,
                )
                sent = True
            except Exception as forward_error:
                logger.warning(f"Обложка не переслалась (пост {cover_id}): {forward_error}")
    if not sent:
        # Не показываем тематическую иллюстрацию как будто это обложка книги.
        # Если настоящий снимок недоступен, отправляем исходный пост с книгой.
        try:
            await bot.copy_message(
                chat_id=callback.message.chat.id,
                from_chat_id=source_chat,
                message_id=int(book["message_id"]),
                caption=caption,
                reply_markup=keyboard,
            )
            sent = True
        except Exception as e:
            logger.warning(f"Пост книги не скопировался ({book.get('message_id')}): {e}")
    if not sent:
        await bot.send_message(
            chat_id=callback.message.chat.id,
            text=caption,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📥 Жүктеу / Скачать", url=book["url"])],
                [InlineKeyboardButton(text="⬅ Артқа / Назад / Back", callback_data=f"bl_{subject_code}_{lang}")],
            ]),
        )
    # Сохраняем в историю
    book_name_short = name[:50]
    add_book_history(callback.from_user.id, subject_code, lang, idx, book_name_short, book["url"])
    record_book_open(book["url"], book_name_short, subject_code, lang)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()

# =========================
# CALLBACK — Избранное
# =========================
@dp.callback_query(lambda c: c.data and c.data.startswith("fav_add_"))
async def fav_add_handler(callback: types.CallbackQuery):
    try:
        subject_code, lang, idx_raw = callback.data.replace("fav_add_", "").split("_")
        idx = int(idx_raw)
    except ValueError:
        await callback.answer(tr(callback.from_user.id, "book_nf_alert"), show_alert=True)
        return
    db_books = BOOKS_DB.get(subject_code, {}).get(lang, [])
    if idx >= len(db_books):
        await callback.answer(tr(callback.from_user.id, "book_nf_alert"), show_alert=True)
        return
    book = db_books[idx]
    book_name = book["file_name"].replace(".pdf","").replace(".djvu","").replace("_"," ")[:50]
    book_url = book["url"]
    added = add_favorite(callback.from_user.id, subject_code, lang, idx, book_name, book_url)
    if added:
        await callback.answer(tr(callback.from_user.id, "fav_added"), show_alert=True)
    else:
        await callback.answer(tr(callback.from_user.id, "fav_exists"), show_alert=True)

# =========================
# КНОПКИ НИЖНЕЙ КЛАВИАТУРЫ
# =========================
@dp.message(is_button("history"))
async def history_button(message: types.Message):
    history = get_book_history(message.from_user.id, limit=10)
    if not history:
        await message.answer(
            "📖 История пуста\n\nАшқан кітаптарыңыз осында көрінеді.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [menu_button()]
            ])
        )
        return
    rows = []
    for sc, lg, bi, bn, bu, opened_at in history:
        date_str = opened_at[:10] if opened_at else ""
        flag = {"rus": "🇷🇺", "kaz": "🇰🇿", "eng": "🇬🇧"}.get(lg, "📖")
        rows.append([InlineKeyboardButton(
            text=f"{flag} {bn[:28]} ({date_str})",
            callback_data=f"bm_{_mid_from_url(bu)}"
        )])
    rows.append([menu_button()])
    await message.answer(
        f"📖 Соңғы {len(history)} кітап / Последние {len(history)} книг:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )

@dp.message(lambda m: m.text and m.text.lower() in SUBJECTS)
async def open_subject(message: types.Message):
    code = SUBJECTS[message.text.lower()]
    await send_subject_menu(message.chat.id, code)

@dp.message(is_button("legacy_subjects"))
async def all_subjects_button(message: types.Message):
    """Кнопку «Все предметы» убрали из клавиатуры, но у части пользователей она ещё висит:
    показываем каталог и сразу подсовываем обновлённую клавиатуру."""
    await send_catalog(message)
    await message.answer(
        "🔄 Мәзір жаңартылды / Меню обновлено 👇",
        reply_markup=main_menu_keyboard(get_lang(message.from_user.id))
    )

@dp.message(Command("history"))
async def history_command(message: types.Message):
    history = get_book_history(message.from_user.id, limit=10)
    if not history:
        await message.answer(
            "📖 История пуста\n\nАшқан кітаптарыңыз осында көрінеді.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [menu_button()]
            ])
        )
        return
    rows = []
    for sc, lg, bi, bn, bu, opened_at in history:
        date_str = opened_at[:10] if opened_at else ""
        flag = {"rus": "🇷🇺", "kaz": "🇰🇿", "eng": "🇬🇧"}.get(lg, "📖")
        rows.append([InlineKeyboardButton(
            text=f"{flag} {bn[:28]} ({date_str})",
            callback_data=f"bm_{_mid_from_url(bu)}"
        )])
    rows.append([menu_button()])
    await message.answer(
        f"📖 Соңғы {len(history)} кітап / Последние {len(history)} книг:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )
