"""Точка входа: подключает модули обработчиков и запускает бота (python main.py)."""

import asyncio
import os

from admin_tools import apply_helper_commands
from backup import auto_restore_if_fresh, backup_loop, make_backup
from core import ADMIN_ID, bot, dp, logger
from database import compact_stats, helper_ids, prune_misses
from keyboards import BOT_INFO

# Модули с обработчиками подключаются В ЭТОМ ПОРЯДКЕ: aiogram отдаёт сообщение первому подошедшему обработчику.
import middlewares  # noqa: F401
import handlers_user  # noqa: F401
import handlers_admin  # noqa: F401
import handlers_catalog  # noqa: F401
import handlers_library  # noqa: F401
import handlers_top5  # noqa: F401
import handlers_backup  # noqa: F401
import handlers_extra  # noqa: F401   — профиль, случайная книга, отзыв, inline; ДО поиска
import handlers_search  # noqa: F401


# =========================
# ФОНОВОЕ СЖАТИЕ СТАТИСТИКИ
# =========================
async def stats_compaction_loop():
    """При запуске и далее раз в сутки сворачивает старые поиски в архив (счётчики не меняются)."""
    while True:
        try:
            moved = await asyncio.to_thread(compact_stats)
            if moved:
                logger.info(f"Статистика: свёрнуто {moved} старых строк в архив")
            await asyncio.to_thread(prune_misses)        # заодно чистим старые ненайденные запросы
        except Exception as e:
            logger.warning(f"Не удалось сжать статистику: {e}")
        await asyncio.sleep(24 * 3600)

# =========================
# MAIN
# =========================
async def main():
    from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat

    # Меню команд (кнопка «/» в Telegram). Админ видит те же команды + свои.
    user_commands = [
        BotCommand(command="start",     description="🚀 Бастау / Начало / Start"),
        BotCommand(command="menu",      description="🏠 Басты мәзір / Главное меню"),
        BotCommand(command="popular",   description="🔥 Танымал / Популярное"),
        BotCommand(command="random",    description="🎲 Кездейсоқ кітап / Случайная книга"),
        BotCommand(command="favorites", description="⭐ Таңдаулылар / Избранное"),
        BotCommand(command="history",   description="📖 Тарих / История"),
        BotCommand(command="profile",   description="👤 Профиль"),
        BotCommand(command="top5",      description="🏆 Топ-5 кітап / книг"),
        BotCommand(command="catalog",   description="📂 Барлық бөлімдер / Все разделы"),
        BotCommand(command="upload",    description="📤 Материал жіберу / Отправить материал"),
        BotCommand(command="feedback",  description="💬 Админге жазу / Написать админу"),
        BotCommand(command="lang",      description="🌐 Тіл / Язык / Language"),
        BotCommand(command="help",      description="ℹ️ Көмек / Помощь / Help"),
    ]
    admin_commands = user_commands + [
        BotCommand(command="top5_set",     description="🏆 Задать топ-5 предмета"),
        BotCommand(command="stats",        description="📊 Статистика"),
        BotCommand(command="users",        description="👥 Список пользователей"),
        BotCommand(command="admin",        description="🛠 Админ-панель (кнопки)"),
        BotCommand(command="update_books", description="🔄 Кітаптарды жаңарту"),
        BotCommand(command="sort_other",   description="📦 Разобрать other"),
        BotCommand(command="backup",       description="💾 Резервная копия сейчас"),
        BotCommand(command="broadcast",    description="📢 Рассылка"),
        BotCommand(command="missing",      description="🔎 Что ищут и не находят"),
        BotCommand(command="compact",      description="🧹 Сжать старую статистику"),
    ]
    # Узнаём имя бота и включён ли inline-режим (для кнопок «Поделиться» и «Искать в любом чате»)
    try:
        me = await bot.get_me()
        BOT_INFO["username"] = me.username or ""
        BOT_INFO["inline"] = bool(me.supports_inline_queries)
        if not BOT_INFO["inline"]:
            logger.info("Inline-режим выключен. Включите в @BotFather: /setinline — появятся «Поделиться» и поиск в любом чате.")
    except Exception as e:
        logger.warning(f"get_me не удался: {e}")

    await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())
    await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=ADMIN_ID))

    for _uid in helper_ids():
        await apply_helper_commands(_uid)

    # Мини-веб-сервер: Render (Web Service) требует открытый порт
    from aiohttp import web
    async def _health(request):
        return web.Response(text="OK")
    _app = web.Application()
    _app.router.add_get("/", _health)
    _runner = web.AppRunner(_app)
    await _runner.setup()
    await web.TCPSite(_runner, "0.0.0.0", int(os.getenv("PORT", "10000"))).start()

    await auto_restore_if_fresh()          # диск обнулился после деплоя? — достаём закреплённую копию
    backup_task = asyncio.create_task(backup_loop())
    compact_task = asyncio.create_task(stats_compaction_loop())

    logger.info("✅ Бот запущен!")
    try:
        # chat_member по умолчанию Telegram НЕ присылает — запрашиваем явно
        await dp.start_polling(
            bot,
            allowed_updates=list(set(dp.resolve_used_update_types()) | {"chat_member"}),
            close_bot_session=False,
        )
    finally:
        backup_task.cancel()
        compact_task.cancel()
        try:                                # последняя копия перед остановкой (деплой/перезапуск)
            await asyncio.wait_for(make_backup(), timeout=20)
        except Exception as e:
            logger.warning(f"Копия при остановке не отправлена: {e}")
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
