"""Поиск книг по тексту. Обработчик БЕЗ фильтра — ловит любое сообщение, которое не поймал никто выше,
поэтому этот модуль всегда подключается ПОСЛЕДНИМ."""

from aiogram import F, types
from aiogram.types import InlineKeyboardButton
from aiogram.types import InlineKeyboardMarkup

from book_cards import SEARCH_GROUPS_LIMIT, group_button, search_book_groups, send_subject_menu
from core import ADMIN_ID, ADMIN_NAME, ADMIN_URL, bot, dp
from database import ban_user, is_staff, log_stat, record_miss, set_wish
from middlewares import find_profanity, spam_tracker
from search_engine import find_subject_fuzzy
from subjects import SUBJECTS, _norm_q
from texts import tr
from keyboards import menu_button


# =========================
# ПОИСК КНИГ ПО ТЕКСТУ
# Обработчик без фильтра: ловит ЛЮБОЕ сообщение, которое не поймал никто выше.
# Поэтому он должен быть зарегистрирован ПОСЛЕДНИМ — иначе он перехватывает команды ниже него.
# =========================
@dp.message()
async def search(message: types.Message):
    if not message.from_user or not message.text:
        return
    text = message.text.strip()
    if len(text) > 200:
        await message.answer("🔎 Слишком длинный запрос. Напишите название короче (до 200 символов).")
        return
    user_id = message.from_user.id

    # Игнорируем неизвестные команды (начинаются с /)
    if text.startswith("/"):
        return

    # Reply-кнопки предметов могут приходить на любом из трёх языков.
    normalized_button = _norm_q(text)
    for button_text, code in SUBJECTS.items():
        if _norm_q(button_text) == normalized_button:
            log_stat(message.from_user.id, code, text)
            await send_subject_menu(message.chat.id, code)
            return

    # =============================
    # АВТОБАН ЗА МАТЫ
    # =============================
    mat = find_profanity(text) if not is_staff(user_id) else None
    if mat:
        ban_user(message.from_user.id, f"Автобан: мат ({mat})")
        spam_tracker.pop(message.from_user.id, None)
        await message.answer(
            "🚫 Сіз бұғатталдыңыз / Вы заблокированы за нецензурную лексику.\n\n"
            "Егер қате болса:\n"
            "Если это ошибка, обратитесь:\n\n"
            "👉 @Tg_Adasan"
        )
        try:
            await bot.send_message(
                ADMIN_ID,
                f"⚠️ Автобан за мат!\n\n"
                f"👤 {message.from_user.first_name}\n"
                f"🆔 ID: {message.from_user.id}\n"
                f"@{message.from_user.username or 'нет username'}\n\n"
                f"💬 Написал: {text[:100]}\n"
                f"📝 Мат: {mat}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔓 Разбанить", callback_data=f"unban_{message.from_user.id}")]
                ])
            )
        except Exception:
            pass
        return
    # =============================

    # 1. Ищем предмет
    subject_code = find_subject_fuzzy(text)
    if subject_code:
        log_stat(message.from_user.id, subject_code, text)
        await send_subject_menu(message.chat.id, subject_code)
        return

    # 3. Поиск в books_db.json: точные совпадения + русские/английские варианты + fuzzy-поиск.
    #    Тома одной серии объединяются в одну кнопку.
    total_found, groups, is_fuzzy = await search_book_groups(text, SEARCH_GROUPS_LIMIT)

    if groups:
        keyboard_rows = [[group_button(message.from_user.id, g)] for g in groups]
        if is_fuzzy:
            head = tr(message.from_user.id, "fuzzy_head")
        else:
            head = tr(message.from_user.id, "found_n", n=total_found, k=len(groups))
        await message.answer(
            f"{head}\n\n{tr(message.from_user.id, 'choose')}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
        )
        return

    # 4. Ничего не найдено — запоминаем запрос (админ видит, чего не хватает) и предлагаем уведомить о появлении
    miss_id = None if is_staff(user_id) else record_miss(user_id, text)
    rows = []
    if miss_id:
        rows.append([InlineKeyboardButton(text=tr(user_id, "wish_btn"), callback_data=f"wish_{miss_id}")])
    rows.append([InlineKeyboardButton(text=tr(user_id, "btn_admin"), url=ADMIN_URL)])
    rows.append([menu_button()])
    await message.answer(
        tr(user_id, "not_found", admin=ADMIN_NAME),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )

@dp.callback_query(F.data.startswith("wish_"))
async def wish_callback(callback: types.CallbackQuery):
    """«🔔 Сообщить, когда появится»: запоминаем желание, кнопку убираем."""
    uid = callback.from_user.id
    try:
        miss_id = int(callback.data[5:])
    except ValueError:
        await callback.answer()
        return
    result = set_wish(uid, miss_id)
    await callback.answer(tr(uid, f"wish_{result}"), show_alert=(result != "ok"))
    if result == "ok" and callback.message and callback.message.reply_markup:
        rows = [r for r in callback.message.reply_markup.inline_keyboard
                if not any((b.callback_data or "").startswith("wish_") for b in r)]
        try:
            await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
        except Exception:
            pass
