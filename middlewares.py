"""Доступ и защита: бан, антифлуд, мат-фильтр, проверка подписки на канал (в т.ч. события chat_member).
Подключается первым — middleware действуют на все обработчики."""

import re
import time
from aiogram import BaseMiddleware
from aiogram import types
from aiogram.types import TelegramObject
from collections import defaultdict
from typing import Any
from typing import Callable

from core import bot, dp, logger
from database import _sub_db_get, _sub_db_set, clear_bot_blocked, is_banned, is_staff, mark_bot_blocked
from keyboards import subscribe_keyboard


_last_message_time = defaultdict(float)

_last_callback_time = defaultdict(float)

# Раньше было 5 сек для сообщений и 2 сек для кнопок: человек нажимал две кнопки подряд,
# и вторая молча терялась — казалось, что бот «завис». Теперь защищаемся только от настоящего спама.
FLOOD_MESSAGE_SECONDS = 1.0
FLOOD_CALLBACK_SECONDS = 0.6

def _prune(d):
    if len(d) > 20000:                 # не даём словарям расти бесконечно
        cutoff = time.time() - 60
        for k in [k for k, v in d.items() if v < cutoff]:
            del d[k]

def is_flood(user_id: int) -> bool:
    now = time.time()
    _prune(_last_message_time)
    if now - _last_message_time[user_id] < FLOOD_MESSAGE_SECONDS:
        return True
    _last_message_time[user_id] = now
    return False

def is_flood_callback(user_id: int) -> bool:
    now = time.time()
    _prune(_last_callback_time)
    if now - _last_callback_time[user_id] < FLOOD_CALLBACK_SECONDS:
        return True
    _last_callback_time[user_id] = now
    return False

# =========================
# MIDDLEWARE — бан + флуд
# =========================
class BanAndFloodMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable, event: TelegramObject, data: dict) -> Any:
        user = getattr(event, 'from_user', None)
        if not user:
            return await handler(event, data)
        user_id = user.id
        # Бан — полное молчание
        if is_banned(user_id):
            # Для callback закрываем spinner
            if hasattr(event, 'answer') and hasattr(event, 'data'):
                try:
                    await event.answer()
                except Exception:
                    pass
            return
        if is_staff(user_id):
            return await handler(event, data)
        # Флуд
        if hasattr(event, 'data'):  # callback
            if is_flood_callback(user_id):
                try:
                    await event.answer()
                except Exception:
                    pass
                return
        else:  # message
            if not getattr(event, "document", None) and is_flood(user_id):
                return
        return await handler(event, data)

dp.message.middleware(BanAndFloodMiddleware())

dp.callback_query.middleware(BanAndFloodMiddleware())

# Антиспам трекер
spam_tracker = {}  # {user_id: [datetime, ...]}

# Список матов (русский + казахский)
MAT_WORDS = [
    "блять", "бля", "сука", "пизд", "ёбан", "ебан", "еба", "ёба",
    "хуй", "хуе", "хуи", "пизд", "пиздо", "пизда", "мразь", "залупа",
    "шлюха", "шлюх", "ублюдок", "ублюд", "мудак", "мудил", "пидор",
    "пидар", "гондон", "гнида", "тварь", "выблядок", "выеб",
    "ахуе", "охуе", "нахуй", "пошел нахуй", "иди нахуй",
    "шайтан", "нокта", "сорай кет", "ит",
]

# Мат ищем по целым словам: короткие слова — только точное совпадение,
# длинные корни — по началу слова. Раньше проверялось «слово внутри текста»,
# и «ит» банило за «цитология», «лейкоцит», «Литвицкий», а «бля» — за «бляшка».
_MAT_EXACT = {
    "бля", "блять", "блядь", "сука", "суки", "ит", "тварь", "мразь", "гнида", "нокта",
    "шайтан", "еба", "залупа", "шлюха", "мудак", "ублюдок", "гондон", "пидор", "пидар",
    "выблядок",
}

_MAT_PREFIX = (
    "пизд", "ебан", "хуй", "хуе", "хуи", "нахуй", "ахуе", "охуе", "выеб",
    "мудил", "ублюд", "шлюх", "бляд", "пидор", "пидар",
)

def find_profanity(text):
    t = text.lower().replace("ё", "е")
    words = re.findall(r"\w+", t)
    for w in words:
        if w in _MAT_EXACT or w.startswith(_MAT_PREFIX):
            return w
    if "сорай кет" in t:
        return "сорай кет"
    return None

CHANNEL_USERNAME = "@library_adasan"

# Подписка хранится в таблице channel_subs и обновляется событиями chat_member
# (Telegram сам сообщает боту, когда кто-то вступил в канал или вышел).
# К Telegram (get_chat_member) бот обращается только если:
#   • человека нет в таблице (его вступление бот не видел);
#   • запись «подписан» старше SUB_RECHECK_SECONDS (вдруг бот был выключен и пропустил выход);
#   • человек нажал кнопку «Подписался» (force=True).
SUB_RECHECK_SECONDS = 24 * 3600

async def check_subscription(user_id, force=False):
    """True — подписан (или проверить не удалось). Сначала смотрим в свою таблицу."""
    if not force:
        rec = _sub_db_get(user_id)
        if rec is not None:
            is_member, updated_at = rec
            if not is_member:
                return False                                   # вышел — не спрашиваем Telegram
            if time.time() - updated_at < SUB_RECHECK_SECONDS:
                return True                                    # подписан, запись свежая
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        if member.status == "restricted":
            ok = bool(getattr(member, "is_member", True))
        else:
            ok = member.status not in ["left", "kicked", "banned"]
    except Exception as e:
        # Бот должен быть АДМИНОМ канала, иначе Telegram не даёт проверить подписку.
        # Чтобы не заблокировать всех из-за сбоя — пропускаем, но пишем в лог.
        logger.warning(f"Проверка подписки не удалась (бот админ канала?): {e}")
        return True
    _sub_db_set(user_id, ok)
    return ok

class SubscriptionMiddleware(BaseMiddleware):
    """Не пускает в бота (в личке) тех, кто не подписан на канал."""
    async def __call__(self, handler: Callable, event: TelegramObject, data: dict) -> Any:
        user = getattr(event, "from_user", None)
        is_callback = hasattr(event, "data")
        chat = (event.message.chat if is_callback and event.message else getattr(event, "chat", None))

        # Пропускаем: нет пользователя, не личка, админ, /start, кнопка «Подписался»
        if (not user or not chat or chat.type != "private" or is_staff(user.id)
                or (not is_callback and (getattr(event, "text", "") or "").startswith("/start"))
                or (is_callback and event.data == "check_sub")):
            return await handler(event, data)

        if await check_subscription(user.id):
            return await handler(event, data)

        text = ("🔒 Ботты пайдалану үшін біздің каналға жазылу керек!\n"
                "Для использования бота нужно подписаться на канал.\n\n"
                "👇 Жазылып, «Жазылдым» батырмасын басыңыз / Подпишитесь и нажмите «Подписался»")
        try:
            if is_callback:
                await event.answer("🔒 Алдымен каналға жазылыңыз / Сначала подпишитесь на канал", show_alert=True)
                await bot.send_message(chat.id, text, reply_markup=subscribe_keyboard())
            else:
                await event.answer(text, reply_markup=subscribe_keyboard())
        except Exception as e:
            logger.warning(f"Не удалось отправить запрос подписки: {e}")
        return  # дальше в обработчики не пускаем

dp.message.middleware(SubscriptionMiddleware())

dp.callback_query.middleware(SubscriptionMiddleware())

@dp.chat_member()
async def on_channel_member_update(event: types.ChatMemberUpdated):
    """Telegram сообщает: кто-то вступил в канал или вышел — сразу пишем в таблицу."""
    if (event.chat.username or "").lower() != CHANNEL_USERNAME.lstrip("@").lower():
        return
    new = event.new_chat_member
    if new.status == "restricted":
        is_member = bool(getattr(new, "is_member", True))
    else:
        is_member = new.status in ("creator", "administrator", "member")
    try:
        _sub_db_set(new.user.id, is_member)
        logger.info(f"Канал: {new.user.id} {'вступил' if is_member else 'вышел'} ({new.status})")
    except Exception as e:
        logger.warning(f"Не удалось записать статус подписки: {e}")

@dp.my_chat_member()
async def on_bot_status_change(event: types.ChatMemberUpdated):
    """Человек заблокировал бота (kicked) или разблокировал (member) — запоминаем,
    чтобы рассылка не тратила время и лимиты Telegram на тех, кому не дойдёт."""
    if event.chat.type != "private":
        return                       # бота добавили/убрали в канале или группе — не про рассылку
    uid = event.from_user.id
    status = event.new_chat_member.status
    try:
        if status == "kicked":
            mark_bot_blocked(uid)
            logger.info(f"Бот заблокирован пользователем {uid}")
        elif status == "member":
            clear_bot_blocked(uid)
            logger.info(f"Бот разблокирован пользователем {uid}")
    except Exception as e:
        logger.warning(f"Не удалось записать блокировку бота: {e}")
