"""«Сообщить, когда появится»: после обновления базы книг пишем тем, кто искал книгу, которой раньше не было.
Без обработчиков — вызывается из /update_books."""

import asyncio

from aiogram.types import InlineKeyboardMarkup

from admin_tools import send_broadcast_one
from book_cards import group_button, search_book_groups
from core import logger
from database import pending_wishes, resolve_miss
from keyboards import menu_button
from texts import tr

WISH_RESULTS_SHOWN = 5      # сколько найденных книг показываем в уведомлении


async def notify_wishes():
    """Для каждого ожидаемого запроса повторяет поиск. Нашлось ТОЧНОЕ совпадение — уведомляем всех ждущих
    и закрываем запрос; похожие «может, вы искали» не считаются (иначе пришлёт случайную книгу).
    Возвращает (сколько запросов закрыто, сколько людей уведомлено)."""
    closed = notified = 0
    for miss_id, sample, user_ids in pending_wishes():
        try:
            _total, groups, is_fuzzy = await search_book_groups(sample, WISH_RESULTS_SHOWN)
        except Exception as e:
            logger.warning(f"Повторный поиск «{sample}» не удался: {e}")
            continue
        if not groups or is_fuzzy:
            continue
        for uid in user_ids:
            rows = [[group_button(uid, g)] for g in groups] + [[menu_button()]]
            status = await send_broadcast_one(
                uid, tr(uid, "wish_found", q=sample), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
            if status == "sent":
                notified += 1
            await asyncio.sleep(0.05)               # не упираемся в лимиты Telegram
        resolve_miss(miss_id)
        closed += 1
    return closed, notified
