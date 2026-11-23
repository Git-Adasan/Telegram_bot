"""Каталог по хэштегам и ручной разбор раздела «other» (/sort_other).
В конце модуля — миграции каталога, которые выполняются при запуске."""

import html as _html
import os
import re
from aiogram import types
from aiogram.types import FSInputFile
from aiogram.types import InlineKeyboardButton
from aiogram.types import InlineKeyboardMarkup

from books import BOOKS_DB, _DYN_NAMES, _load_sort_overrides, _save_sort_overrides, save_books_db
from core import ADMIN_ID, BASE_DIR, bot, logger
from series import inherit_series_covers, normalize_existing_catalog, propagate_series_covers
from subjects import SUBJECTS, SUBJECT_NAMES
from top5 import _top5_codes
from uploads import LANG_LABELS
from keyboards import menu_button


_sort_skipped = set()   # message_id, пропущенные до перезапуска бота

def _pop_book(db, mid):
    """Достаёт книгу из базы, где бы она ни лежала. Возвращает (язык, книга) или None."""
    for sc, langs in db.items():
        for lg, lst in langs.items():
            for i, b in enumerate(lst):
                if b.get("message_id") == mid:
                    return lg, lst.pop(i)
    return None

def _put_book(db, code, lg, book):
    tgt = db.setdefault(code, {}).setdefault(lg, [])
    tgt.append(book)
    tgt.sort(key=lambda x: x["message_id"], reverse=True)   # как и во всей базе: новые сверху

def apply_sort_overrides(db):
    """Применяет ручные решения админа к свежесобранной базе (вызывается из /update_books),
    чтобы ручная сортировка не сбрасывалась при каждом обновлении."""
    for mid, code in _load_sort_overrides().items():
        if code == "other":
            continue
        found = _pop_book(db, int(mid))
        if found:
            _put_book(db, code, found[0], found[1])
    return db

def _sort_queue():
    ov = _load_sort_overrides()
    out = []
    for lg in ("rus", "kaz", "eng"):
        for b in BOOKS_DB.get("other", {}).get(lg, []):
            mid = b["message_id"]
            if str(mid) in ov or mid in _sort_skipped:
                continue
            out.append((lg, b))
    return out

def _sort_move(mid, code):
    """Переносит книгу из other в предмет и запоминает решение."""
    other = BOOKS_DB.get("other", {})
    for lg, lst in other.items():
        for i, b in enumerate(lst):
            if b.get("message_id") == mid:
                lst.pop(i)
                _put_book(BOOKS_DB, code, lg, b)
                save_books_db()
                ov = _load_sort_overrides()
                ov[str(mid)] = code
                _save_sort_overrides(ov)
                return True
    return False

# --- sort_other: handlers ---

async def _sort_send_files():
    """Хостинг при перезапуске откатывает файлы — присылаем админу свежие копии."""
    for fn, cap in (
        ("books_db.json", "💾 books_db.json — замени этим файлом старый в проекте"),
        ("sort_overrides.json", "💾 sort_overrides.json — положи в проект рядом с books_db.json "
                                "(иначе /update_books забудет ручную сортировку)"),
    ):
        path = os.path.join(BASE_DIR, fn)
        if os.path.exists(path):
            try:
                await bot.send_document(ADMIN_ID, FSInputFile(path), caption=cap)
            except Exception as e:
                logger.warning(f"sort_other: не отправился {fn}: {e}")

def _sort_card():
    queue = _sort_queue()
    if not queue:
        return "✅ Разбор закончен — в other больше нет книг без решения.", None
    lg, b = queue[0]
    mid = b["message_id"]
    caption = (b.get("caption") or "").strip().replace("\n", " ")[:200]
    text = (
        f"📦 <b>other</b> — осталось: {len(queue)}\n\n"
        f"📄 <b>{_html.escape(b.get('file_name', '?'))}</b>\n"
        f"🌐 {LANG_LABELS.get(lg, lg)}\n"
        + (f"📝 {_html.escape(caption)}\n" if caption else "")
        + f"🔗 {b.get('url', '')}\n\n"
        "Куда отнести?"
    )
    rows, row = [], []
    for label, code in SUBJECTS.items():
        row.append(InlineKeyboardButton(text=label, callback_data=f"srt_{code}_{mid}"))
        if len(row) == 2:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([
        InlineKeyboardButton(text="⏭ Пропустить", callback_data=f"srt_skip_{mid}"),
        InlineKeyboardButton(text="📦 Оставить в other", callback_data=f"srt_keep_{mid}"),
    ])
    rows.append([InlineKeyboardButton(text="💾 Прислать файлы", callback_data="srt_files_0")])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)

# =========================
# КАТАЛОГ ПО ХЭШТЕГАМ (/catalog) — разделы создаются из хэштегов в постах канала
# =========================
# --- catalog: logic ---
# Хэштег, который НЕ является предметом (тип материала и т.п.)
_CAT_STOP = {
    "книга", "книги", "учебник", "методичка", "методички", "конспект", "конспекты", "шпаргалка",
    "шпоры", "лекция", "лекции", "препараты", "сборник", "атлас", "adasan", "library_adasan",
    "библиотека", "библотека", "pdf", "тест", "тесты",
}

# Хэштеги, которые уже относятся к 14 готовым предметам: такие книги каталог не трогает
_CAT_STATIC_STEMS = (
    "гист", "цитол", "эмбри", "анат", "anat", "anatom", "biochem", "биох", "бх", "физио", "физиол", "ішкі", "внутр",
    "патфиз", "патофиз", "патфизиол", "патан", "патолог", "топ", "операт", "хирург",
    "пропед", "биохим", "биохи", "биоким", "биох", "бхим", "бх", "bkh", "biochem", "biochemistry",
    "фарма", "фармо", "pharma", "pharmac", "pharmaco", "микроб", "генет", "биофиз", "тарих",
)

# Книги без хэштега, которые определяем по названию (только из раздела other)
_CAT_KEYWORDS = (
    ("пропед", "пропедевтика"), ("эпидем", "эпидемиология"), ("стомат", "стоматология"),
    ("иммунол", "иммунология"), ("радиолог", "радиология"), ("лучев", "радиология"),
)

CATALOG_MIN_BOOKS = 1      # сколько книг нужно, чтобы создать раздел (поставь 2, чтобы убрать одиночки)

CATALOG_TAKE_MIN = 3       # книги из ГОТОВЫХ предметов (не из other) переносим, только если в разделе от 3 книг

CATALOG_SIM = 0.8          # насколько похожи хэштеги, чтобы считать их опечаткой одного раздела

_CAT_TAG_RE = re.compile(r"#(\w+)")

_CAT_TR = dict(zip("абвгдезийклмнопрстуфхыэ", "abvgdezijklmnoprstufhye"))

_CAT_TR.update({"ё": "e", "ж": "zh", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sh", "ю": "yu", "я": "ya",
                "ъ": "", "ь": "", "ә": "a", "і": "i", "ң": "n", "ғ": "g", "ү": "u", "ұ": "u",
                "қ": "k", "ө": "o", "һ": "h"})

def _cat_norm(s):
    return (s or "").lower().replace("ё", "е")

def _cat_slug(word):
    s = "".join(_CAT_TR.get(ch, ch) for ch in _cat_norm(word))
    return re.sub(r"[^a-z0-9]", "", s)[:20] or "razdel"

def _cat_tags(book):
    return [_cat_norm(t) for t in _CAT_TAG_RE.findall(book.get("caption", "") or "")]

def _cat_is_static(tag):
    return tag.startswith(_CAT_STATIC_STEMS)

def _cat_book_tag(book, in_other):
    """Хэштег-кандидат для раздела каталога или None."""
    tags = _cat_tags(book)
    # Варианты тегов стоматологии всегда создают один раздел и используют его обложку.
    if any(t.startswith(("стом", "stom")) for t in tags):
        return "стоматология"
    if any(_cat_is_static(t) for t in tags):
        return None                      # хэштег готового предмета — книгу не трогаем
    for t in tags:
        if len(t) >= 4 and t not in _CAT_STOP:
            return t
    if in_other:                         # хэштега нет — пробуем по названию (только из other)
        text = _cat_norm((book.get("file_name", "") or "") + " " + (book.get("caption", "") or ""))
        for stem, name in _CAT_KEYWORDS:
            if stem in text:
                return name
    return None

def _cat_similar(a, b):
    from difflib import SequenceMatcher
    return a[0] == b[0] and SequenceMatcher(None, a, b).ratio() >= CATALOG_SIM

def build_dynamic_catalog(db):
    """Создаёт разделы из хэштегов (с учётом опечаток) и переносит туда книги.
    Вызывается из /update_books. Возвращает {code: (название, число_книг)}."""
    from collections import Counter
    overrides = _load_sort_overrides()
    cand = []                                            # (откуда_код, язык, книга, тег)
    for sc, langs in db.items():
        for lg, lst in langs.items():
            for b in lst:
                if overrides.get(str(b.get("message_id"))) == "other":
                    continue                              # админ решил оставить в other
                tag = _cat_book_tag(b, in_other=(sc == "other"))
                if tag:
                    cand.append((sc, lg, b, tag))
    freq = Counter(t for _, _, _, t in cand)
    heads, head_of = [], {}
    for tag, _n in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0])):
        for h in heads:
            if _cat_similar(tag, h):
                head_of[tag] = h
                break
        else:
            heads.append(tag)
            head_of[tag] = tag
    size_all = Counter(head_of[t] for _, _, _, t in cand)
    # из готовых предметов (анатомия, внутренние…) берём книгу, только если раздел крупный
    cand = [c for c in cand if c[0] == "other" or size_all[head_of[c[3]]] >= CATALOG_TAKE_MIN]
    group_size = Counter(head_of[t] for _, _, _, t in cand)
    used = set(SUBJECT_NAMES.keys()) - set(_DYN_NAMES.keys())
    codes = {}
    for h in heads:
        if group_size[h] < CATALOG_MIN_BOOKS:
            continue
        code, n = _cat_slug(h), 2
        while code in used:
            code = f"{_cat_slug(h)[:17]}{n}"; n += 1
        used.add(code); codes[h] = code
    summary = {}
    for sc, lg, b, tag in cand:
        h = head_of[tag]
        if h not in codes:
            continue
        code = codes[h]
        for i, x in enumerate(db[sc][lg]):
            if x is b:
                db[sc][lg].pop(i)
                break
        title = "📖 " + h[:1].upper() + h[1:]
        b["subject_title"] = title
        db.setdefault(code, {}).setdefault(lg, []).append(b)
        summary[code] = (title, summary.get(code, ("", 0))[1] + 1)
    for code in codes.values():
        for lg in db.get(code, {}):
            db[code][lg].sort(key=lambda x: x["message_id"], reverse=True)
    return summary

def _refresh_catalog_names(db):
    """Названия разделов хранятся прямо в книгах (subject_title) — отдельного файла не нужно."""
    for code in list(_DYN_NAMES):
        SUBJECT_NAMES.pop(code, None)                   # убираем названия исчезнувших разделов
    _DYN_NAMES.clear()
    static_codes = set(SUBJECTS.values())
    for code, langs in db.items():
        if code == "other" or code in static_codes:
            continue
        for lst in langs.values():
            for b in lst:
                if b.get("subject_title"):
                    _DYN_NAMES[code] = b["subject_title"]
                    break
            if code in _DYN_NAMES:
                break
    for code, name in _DYN_NAMES.items():
        SUBJECT_NAMES[code] = name

def _catalog_extras():
    out = []
    for code in _DYN_NAMES:
        n = sum(len(v) for v in BOOKS_DB.get(code, {}).values())
        if n:
            out.append((n, code))
    out.sort(key=lambda t: (-t[0], t[1]))
    return out[:40]

# --- catalog: handlers ---
_refresh_catalog_names(BOOKS_DB)

def catalog_keyboard():
    rows, row = [], []
    for label, code in SUBJECTS.items():
        row.append(InlineKeyboardButton(text=SUBJECT_NAMES.get(code, label), callback_data=f"subject_{code}"))
        if len(row) == 2:
            rows.append(row); row = []
    if row:
        rows.append(row)
    row = []
    for n, code in _catalog_extras():
        row.append(InlineKeyboardButton(text=f"{_DYN_NAMES[code]} ({n})", callback_data=f"books_{code}"))
        if len(row) == 2:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([menu_button()])
    if _top5_codes():                                    # «Топ-5» — только если список уже составлен
        rows.insert(0, [InlineKeyboardButton(text="🏆 Топ-5 книг / Үздік 5 / Top-5", callback_data="t5_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

CATALOG_TEXT = "📋 Барлық пәндер / Все предметы / All subjects:\n\nПәнді таңдаңыз:"

async def send_catalog(message: types.Message):
    await message.answer(CATALOG_TEXT, reply_markup=catalog_keyboard())

# --- covers: handlers ---
_catalog_migrated = normalize_existing_catalog(BOOKS_DB)

_catalog_covers_added = inherit_series_covers(BOOKS_DB) + propagate_series_covers(BOOKS_DB)

if _catalog_migrated:
    _refresh_catalog_names(BOOKS_DB)

if _catalog_migrated or _catalog_covers_added:
    save_books_db()
