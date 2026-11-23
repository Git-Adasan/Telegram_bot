"""Вспомогательное для админ-панели: клавиатура, команды помощников, список банов."""

import asyncio

from aiogram import types
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton
from aiogram.types import InlineKeyboardMarkup
from aiogram.types import KeyboardButton
from aiogram.types import ReplyKeyboardMarkup

from core import bot, logger
from database import get_banned_list, helper_ids, mark_bot_blocked, resolve_user


async def send_broadcast_one(uid, text, max_retries=3, reply_markup=None):
    """Отправить одно сообщение рассылки. Возвращает "sent", "blocked" или "failed".

    * Telegram просит подождать (RetryAfter) — ждём указанное время и пробуем снова;
    * пользователь заблокировал бота / удалил аккаунт — помечаем, больше ему не шлём;
    * любая другая ошибка — считаем «не доставлено», пользователя не трогаем.
    """
    for attempt in range(max_retries + 1):
        try:
            if reply_markup is None:
                await bot.send_message(chat_id=uid, text=text)
            else:
                await bot.send_message(chat_id=uid, text=text, reply_markup=reply_markup)
            return "sent"
        except TelegramRetryAfter as e:
            if attempt == max_retries:
                return "failed"
            await asyncio.sleep(e.retry_after + 1)
        except TelegramForbiddenError:                      # бот заблокирован / пользователь удалён
            mark_bot_blocked(uid)
            return "blocked"
        except TelegramBadRequest as e:
            if "chat not found" in str(e).lower() or "deactivated" in str(e).lower():
                mark_bot_blocked(uid)
                return "blocked"
            return "failed"
        except Exception:
            return "failed"
    return "failed"


def admin_keyboard(user_id=None):
    rows = [
        [KeyboardButton(text="👥 Пользователи"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="🚫 Баны")],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

HELPER_COMMANDS = [
    ("start", "Начало / Бастау / Start"),
    ("admin", "🛠 Админ-панель"), ("stats", "📊 Статистика"), ("users", "👥 Список пользователей"),
    ("missing", "🔎 Что ищут и не находят"),
    ("ban", "🚫 Бан пользователя"), ("unban", "🔓 Разбан пользователя"), ("banlist", "📋 Список банов"),
]

async def apply_helper_commands(user_id):
    from aiogram.types import BotCommand, BotCommandScopeChat
    try:
        await bot.set_my_commands([BotCommand(command=c, description=d) for c, d in HELPER_COMMANDS],
                                  scope=BotCommandScopeChat(chat_id=user_id))
    except Exception as e:
        logger.warning(f"Не удалось задать команды помощнику {user_id}: {e}")

async def clear_helper_commands(user_id):
    from aiogram.types import BotCommandScopeChat
    try:
        await bot.delete_my_commands(scope=BotCommandScopeChat(chat_id=user_id))
    except Exception as e:
        logger.warning(f"Не удалось сбросить команды {user_id}: {e}")

async def _show_helpers(message: types.Message):
    ids = sorted(helper_ids())
    text = "🛡 <b>Помощники админа</b>\n\n👑 Владелец: вы\n"
    if not ids:
        text += "\nПомощников пока нет.\n"
    for uid in ids:
        _, name = resolve_user(str(uid))
        from html import escape
        text += f"• {escape(name or str(uid))} — id {uid}\n"
    text += ("\n➕ /addadmin @username или id\n➖ /removeadmin @username или id\n\n"
             "Помощник: /admin, /users, /stats, /ban, /unban, /banlist.\n"
             "Только владелец: рассылка, /update_books, /sort_other, назначение помощников.")
    await message.answer(text, parse_mode="HTML")

async def send_banlist(message: types.Message):
    banned = get_banned_list()
    if not banned:
        await message.answer("✅ Бұғатталған пайдаланушылар жоқ.")
        return
    text = f"🚫 Бұғатталғандар ({len(banned)}):\n\n"
    rows = []
    for uid, username, fname, banned_at, reason in banned:
        uname = f"@{username}" if username else f"id:{uid}"
        fname = fname or "?"
        date_str = banned_at[:10] if banned_at else "?"
        text += f"👤 {fname} ({uname})\n🆔 {uid}\n📅 {date_str}\n📝 {reason}\n\n"
        rows.append([InlineKeyboardButton(
            text=f"🔓 Разблокировать {fname[:15]}",
            callback_data=f"unban_{uid}"
        )])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
