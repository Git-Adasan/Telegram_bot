"""Обработчики /backup и /restore."""

from aiogram import types
from aiogram.filters import Command

from backup import _restore_command_impl, make_backup
from core import ADMIN_ID, dp


@dp.message(Command("backup"))
async def backup_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Рұқсат жоқ!"); return
    try:
        sent = await make_backup(force=True)
    except Exception as e:
        await message.answer(f"❌ Не удалось: {e}"); return
    await message.answer("✅ Копия отправлена и закреплена." if sent else
                         "ℹ️ В базе пока нет данных — копировать нечего.")

@dp.message(Command("restore"))
async def restore_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Рұқсат жоқ!"); return
    await _restore_command_impl(message, message.reply_to_message.document if message.reply_to_message else None)

@dp.message(lambda m: m.document is not None and m.from_user and m.from_user.id == ADMIN_ID
            and (m.caption or "").strip().startswith("/restore"))
async def restore_document(message: types.Message):
    await _restore_command_impl(message, message.document)
