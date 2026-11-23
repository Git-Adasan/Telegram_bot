"""Обработчики /top5 и команд владельца для настройки топ-5."""

import json as _json
from aiogram import types
from aiogram.filters import Command

from core import bot, dp
from series import series_info
from top5 import TOP5_MAX, _top5_admin_guard, _top5_help, _top5_mid, _top5_show_menu, _top5_subject, load_top5, save_top5, top5_card


@dp.message(Command("top5"))
async def top5_command(message: types.Message):
    await _top5_show_menu(message.chat.id)

@dp.callback_query(lambda c: c.data and c.data.startswith("t5_"))
async def top5_callback(callback: types.CallbackQuery):
    code = callback.data[3:]
    chat_id = callback.message.chat.id
    if code == "menu":
        await _top5_show_menu(chat_id)
    else:
        card = top5_card(code)
        if not card:
            await callback.answer("Список пока пуст", show_alert=True)
            return
        await bot.send_message(chat_id, card[0], reply_markup=card[1])
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()

@dp.message(Command("top5_set"))
async def top5_set_command(message: types.Message):
    if not _top5_admin_guard(message):
        await message.answer("❌ Рұқсат жоқ!"); return
    parts = (message.text or "").split()
    if len(parts) < 3:
        await message.answer(_top5_help()); return
    code = _top5_subject(parts[1])
    if not code:
        await message.answer(f"❌ Не нашёл предмет «{parts[1]}». Напишите код или слово, например: гистология"); return
    data, old = load_top5(), {i.get("mid"): i.get("video") for i in (load_top5().get(code) or [])}
    items, seen, bad = [], set(), []
    for tok in parts[2:]:
        mid = _top5_mid(tok)
        if not mid:
            bad.append(tok); continue
        info = series_info(mid)
        key = info["id"] if info else mid
        if key in seen:
            continue
        seen.add(key)
        item = {"mid": mid}
        if old.get(mid):
            item["video"] = old[mid]                 # видео не теряется при пересборке списка
        items.append(item)
    if bad:
        await message.answer("❌ Не нашёл книги: " + ", ".join(bad) + "\nСписок НЕ изменён."); return
    if not items:
        await message.answer("❌ Нет ни одной книги."); return
    data[code] = items[:TOP5_MAX]
    save_top5(data)
    card = top5_card(code)
    note = "\n(оставил первые 5)" if len(items) > TOP5_MAX else ""
    await message.answer(f"✅ Сохранено.{note}")
    if card:
        await message.answer(card[0], reply_markup=card[1])

@dp.message(Command("top5_video"))
async def top5_video_command(message: types.Message):
    if not _top5_admin_guard(message):
        await message.answer("❌ Рұқсат жоқ!"); return
    parts = (message.text or "").split()
    if len(parts) != 4:
        await message.answer("Формат: /top5_video <предмет> <номер 1-5> <ссылка на видео или ->"); return
    code, data = _top5_subject(parts[1]), load_top5()
    items = data.get(code) if code else None
    if not items or not parts[2].isdigit() or not (1 <= int(parts[2]) <= len(items)):
        await message.answer("❌ Проверьте предмет и номер книги в списке."); return
    link = parts[3]
    if link == "-":
        items[int(parts[2]) - 1].pop("video", None)
    elif link.startswith(("http://", "https://")):
        items[int(parts[2]) - 1]["video"] = link
    else:
        await message.answer("❌ Ссылка должна начинаться с http:// или https://"); return
    save_top5(data)
    await message.answer("✅ Готово. Проверьте: /top5")

@dp.message(Command("top5_del"))
async def top5_del_command(message: types.Message):
    if not _top5_admin_guard(message):
        await message.answer("❌ Рұқсат жоқ!"); return
    parts = (message.text or "").split()
    code, data = (_top5_subject(parts[1]) if len(parts) > 1 else None), load_top5()
    if not code or code not in data:
        await message.answer("Формат: /top5_del <предмет> [номер]"); return
    if len(parts) > 2 and parts[2].isdigit() and 1 <= int(parts[2]) <= len(data[code]):
        data[code].pop(int(parts[2]) - 1)
        if not data[code]:
            del data[code]
    elif len(parts) == 2:
        del data[code]
    else:
        await message.answer("❌ Неверный номер."); return
    save_top5(data)
    await message.answer("✅ Удалено.")

@dp.message(Command("top5_export"))
async def top5_export_command(message: types.Message):
    if not _top5_admin_guard(message):
        await message.answer("❌ Рұқсат жоқ!"); return
    raw = _json.dumps(load_top5(), ensure_ascii=False, indent=2).encode("utf-8")
    await message.answer_document(types.BufferedInputFile(raw, filename="top5.json"),
                                  caption="Положите файл в корень проекта и сделайте git commit + push.")
