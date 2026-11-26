"""Карточки и списки книг: языки, страницы, кнопки поиска по сериям, автоответ в группах."""

import os
import re
from aiogram import types
from aiogram.types import FSInputFile
from aiogram.types import InlineKeyboardButton
from aiogram.types import InlineKeyboardMarkup

from books import BOOKS_DB, _DYN_NAMES
from core import BASE_DIR, CHANNEL, bot, logger
from database import add_book_history, get_votes, record_book_open
from keyboards import BOT_INFO, back_menu_row, menu_button, subject_inline
from search_engine import search_books_multilingual
from series import _plain_name, series_index, series_info
from subjects import SUBJECT_PHOTOS, subject_title
from texts import LANG_NAMES, esc, tl, tr, user_lang
from top5 import _top5_codes

PER_PAGE = 8


def subject_book_count(code):
    return sum(len(v) for v in BOOKS_DB.get(code, {}).values())


async def send_subject_menu(chat_id, code, uid=None):
    """Меню предмета на языке пользователя. В личке chat_id совпадает с id пользователя."""
    lang = user_lang(uid or chat_id)
    total = subject_book_count(code)
    # Раздел из хэштегов открывается сразу списком языков (без силлабусов и препаратов)
    if code in _DYN_NAMES:
        await bot.send_message(
            chat_id,
            tl(lang, "books_choose_lang", name=esc(_DYN_NAMES[code]), n=total),
            parse_mode="HTML",
            reply_markup=lang_inline(code, uid or chat_id),
        )
        return
    caption = tl(lang, "subject_menu", name=esc(subject_title(code, lang)), n=total)
    photo_file = SUBJECT_PHOTOS.get(code)
    photo_path = os.path.join(BASE_DIR, photo_file) if photo_file else None
    if photo_path and os.path.exists(photo_path):
        await bot.send_photo(chat_id=chat_id, photo=FSInputFile(photo_path), caption=caption,
                             parse_mode="HTML", reply_markup=subject_inline(code, lang))
    else:
        await bot.send_message(chat_id=chat_id, text=caption, parse_mode="HTML",
                               reply_markup=subject_inline(code, lang))

# =========================
# INLINE — язык книг из BOOKS_DB
# =========================
def lang_inline(subject_code, uid=None):
    lang_ui = user_lang(uid)
    langs = BOOKS_DB.get(subject_code, {})
    order = ["rus", "kaz", "eng"]
    if lang_ui == "en":
        order = ["eng", "rus", "kaz"]      # английский интерфейс: English первым, остальные доступны
    elif lang_ui == "kz":
        order = ["kaz", "rus", "eng"]      # казахский интерфейс: казахские книги первыми
    buttons = [
        InlineKeyboardButton(text=f"{LANG_NAMES[lg]} · {len(_list_entries(subject_code, lg))}",
                             callback_data=f"bl_{subject_code}_{lg}")
        for lg in order if langs.get(lg)
    ]
    rows = [[b] for b in buttons]
    # «Назад» из раздела-хэштега ведёт в каталог, а не в меню предмета
    back_to = "catalog_open" if subject_code in _DYN_NAMES else f"subject_{subject_code}"
    rows.append(back_menu_row(lang_ui, back_to))
    if subject_code in _top5_codes():                    # «Топ-5» — только там, где список уже составлен
        rows.insert(0, [InlineKeyboardButton(text="🏆 Топ-5 / Үздік 5", callback_data=f"t5_{subject_code}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def _list_entries(subject_code, lang):
    """Элементы списка книг раздела: все тома одной серии — ОДНИМ элементом.
    [(индекс_в_списке, книга, id_серии | None)]"""
    books = BOOKS_DB.get(subject_code, {}).get(lang, [])
    of = series_index()["of"]
    seen, out = set(), []
    for idx, b in enumerate(books):
        sid = of.get(b.get("message_id"))
        if sid:
            if sid in seen:
                continue
            seen.add(sid)
        out.append((idx, b, sid))
    return out

def page_count(subject_code, lang):
    return max(1, -(-len(_list_entries(subject_code, lang)) // PER_PAGE))

def booklist_header(uid, subject_code, lang, page=0):
    """Заголовок списка книг: предмет · язык · сколько книг · страница."""
    ui = user_lang(uid)
    n = len(_list_entries(subject_code, lang))
    pages = page_count(subject_code, lang)
    page = min(max(page, 0), pages - 1)
    page_txt = tl(ui, "list_page", p=page + 1, t=pages) if pages > 1 else ""
    return tl(ui, "list_header_html", name=esc(subject_title(subject_code, ui)),
              lang=LANG_NAMES.get(lang, lang), n=n, page=page_txt)

def booklist_inline(subject_code, lang, page=0, uid=None):
    entries = _list_entries(subject_code, lang)
    pages = page_count(subject_code, lang)
    page = min(max(page, 0), pages - 1)                 # старая кнопка после /update_books — не выходим за границы
    start = page * PER_PAGE
    end = start + PER_PAGE
    rows = []
    for idx, book, sid in entries[start:end]:
        info = series_info(book.get("message_id")) if sid else None
        if info:
            first = info["members"][0]
            rows.append([group_button(uid, {"sc": first["sc"], "lang": first["lang"], "idx": first["idx"],
                                            "book": first["book"], "series": info})])
            continue
        name = _plain_name(book.get("file_name", ""))[:40]
        rows.append([InlineKeyboardButton(
            text=f"📖 {name}", callback_data=f"bk_{subject_code}_{lang}_{idx}")])
    if pages > 1:
        # Навигация всегда из трёх кнопок: ◀️ | 2/5 | ▶️ — видно, где ты находишься
        rows.append([
            InlineKeyboardButton(text="◀️" if page > 0 else "·",
                                 callback_data=f"bp_{subject_code}_{lang}_{page-1}" if page > 0 else "noop"),
            InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="noop"),
            InlineKeyboardButton(text="▶️" if end < len(entries) else "·",
                                 callback_data=f"bp_{subject_code}_{lang}_{page+1}" if end < len(entries) else "noop"),
        ])
    rows.append(back_menu_row(user_lang(uid), f"books_{subject_code}"))
    return InlineKeyboardMarkup(inline_keyboard=rows)

def share_button(uid, title):
    """«📤 Поделиться» — открывает выбор чата с inline-запросом по названию книги."""
    if not BOT_INFO["inline"] or not title:
        return None
    return InlineKeyboardButton(text=tr(uid, "btn_share"), switch_inline_query=title[:60])

def book_card_keyboard(subject_code, lang, idx, url, uid=None, title=None, extra_rows=None):
    likes, dislikes = get_votes(url)
    ui = user_lang(uid)
    rows = [[InlineKeyboardButton(text=tl(ui, "btn_download"), url=url)]]
    second = [InlineKeyboardButton(text=tl(ui, "fav_add_btn"), callback_data=f"fav_add_{subject_code}_{lang}_{idx}")]
    share = share_button(uid, title)
    if share:
        second.append(share)
    rows.append(second)
    rows.append([
        InlineKeyboardButton(text=f"👍 {likes}", callback_data=f"rate_up_{subject_code}_{lang}_{idx}"),
        InlineKeyboardButton(text=f"👎 {dislikes}", callback_data=f"rate_dn_{subject_code}_{lang}_{idx}"),
    ])
    rows += extra_rows or []
    rows.append(back_menu_row(ui, f"bl_{subject_code}_{lang}"))
    return InlineKeyboardMarkup(inline_keyboard=rows)

def book_card_caption(uid, subject_code, lang, title, extra=""):
    ui = user_lang(uid)
    return tl(ui, "book_card", title=esc(title[:40]), subject=esc(subject_title(subject_code, ui)),
              lang=LANG_NAMES.get(lang, lang), extra=extra)

async def send_book_card(chat_id, uid, subject_code, lang, idx, head=None, extra_rows=None):
    """Карточка одной книги: настоящая обложка из канала (если есть) + описание + кнопки.
    Возвращает False, если книги с таким индексом нет. Многотомные книги — отдельной карточкой серии."""
    books_list = BOOKS_DB.get(subject_code, {}).get(lang, [])
    if not 0 <= idx < len(books_list):
        return False
    book = books_list[idx]
    series = series_info(book.get("message_id"))
    if series:
        await send_series_card(chat_id, uid, series, head=head)
        return True
    name = _plain_name(book.get("file_name", "")) or "📖"
    caption = book_card_caption(uid, subject_code, lang, name)
    if head:
        caption = f"{head}\n\n{caption}"
    keyboard = book_card_keyboard(subject_code, lang, idx, book["url"], uid, title=name, extra_rows=extra_rows)
    source_chat = f"@{CHANNEL.lstrip('@')}"
    sent = False
    cover_id = book.get("photo_message_id")
    if cover_id:
        try:
            await bot.copy_message(chat_id=chat_id, from_chat_id=source_chat, message_id=int(cover_id),
                                   caption=caption, parse_mode="HTML", reply_markup=keyboard)
            sent = True
        except Exception as e:
            logger.warning(f"Обложка не скопировалась (пост {cover_id}): {e}")
    if not sent and book.get("message_id"):
        # Обложки нет — присылаем сам пост с файлом (книгу можно открыть прямо в чате).
        try:
            await bot.copy_message(chat_id=chat_id, from_chat_id=source_chat, message_id=int(book["message_id"]),
                                   caption=caption, parse_mode="HTML", reply_markup=keyboard)
            sent = True
        except Exception as e:
            logger.warning(f"Пост книги не скопировался ({book.get('message_id')}): {e}")
    if not sent:
        # Не выдаём тематическую картинку за обложку: если ничего не вышло — аккуратная текстовая карточка.
        await bot.send_message(chat_id=chat_id, text=caption, parse_mode="HTML", reply_markup=keyboard)
    short = name[:50]
    add_book_history(uid, subject_code, lang, idx, short, book["url"])
    record_book_open(book["url"], short, subject_code, lang)
    return True

# =========================
# ГРУППЫ / ОБСУЖДЕНИЯ КАНАЛА — авто-ответ книгой
# =========================
GROUP_MIN_SCORE = 0.8        # строже, чем в личке: меньше ложных срабатываний в болтовне

GROUP_MAX_RESULTS = 3        # больше стольких книг — запрос слишком общий, молчим

GROUP_USER_COOLDOWN = 20     # секунд между ответами одному человеку

GROUP_CHAT_COOLDOWN = 4      # секунд между ответами в одном чате

_group_user_last = {}

_group_chat_last = {}

async def _send_book_to_group(message, sc, lang, idx, bk):
    """Копирует файл из канала в группу. Если не вышло — отправляет карточку со ссылкой."""
    url = bk.get("url", "")
    name = bk["file_name"].replace(".pdf", "").replace(".djvu", "").replace("_", " ")
    m = re.search(r"/(\d+)$", url)
    cover_id = bk.get("photo_message_id")
    if m and cover_id:
        try:
            await bot.copy_message(
                chat_id=message.chat.id,
                from_chat_id=f"@{CHANNEL.lstrip('@')}",
                message_id=int(cover_id),
                reply_to_message_id=message.message_id,
            )
        except Exception as e:
            logger.warning(f"Обложка в группу не скопировалась ({cover_id}): {e}")
    if m:
        try:
            await bot.copy_message(
                chat_id=message.chat.id,
                from_chat_id=f"@{CHANNEL.lstrip('@')}",
                message_id=int(m.group(1)),
                reply_to_message_id=message.message_id,
            )
            return True
        except Exception as e:
            logger.warning(f"copy_message не удался ({url}): {e}")
    try:
        await message.reply(
            f"📖 {name[:60]}\n📌 @library_adasan",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📥 Жүктеу / Скачать", url=url)]
            ])
        )
        return True
    except Exception as e:
        logger.warning(f"Ответ в группу не удался: {e}")
        return False

# =========================
# ОБЪЕДИНЕНИЕ ТОМОВ В ОДНУ КНОПКУ ПОИСКА
# «Пищевар Неттер Часть 1 / 2 / 3» -> одна кнопка «Пищевар Неттер — тома 1, 2, 3»
# =========================
SEARCH_GROUPS_LIMIT = 15   # сколько кнопок максимум показываем в результатах поиска

_FLAGS = {"rus": "🇷🇺", "kaz": "🇰🇿", "eng": "🇬🇧"}

def _sx_tail(member_title, series_title):
    """Чем том отличается от остальных: «Ажаев Гистология 2 бөлім Жалпы гистология» -> «Жалпы гистология»."""
    t = (member_title or "").strip()
    s = (series_title or "").strip()
    if s and t.lower().startswith(s.lower()):
        t = t[len(s):]
    return re.sub(r"^[\s.,;:\-–—()\d]+", "", t).strip()

def _vol_label(numbers):
    """[1, 2, 3] -> «1, 2, 3»;  [1..6] -> «1–6»;  [1, 2, 5] -> «1, 2, 5»."""
    nums = sorted({n for n in numbers if n is not None})
    if not nums:
        return ""
    runs, start, prev = [], nums[0], nums[0]
    for n in nums[1:]:
        if n == prev + 1:
            prev = n
            continue
        runs.append((start, prev))
        start = prev = n
    runs.append((start, prev))
    parts = []
    for a, b in runs:
        parts.append(f"{a}–{b}" if b - a >= 3 else ", ".join(str(x) for x in range(a, b + 1)))
    return ", ".join(parts)

async def search_book_groups(query, limit=SEARCH_GROUPS_LIMIT):
    """Поиск, где тома одной серии объединены в одну кнопку — независимо от языка и предмета, в которые
    бот отнёс каждый том. Возвращает (всего_групп, группы, is_fuzzy).
    Группа: {"sc", "lang", "idx", "book", "series"}; series = None, если книга одна."""
    _total, books, is_fuzzy = await search_books_multilingual(query, 10 ** 6)
    of = series_index()["of"]
    groups, seen = [], set()
    for sc, lang, idx, bk in books:
        sid = of.get(bk.get("message_id"))
        if sid:
            if sid in seen:
                continue
            info = series_info(bk["message_id"])
            if info:
                seen.add(sid)
                first = info["members"][0]
                groups.append({"sc": first["sc"], "lang": first["lang"], "idx": first["idx"],
                               "book": first["book"], "series": info})
                continue
        groups.append({"sc": sc, "lang": lang, "idx": idx, "book": bk, "series": None})
    return len(groups), groups[:limit], is_fuzzy

def group_button(uid, g):
    s = g.get("series")
    if s:
        flag = _FLAGS.get(s["lang"], "")
        title = (s["title"] or "")[:30]
        vols = _vol_label([m["vol"] for m in s["members"]])
        word = tr(uid, "vol_word")
        if title and vols:
            label = f"{flag} {title} — {word} {vols}"
        elif title:
            label = f"{flag} {title} ({len(s['members'])})"
        else:                                            # у томов нет названия: «том 1», «том 2»…
            label = f"{flag} {word.capitalize()} {vols}".strip() if vols else f"{flag} ({len(s['members'])})"
        return InlineKeyboardButton(text=label, callback_data=f"bg_{g['sc']}_{g['lang']}_{g['idx']}")
    flag = _FLAGS.get(g["lang"], "")
    name = _plain_name(g["book"].get("file_name", ""))[:35]
    return InlineKeyboardButton(text=f"{flag} {name}", callback_data=f"bk_{g['sc']}_{g['lang']}_{g['idx']}")

async def _send_cover_card(chat_id, cover_id, post_id, caption, keyboard):
    """Обложка + подпись + кнопки. Порядок как в карточке одной книги:
    копия обложки -> пересылка обложки + текст -> пост с книгой -> просто текст."""
    source_chat = f"@{CHANNEL.lstrip('@')}"
    if cover_id:
        try:
            await bot.copy_message(chat_id=chat_id, from_chat_id=source_chat, message_id=int(cover_id),
                                   caption=caption, parse_mode="HTML", reply_markup=keyboard)
            return "cover"
        except Exception as e:
            logger.warning(f"Обложка серии не скопировалась (пост {cover_id}): {e}")
            try:
                await bot.forward_message(chat_id=chat_id, from_chat_id=source_chat, message_id=int(cover_id))
                await bot.send_message(chat_id=chat_id, text=caption, parse_mode="HTML", reply_markup=keyboard)
                return "cover-forward"
            except Exception as e2:
                logger.warning(f"Обложка серии не переслалась (пост {cover_id}): {e2}")
    # Обложки нет — не выдаём чужую картинку за обложку, показываем текстовую карточку.
    await bot.send_message(chat_id=chat_id, text=caption, parse_mode="HTML", reply_markup=keyboard)
    return "text"

def _series_card_keyboard(info, uid):
    """Многотомная книга = ОДНА книга: кнопки скачивания по томам, а ⭐ и 👍/👎 — один раз на всю серию
    (хранятся на первом томе, так же как открытия и история)."""
    ui = user_lang(uid)
    rows = []
    for member in info["members"]:
        book = member["book"]
        vol = member.get("vol")
        tail_txt = _sx_tail(member["title"], info.get("title") or "")
        if vol is not None:
            label = f"📥 {tl(ui, 'vol_btn')} {vol}" + (f" · {tail_txt}" if tail_txt else "")
        else:
            label = f"📥 {_plain_name(book.get('file_name', ''))}"
        rows.append([InlineKeyboardButton(text=label[:56], url=book["url"])])
    first = info["members"][0]
    sc, lang, idx = first["sc"], first["lang"], first["idx"]
    likes, dislikes = get_votes(first["book"]["url"])
    second = [InlineKeyboardButton(text=tl(ui, "fav_add_btn"), callback_data=f"fav_add_{sc}_{lang}_{idx}")]
    share = share_button(uid, info.get("title") or "")
    if share:
        second.append(share)
    rows.append(second)
    rows.append([
        InlineKeyboardButton(text=f"👍 {likes}", callback_data=f"rate_up_{sc}_{lang}_{idx}"),
        InlineKeyboardButton(text=f"👎 {dislikes}", callback_data=f"rate_dn_{sc}_{lang}_{idx}"),
    ])
    rows.append(back_menu_row(ui, f"bl_{sc}_{lang}"))
    return InlineKeyboardMarkup(inline_keyboard=rows)

async def send_series_card(chat_id, uid, info, head=None):
    """Одна карточка на всю серию: обложка один раз + кнопка скачивания каждого тома по порядку."""
    members = info["members"]
    title = info["title"] or ""
    vols = _vol_label([m["vol"] for m in members])
    heading = title or f"{tr(uid, 'vol_word').capitalize()} {vols}".strip()
    extra = f"\n📑 {tr(uid, 'series_volumes')} {vols}" if vols else ""
    caption = book_card_caption(uid, info["subject"], info["lang"], heading, extra=extra)
    if head:
        caption = f"{head}\n\n{caption}"
    keyboard = _series_card_keyboard(info, uid)

    # Обложка у всех томов общая; берём первую найденную (propagate_series_covers уже раздал её томам).
    await _send_cover_card(chat_id, info["cover"], members[0]["book"].get("message_id"), caption, keyboard)
    try:
        first = members[0]
        name = (title or _plain_name(first["book"].get("file_name", "")))[:50]
        add_book_history(uid, first["sc"], first["lang"], first["idx"], name, first["book"]["url"])
        record_book_open(first["book"]["url"], name, first["sc"], first["lang"])
    except Exception as e:
        logger.warning(f"История серии не записалась: {e}")

async def _send_series_card(callback: types.CallbackQuery, info):
    """Обёртка для кнопок: показывает серию и убирает сообщение со списком."""
    await send_series_card(callback.message.chat.id, callback.from_user.id, info)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()
