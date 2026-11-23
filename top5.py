"""Топ-5 книг по предметам: хранение (top5.json), карточки, проверки."""

import json as _json
import os
import re
from aiogram.types import InlineKeyboardButton
from aiogram.types import InlineKeyboardMarkup

from books import BOOKS_DB, _find_by_message_id
from core import ADMIN_ID, BASE_DIR, bot
from series import _plain_name, series_info
from subjects import SUBJECT_NAMES, find_subject
from keyboards import menu_button


# =========================
# 🏆 ТОП-5 КНИГ ПО ПРЕДМЕТАМ
# Список выбирает владелец, под каждой книгой — кнопка со ссылкой на его видео.
# Хранится в top5.json:  {"gistologiya": [{"mid": 123, "video": "https://..."}, ...]}
# =========================
TOP5_PATH = os.path.join(BASE_DIR, "top5.json")

TOP5_MAX = 5

_LANG_FLAG = {"rus": "🇷🇺", "kaz": "🇰🇿", "eng": "🇬🇧"}

def load_top5():
    try:
        with open(TOP5_PATH, encoding="utf-8") as f:
            data = _json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}

def save_top5(data):
    tmp = TOP5_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        _json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, TOP5_PATH)

def _top5_item(mid):
    """(название, язык) книги или серии по message_id; None, если книги уже нет в каталоге."""
    loc = _find_by_message_id(mid) if isinstance(mid, int) else None
    if not loc:
        return None
    sc, lg, i = loc
    book = BOOKS_DB[sc][lg][i]
    info = series_info(mid)
    title = info["title"] if info and info.get("title") else _plain_name(book.get("file_name", ""))
    return title, lg

def top5_card(code):
    """(текст, клавиатура) топ-5 предмета или None, если список пуст."""
    rows, lines = [], []
    for it in (load_top5().get(code) or [])[:TOP5_MAX]:
        got = _top5_item(it.get("mid"))
        if not got:
            continue
        n = len(rows) + 1
        title, lg = got
        lines.append(f"{n}. {_LANG_FLAG.get(lg, '📖')} {title}")
        row = [InlineKeyboardButton(text=f"📖 {n}. {title[:26]}", callback_data=f"bm_{it['mid']}")]
        if str(it.get("video") or "").startswith(("http://", "https://")):
            row.append(InlineKeyboardButton(text="🎬 Видео", url=it["video"]))
        rows.append(row)
    if not rows:
        return None
    rows.append([InlineKeyboardButton(text="📋 Каталог / Catalog", callback_data="catalog_open")])
    rows.append([menu_button()])
    text = (f"🏆 Топ-5 · {SUBJECT_NAMES.get(code, code)}\n\n" + "\n".join(lines)
            + "\n\n🎬 Рядом с книгой — мой видеоразбор (если уже вышел)\n📌 @library_adasan")
    return text, InlineKeyboardMarkup(inline_keyboard=rows)

def _top5_codes():
    return [c for c in load_top5() if top5_card(c)]

def _top5_picker():
    rows, row = [], []
    for c in _top5_codes():
        row.append(InlineKeyboardButton(text=SUBJECT_NAMES.get(c, c), callback_data=f"t5_{c}"))
        if len(row) == 2:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([menu_button()])
    return InlineKeyboardMarkup(inline_keyboard=rows)

async def _top5_show_menu(chat_id):
    codes = _top5_codes()
    if not codes:
        await bot.send_message(
            chat_id,
            "🏆 Топ-5 пока не настроен или книги из списка отсутствуют в каталоге.\n"
            "Владелец может задать его командой /top5_set: предмет и ссылки на посты книг в канале."
        )
    elif len(codes) == 1:
        text, kb = top5_card(codes[0])
        await bot.send_message(chat_id, text, reply_markup=kb)
    else:
        await bot.send_message(chat_id, "🏆 Топ-5 книг — выберите предмет:", reply_markup=_top5_picker())

# ---------- управление (только владелец) ----------
def _top5_subject(token):
    t = (token or "").lower()
    if t in SUBJECT_NAMES:
        return t
    return find_subject(t)

def _top5_mid(token):
    """message_id из ссылки t.me/library_adasan/123 или числа; пост с обложкой тоже подходит."""
    m = re.search(r"(\d+)\s*$", (token or "").strip())
    if not m:
        return None
    n = int(m.group(1))
    if _find_by_message_id(n):
        return n
    for langs in BOOKS_DB.values():
        for books in langs.values():
            for b in books:
                if b.get("photo_message_id") == n:
                    return b["message_id"]
    return None

def _top5_help():
    state = []
    for code, items in load_top5().items():
        names = [(_top5_item(i.get("mid")) or ("?",))[0][:22] + (" 🎬" if i.get("video") else "") for i in items]
        state.append(f"• {code}: " + "; ".join(names))
    codes = ", ".join(f"{c} ({n.split(' ', 1)[-1]})" for c, n in list(SUBJECT_NAMES.items())[:40])
    return (
        "🏆 Управление топ-5 (только владелец)\n\n"
        "/top5_set <предмет> <ссылка1> ... <ссылка5> — задать список (ссылки на посты книг в канале)\n"
        "/top5_video <предмет> <номер> <ссылка на видео> — видео к книге (вместо ссылки «-» удаляет)\n"
        "/top5_del <предмет> [номер] — убрать книгу или весь список\n"
        "/top5_export — прислать top5.json (его нужно закоммитить в GitHub)\n\n"
        "Предмет — код или слово: гистология, патфиз…\n"
        f"Коды: {codes}\n\n"
        "Сейчас:\n" + ("\n".join(state) if state else "пока ничего")
    )

def _top5_admin_guard(message):
    return message.from_user.id == ADMIN_ID
