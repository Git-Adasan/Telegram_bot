"""Обработчики: популярное, оценки, загрузка материалов, группы/обсуждения канала, серии книг."""

import asyncio
import html as _html
import time
from aiogram import F
from aiogram import types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton
from aiogram.types import InlineKeyboardMarkup

from buttons import is_button
from book_cards import GROUP_CHAT_COOLDOWN, GROUP_MAX_RESULTS, GROUP_MIN_SCORE, GROUP_USER_COOLDOWN, _group_chat_last, _group_user_last, _send_book_to_group, _send_series_card, _series_card_keyboard, book_card_keyboard
from books import BOOKS_DB, save_books_db
from core import ADMIN_ID, CHANNEL, bot, dp, logger
from database import add_book_history, add_submission, count_pending_by_user, get_lang, record_book_open, set_submission_status, set_vote
from keyboards import main_menu_keyboard, menu_button
from search_engine import fuzzy_find_books
from series import _plain_name, series_info
from subjects import SUBJECT_NAMES
from texts import tr, user_lang
from uploads import LANG_CAPTION, LANG_LABELS, MAX_PENDING_PER_USER, MAX_UPLOAD_BYTES, SUBJECT_HASHTAGS, UPLOAD_COOLDOWN_SECONDS, UPLOAD_EXT, _notify_user, _parse_sub, _upload_last_time, _upload_state, start_upload, submission_admin_kb
from views import send_popular


# ---------- Закладки убраны: ответ на старые кнопки в чатах ----------
@dp.message(lambda m: m.text and m.text.lower() == "📌 закладки")
async def legacy_bookmark_message(message: types.Message):
    # у части пользователей ещё висит старая клавиатура — обновляем её на новую
    await message.answer("📌 Закладки убрали. Меню обновлено 👇", reply_markup=main_menu_keyboard(get_lang(message.from_user.id)))

@dp.callback_query(lambda c: c.data and c.data.startswith(("bmark_", "bmdel_", "show_bookmarks")))
async def legacy_bookmark_callback(callback: types.CallbackQuery):
    await callback.answer("📌 Закладки убрали / Функция закладок удалена", show_alert=True)

@dp.message(Command("popular"))
async def popular_command(message: types.Message):
    await send_popular(message)

@dp.message(is_button("popular"))
async def popular_button(message: types.Message):
    await send_popular(message)

# ---------- Оценка 👍/👎 ----------
@dp.callback_query(lambda c: c.data and c.data.startswith("rate_"))
async def rate_handler(callback: types.CallbackQuery):
    try:
        direction, rest = callback.data[5:].split("_", 1)              # rate_up_… / rate_dn_…
        subject_code, lang, idx_raw = rest.rsplit("_", 2)
        idx = int(idx_raw)
        book = BOOKS_DB[subject_code][lang][idx]
    except (ValueError, KeyError, IndexError):
        await callback.answer(tr(callback.from_user.id, "book_nf_alert"), show_alert=True)
        return
    vote = 1 if direction == "up" else -1
    result = set_vote(callback.from_user.id, book["url"], vote)
    try:
        series = series_info(book.get("message_id"))
        updated_keyboard = (_series_card_keyboard(series, callback.from_user.id) if series
                            else book_card_keyboard(subject_code, lang, idx, book["url"], callback.from_user.id,
                                                    title=_plain_name(book.get("file_name", ""))))
        await callback.message.edit_reply_markup(reply_markup=updated_keyboard)
    except Exception as edit_error:
        logger.debug("Не удалось обновить кнопки оценки: %s", edit_error)
    if result == 0:
        await callback.answer({"kz": "Дауыс алынды", "ru": "Голос убран", "en": "Vote removed"}[user_lang(callback.from_user.id)])
    else:
        await callback.answer({"kz": "Рахмет! 🙌", "ru": "Спасибо! 🙌", "en": "Thanks! 🙌"}[user_lang(callback.from_user.id)])

@dp.message(Command("upload"))
async def upload_command(message: types.Message):
    await start_upload(message)

@dp.message(is_button("upload"))
async def upload_button(message: types.Message):
    await start_upload(message)

@dp.callback_query(lambda c: c.data == "upl_cancel")
async def upload_cancel(callback: types.CallbackQuery):
    _upload_state.discard(callback.from_user.id)
    try:
        await callback.message.edit_text("Жақсы, болдырмадық / Хорошо, отменили.")
    except Exception:
        pass
    await callback.answer()

@dp.message(lambda m: m.document is not None and m.chat.type == "private" and m.from_user and m.from_user.id in _upload_state)
async def receive_material(message: types.Message):
    uid = message.from_user.id
    doc = message.document
    now = time.monotonic()
    if now - _upload_last_time.get(uid, 0) < UPLOAD_COOLDOWN_SECONDS:
        await message.answer("⏳ Подождите немного перед следующей отправкой файла.")
        return
    _upload_last_time[uid] = now
    if doc.file_size is not None and doc.file_size > MAX_UPLOAD_BYTES:
        await message.answer(
            "⚠️ Файл слишком большой. Максимальный размер — 45 МБ."
        )
        return
    fname = doc.file_name or "material"
    if not fname.lower().endswith(UPLOAD_EXT):
        await message.answer(
            "⚠️ Бұл формат қолдау таппайды / Этот формат не подходит.\n"
            "PDF, DOC(X), PPT(X), TXT, EPUB, DJVU жіберіңіз."
        )
        return
    if count_pending_by_user(uid) >= MAX_PENDING_PER_USER:
        _upload_state.discard(uid)
        await message.answer(
            "⏳ Алдыңғы файлдарыңыз әлі тексерілуде. Сәл күте тұрыңыз.\n"
            "Ваши предыдущие файлы ещё на проверке. Подождите немного."
        )
        return
    sub_id = add_submission(uid, message.from_user.username, message.from_user.first_name, doc.file_id, fname)
    who = f"@{message.from_user.username}" if message.from_user.username else (message.from_user.first_name or "—")
    admin_caption = (
        f"📤 Жаңа материал / Новый материал #{sub_id}\n"
        f"👤 {_html.escape(who)} (ID {uid})\n"
        f"📄 {_html.escape(fname)}"
    )
    try:
        await bot.send_document(
            ADMIN_ID, doc.file_id, caption=admin_caption, parse_mode="HTML",
            reply_markup=submission_admin_kb(sub_id)
        )
    except Exception as e:
        logger.error(f"submission to admin failed: {e}")
        set_submission_status(sub_id, "error")
        await message.answer("❌ Қате шықты, кейінірек қайталап көріңіз / Ошибка, попробуйте позже.")
        return
    _upload_state.discard(uid)
    await message.answer(
        "✅ Рахмет! Файл админге тексеруге жіберілді.\n"
        "Спасибо! Файл отправлен админу на проверку.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [menu_button()]
        ])
    )

@dp.callback_query(lambda c: c.data and c.data.startswith("sbm_ok_"))
async def sbm_approve_start(callback: types.CallbackQuery):
    sub, _ = _parse_sub(callback, "sbm_ok_")
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Рұқсат жоқ!", show_alert=True)
        return
    if not sub or sub["status"] != "pending":
        await callback.answer("Бұл өтінім өңделген / Уже обработано", show_alert=True)
        return
    codes = list(SUBJECT_NAMES.keys())
    rows = []
    for i in range(0, len(codes), 2):
        rows.append([
            InlineKeyboardButton(text=SUBJECT_NAMES[c], callback_data=f"sbm_sj_{sub['id']}_{c}")
            for c in codes[i:i + 2]
        ])
    rows.append([InlineKeyboardButton(text="⬅ Назад", callback_data=f"sbm_back_{sub['id']}")])
    try:
        await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except Exception:
        pass
    await callback.answer("Пәнді таңдаңыз / Выберите предмет")

@dp.callback_query(lambda c: c.data and c.data.startswith("sbm_back_"))
async def sbm_back(callback: types.CallbackQuery):
    sub, _ = _parse_sub(callback, "sbm_back_")
    if not sub:
        await callback.answer()
        return
    try:
        await callback.message.edit_reply_markup(reply_markup=submission_admin_kb(sub["id"]))
    except Exception:
        pass
    await callback.answer()

@dp.callback_query(lambda c: c.data and c.data.startswith("sbm_sj_"))
async def sbm_pick_subject(callback: types.CallbackQuery):
    sub, rest = _parse_sub(callback, "sbm_sj_")
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Рұқсат жоқ!", show_alert=True)
        return
    if not sub or sub["status"] != "pending" or not rest or rest[0] not in SUBJECT_HASHTAGS:
        await callback.answer("Бұл өтінім өңделген / Уже обработано", show_alert=True)
        return
    code = rest[0]
    rows = [[InlineKeyboardButton(text=label, callback_data=f"sbm_lg_{sub['id']}_{code}_{lg}")]
            for lg, label in LANG_LABELS.items()]
    rows.append([InlineKeyboardButton(text="⬅ Назад", callback_data=f"sbm_ok_{sub['id']}")])
    try:
        await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except Exception:
        pass
    await callback.answer(SUBJECT_NAMES.get(code, code))

@dp.callback_query(lambda c: c.data and c.data.startswith("sbm_lg_"))
async def sbm_publish(callback: types.CallbackQuery):
    sub, rest = _parse_sub(callback, "sbm_lg_")
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Рұқсат жоқ!", show_alert=True)
        return
    if (not sub or sub["status"] != "pending" or not rest or len(rest) < 2
            or rest[0] not in SUBJECT_HASHTAGS or rest[1] not in LANG_CAPTION):
        await callback.answer("Бұл өтінім өңделген / Уже обработано", show_alert=True)
        return
    code, lang = rest[0], rest[1]
    display_name = sub["file_name"].rsplit(".", 1)[0].replace("_", " ")
    caption = (
        f"📖 {display_name}\n\n"
        f"{SUBJECT_HASHTAGS[code]}\n"
        f"🌐 {LANG_CAPTION[lang]}\n"
        f"📤 Студенттен / От студента"
    )
    try:
        msg = await bot.send_document(CHANNEL, sub["file_id"], caption=caption)
    except Exception as e:
        logger.error(f"publish to channel failed: {e}")
        await callback.answer(
            f"❌ Каналға жариялау мүмкін болмады: {str(e)[:120]}\n"
            "Бот каналда админ болуы керек (хабар жариялау құқығымен).",
            show_alert=True
        )
        return
    BOOKS_DB.setdefault(code, {"rus": [], "kaz": [], "eng": []}).setdefault(lang, []).append({
        "message_id": msg.message_id,
        "file_name": sub["file_name"],
        "caption": caption[:300],
        "url": f"https://t.me/{CHANNEL.lstrip('@')}/{msg.message_id}",
    })
    save_books_db()
    set_submission_status(sub["id"], "approved", code, lang)
    try:
        await callback.message.edit_caption(
            caption=f"✅ Қабылданды / Одобрено #{sub['id']}\n📄 {sub['file_name']}\n"
                    f"{SUBJECT_NAMES.get(code, code)} · {LANG_LABELS[lang]}",
            reply_markup=None
        )
    except Exception:
        pass
    await _notify_user(
        sub["user_id"],
        "🎉 Рахмет! Сіздің материалыңыз кітапханаға қосылды.\n"
        "Спасибо! Ваш материал добавлен в библиотеку."
    )
    await callback.answer("✅ Жарияланды")

@dp.callback_query(lambda c: c.data and c.data.startswith("sbm_no_"))
async def sbm_reject(callback: types.CallbackQuery):
    sub, _ = _parse_sub(callback, "sbm_no_")
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Рұқсат жоқ!", show_alert=True)
        return
    if not sub or sub["status"] != "pending":
        await callback.answer("Бұл өтінім өңделген / Уже обработано", show_alert=True)
        return
    set_submission_status(sub["id"], "rejected")
    try:
        await callback.message.edit_caption(
            caption=f"❌ Қайтарылды / Отклонено #{sub['id']}\n📄 {sub['file_name']}",
            reply_markup=None
        )
    except Exception:
        pass
    await _notify_user(
        sub["user_id"],
        "Рахмет, файлды жібергеніңіз үшін! Бұл жолы кітапханаға қоса алмадық, "
        "бірақ басқа материалдарыңызды жіберуге болады.\n\n"
        "Спасибо, что отправили файл! В этот раз мы не смогли добавить его в библиотеку, "
        "но вы можете присылать другие материалы."
    )
    await callback.answer("Қайтарылды")

@dp.message(F.chat.type.in_({"group", "supergroup"}), F.text)
async def group_book_search(message: types.Message):
    # Не отвечаем автопересылкам постов канала и другим ботам.
    # Исключение: сообщение «от имени канала/группы» (sender_chat) — Telegram показывает
    # отправителем служебного бота, но писал живой админ.
    if not message.from_user or message.is_automatic_forward:
        return
    if message.from_user.is_bot and not message.sender_chat:
        return
    text = (message.text or "").strip()
    if len(text) < 4 or len(text) > 100 or text.startswith("/"):
        logger.debug("GROUP message skipped (length/command)")
        return

    now = time.time()
    uid = message.sender_chat.id if message.sender_chat else message.from_user.id
    cid = message.chat.id
    if now - _group_user_last.get(uid, 0) < GROUP_USER_COOLDOWN:
        return
    if now - _group_chat_last.get(cid, 0) < GROUP_CHAT_COOLDOWN:
        return

    total, found = await asyncio.to_thread(fuzzy_find_books, text, GROUP_MAX_RESULTS + 1, GROUP_MIN_SCORE)
    logger.info("GROUP search completed; results=%d", total)
    # Ничего не нашли или запрос слишком общий («анатомия») — молчим, не мешаем чату
    if not found or total > GROUP_MAX_RESULTS:
        return

    _group_user_last[uid] = now
    _group_chat_last[cid] = now
    for sc, lang, idx, bk in found:
        if await _send_book_to_group(message, sc, lang, idx, bk):
            try:
                nm = bk["file_name"].replace(".pdf", "").replace(".djvu", "").replace("_", " ")[:50]
                record_book_open(bk["url"], nm, sc, lang)
                if not message.sender_chat:
                    add_book_history(uid, sc, lang, idx, nm, bk["url"])
            except Exception:
                pass

@dp.message(lambda m: m.photo)
async def get_file_id(message: types.Message):
    if (not message.from_user or message.from_user.id != ADMIN_ID
            or message.chat.type != "private"):
        return
    file_id = message.photo[-1].file_id
    await message.answer(f"file_id:\n`{file_id}`", parse_mode="Markdown")

@dp.callback_query(lambda c: c.data and c.data.startswith("bg_"))
async def book_group_handler(callback: types.CallbackQuery):
    uid = callback.from_user.id
    try:
        _prefix, rest = callback.data.split("_", 1)
        sc, lang, idx = rest.rsplit("_", 2)
        base = BOOKS_DB[sc][lang][int(idx)]
    except (ValueError, KeyError, IndexError):
        await callback.answer(tr(uid, "book_nf_alert"), show_alert=True)
        return
    info = series_info(base.get("message_id"))
    if not info:
        await callback.answer(tr(uid, "book_nf_alert"), show_alert=True)
        return
    await _send_series_card(callback, info)
