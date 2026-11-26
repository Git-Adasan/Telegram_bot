"""Новые возможности: 👤 профиль, 🎲 случайная книга, 💬 обратная связь с админом, 🔎 inline-поиск в любом чате.

Подключается в main.py ПЕРЕД handlers_search: обработчик отзыва ловит обычный текст,
и если бы поиск стоял выше, отзыв ушёл бы в поиск книг.
"""

import random
import time
from datetime import datetime

from aiogram import F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton
from aiogram.types import InlineKeyboardMarkup

from book_cards import _vol_label, search_book_groups, send_book_card
from books import BOOKS_DB
from buttons import LABELS, is_button
from core import ADMIN_ID, bot, dp, logger
from database import get_user_profile, is_banned
from keyboards import BOT_INFO, menu_button
from series import _plain_name
from subjects import subject_title
from texts import LANG_FLAGS, LANG_NAMES, esc, tl, user_lang

LANG_UI_NAMES = {"kz": "🇰🇿 Қазақша", "ru": "🇷🇺 Русский", "en": "🇬🇧 English"}


# =========================
# 👤 ПРОФИЛЬ
# =========================
_LEVELS = (0, 5, 20, 50)          # сколько книг открыть для уровня 0 / 1 / 2 / 3


def _profile_text(uid):
    lang = user_lang(uid)
    p = get_user_profile(uid)
    since, days = "—", 0
    if p["joined_at"]:
        try:
            joined = datetime.fromisoformat(p["joined_at"])
            since, days = joined.strftime("%d.%m.%Y"), max(0, (datetime.now() - joined).days)
        except ValueError:
            pass
    level = max(i for i, need in enumerate(_LEVELS) if p["opened"] >= need)
    badge = tl(lang, f"badge_{level}")
    if level + 1 < len(_LEVELS):
        badge += tl(lang, "badge_next", left=_LEVELS[level + 1] - p["opened"])
    return tl(lang, "profile", lang=LANG_UI_NAMES[lang], since=since, days=days, opened=p["opened"],
              favs=p["favs"], searches=p["searches"], votes=p["votes"], wishes=p["wishes"], badge=badge)


def _profile_keyboard(uid):
    lang = user_lang(uid)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=LABELS["favorites"][lang], callback_data="go_fav"),
         InlineKeyboardButton(text=LABELS["history"][lang], callback_data="go_history")],
        [InlineKeyboardButton(text=tl(lang, "btn_lang"), callback_data="go_lang"),
         InlineKeyboardButton(text=tl(lang, "btn_feedback"), callback_data="go_feedback")],
        [menu_button(lang)],
    ])


@dp.message(Command("profile", "me"))
@dp.message(is_button("profile"))
async def profile_command(message: types.Message):
    uid = message.from_user.id
    await message.answer(_profile_text(uid), parse_mode="HTML", reply_markup=_profile_keyboard(uid))


@dp.callback_query(F.data == "go_profile")
async def profile_callback(callback: types.CallbackQuery):
    uid = callback.from_user.id
    await callback.answer()
    await callback.message.answer(_profile_text(uid), parse_mode="HTML", reply_markup=_profile_keyboard(uid))


@dp.callback_query(F.data == "go_history")
async def history_callback(callback: types.CallbackQuery):
    from handlers_user import _history_screen          # экран истории — один на кнопку и команду
    await callback.answer()
    text, keyboard = _history_screen(callback.from_user.id)
    await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard)


# =========================
# 🎲 СЛУЧАЙНАЯ КНИГА
# =========================
_LANG_PREF = {"kz": "kaz", "ru": "rus", "en": "eng"}


def _random_location(lang_ui):
    """Случайная книга. В 70% случаев — на языке интерфейса пользователя (если такие есть)."""
    pool, preferred = [], []
    want = _LANG_PREF.get(lang_ui)
    for sc, langs in BOOKS_DB.items():
        for lg, books in langs.items():
            for i in range(len(books)):
                pool.append((sc, lg, i))
                if lg == want:
                    preferred.append((sc, lg, i))
    if preferred and random.random() < 0.7:
        return random.choice(preferred)
    return random.choice(pool) if pool else None


async def send_random_book(chat_id, uid):
    lang = user_lang(uid)
    loc = _random_location(lang)
    if not loc:
        await bot.send_message(chat_id, tl(lang, "random_empty"))
        return
    more = [[InlineKeyboardButton(text=tl(lang, "btn_more_random"), callback_data="go_random")]]
    await send_book_card(chat_id, uid, *loc, head=tl(lang, "random_head"), extra_rows=more)


@dp.message(Command("random"))
@dp.message(is_button("random"))
async def random_command(message: types.Message):
    await send_random_book(message.chat.id, message.from_user.id)


@dp.callback_query(F.data == "go_random")
async def random_callback(callback: types.CallbackQuery):
    await callback.answer("🎲")
    await send_random_book(callback.message.chat.id, callback.from_user.id)


# =========================
# 💬 ОБРАТНАЯ СВЯЗЬ С АДМИНОМ
# =========================
FEEDBACK_COOLDOWN = 60            # секунд между отзывами одного человека
FEEDBACK_STATE_TTL = 15 * 60      # сколько ждём текст после нажатия «Написать админу»

_feedback_state = {}              # user_id -> когда нажал «Написать»
_feedback_last = {}               # user_id -> когда последний раз отправил
_admin_reply_to = {}              # admin_id -> user_id, которому сейчас пишем ответ


def _cancel_kb(lang):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=tl(lang, "btn_cancel"),
                                                                       callback_data="fb_cancel")]])


async def _ask_feedback(chat_id, uid):
    lang = user_lang(uid)
    if time.time() - _feedback_last.get(uid, 0) < FEEDBACK_COOLDOWN:
        await bot.send_message(chat_id, tl(lang, "feedback_cooldown"))
        return
    _feedback_state[uid] = time.time()
    await bot.send_message(chat_id, tl(lang, "feedback_prompt"), parse_mode="HTML", reply_markup=_cancel_kb(lang))


@dp.message(Command("feedback"))
async def feedback_command(message: types.Message):
    if message.chat.type != "private":
        return
    await _ask_feedback(message.chat.id, message.from_user.id)


@dp.callback_query(F.data == "go_feedback")
async def feedback_callback(callback: types.CallbackQuery):
    await callback.answer()
    await _ask_feedback(callback.message.chat.id, callback.from_user.id)


@dp.callback_query(F.data == "fb_cancel")
async def feedback_cancel(callback: types.CallbackQuery):
    _feedback_state.pop(callback.from_user.id, None)
    _admin_reply_to.pop(callback.from_user.id, None)
    await callback.answer()
    try:
        await callback.message.edit_text(tl(user_lang(callback.from_user.id), "feedback_cancel"))
    except Exception:
        pass


def _waiting_feedback(m: types.Message):
    if not m.from_user or m.chat.type != "private" or not m.text or m.text.startswith("/"):
        return False
    started = _feedback_state.get(m.from_user.id)
    return bool(started) and time.time() - started < FEEDBACK_STATE_TTL


@dp.message(_waiting_feedback)
async def feedback_receive(message: types.Message):
    user = message.from_user
    _feedback_state.pop(user.id, None)
    _feedback_last[user.id] = time.time()
    who = f"@{user.username}" if user.username else esc(user.first_name or "—")
    try:
        await bot.send_message(
            ADMIN_ID,
            f"💬 <b>Отзыв / Пікір</b>\n👤 {who} · <code>{user.id}</code> · {user_lang(user.id)}\n\n{esc(message.text[:3500])}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="↩️ Ответить", callback_data=f"fbr_{user.id}"),
            ]]),
        )
    except Exception as e:
        logger.warning(f"Отзыв не доставлен админу: {e}")
    await message.answer(tl(user_lang(user.id), "feedback_sent"),
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=[[menu_button(user_lang(user.id))]]))


@dp.callback_query(F.data.startswith("fbr_"))
async def feedback_reply_start(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌", show_alert=True)
        return
    try:
        target = int(callback.data[4:])
    except ValueError:
        await callback.answer()
        return
    _admin_reply_to[ADMIN_ID] = target
    await callback.answer()
    await callback.message.answer(f"✍️ Напишите ответ для <code>{target}</code> одним сообщением.",
                                  parse_mode="HTML", reply_markup=_cancel_kb("ru"))


@dp.message(lambda m: m.from_user and m.from_user.id == ADMIN_ID and m.chat.type == "private"
            and m.text and not m.text.startswith("/") and ADMIN_ID in _admin_reply_to)
async def feedback_reply_send(message: types.Message):
    target = _admin_reply_to.pop(ADMIN_ID)
    try:
        await bot.send_message(target, tl(user_lang(target), "feedback_reply", text=esc(message.text)),
                               parse_mode="HTML")
        await message.answer("✅ Ответ отправлен.")
    except Exception as e:
        await message.answer(f"❌ Не доставлено: {esc(str(e)[:200])}", parse_mode="HTML")


# =========================
# 🔎 INLINE-ПОИСК: @бот название — в любом чате
# Нужно один раз включить в @BotFather: /setinline → выбрать бота → подсказка «Название книги…».
# =========================
def _inline_result(uid, g, n):
    lang = user_lang(uid)
    series = g.get("series")
    book = g["book"]
    if series:
        title = series["title"] or _plain_name(book.get("file_name", ""))
        vols = _vol_label([m["vol"] for m in series["members"]])
        buttons = [[InlineKeyboardButton(text=f"📥 {tl(lang, 'vol_btn')} {m['vol']}" if m.get("vol") is not None
                                         else f"📥 {_plain_name(m['book'].get('file_name', ''))[:40]}",
                                         url=m["book"]["url"])] for m in series["members"][:8]]
        extra = f"\n📑 {tl(lang, 'series_volumes')} {vols}" if vols else ""
        flag = LANG_FLAGS.get(series["lang"], "")
        sc, lg = series["subject"], series["lang"]
    else:
        title = _plain_name(book.get("file_name", "")) or "📖"
        buttons = [[InlineKeyboardButton(text=tl(lang, "btn_download"), url=book["url"])]]
        extra = ""
        flag = LANG_FLAGS.get(g["lang"], "")
        sc, lg = g["sc"], g["lang"]
    if BOT_INFO["username"]:
        buttons.append([InlineKeyboardButton(text="🤖 Adasan Library", url=f"https://t.me/{BOT_INFO['username']}?start=inline")])
    text = (f"📖 <b>{esc(title[:120])}</b>\n"
            f"📚 {esc(subject_title(sc, lang))} · {LANG_NAMES.get(lg, lg)}{extra}\n\n📌 @library_adasan")
    return types.InlineQueryResultArticle(
        id=f"{sc}:{lg}:{g['idx']}:{n}"[:64],
        title=f"{flag} {title[:90]}",
        description=f"{subject_title(sc, lang)} · {LANG_NAMES.get(lg, lg)}",
        input_message_content=types.InputTextMessageContent(message_text=text, parse_mode="HTML",
                                                           link_preview_options=types.LinkPreviewOptions(is_disabled=True)),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@dp.inline_query()
async def inline_search(query: types.InlineQuery):
    uid = query.from_user.id
    lang = user_lang(uid)
    text = (query.query or "").strip()[:100]
    open_bot = types.InlineQueryResultsButton(text=tl(lang, "inline_hint") if not text else "🤖 Adasan Library",
                                              start_parameter="inline")
    if is_banned(uid) or len(text) < 2:
        await query.answer([], cache_time=60, is_personal=True, button=open_bot)
        return
    try:
        _total, groups, _fuzzy = await search_book_groups(text, 20)
    except Exception as e:
        logger.warning(f"Inline-поиск не удался: {e}")
        groups = []
    results = [_inline_result(uid, g, n) for n, g in enumerate(groups)]
    if not results:
        results = [types.InlineQueryResultArticle(
            id="nf",
            title=f"😕 {tl(lang, 'inline_nf')}",
            description=tl(lang, "inline_nf_desc"),
            input_message_content=types.InputTextMessageContent(
                message_text=f"🔎 {esc(text)}\n\n📌 @library_adasan", parse_mode="HTML"),
        )]
    await query.answer(results, cache_time=120, is_personal=True, button=open_bot)   # личный: текст на языке пользователя
