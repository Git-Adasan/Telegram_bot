"""Обработчики каталога (/catalog)."""

from aiogram import types
from aiogram.filters import Command

from catalog import CATALOG_TEXT, catalog_keyboard, send_catalog
from core import bot, dp


@dp.message(Command("catalog"))
async def catalog_command(message: types.Message):
    await send_catalog(message)

@dp.callback_query(lambda c: c.data == "catalog_open")
async def catalog_open_callback(callback: types.CallbackQuery):
    await bot.send_message(callback.message.chat.id, CATALOG_TEXT, reply_markup=catalog_keyboard())
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()
