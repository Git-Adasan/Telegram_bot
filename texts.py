"""Тексты интерфейса на трёх языках (UI), функция tr() и приветствие."""

import html

from database import get_lang
from texts_ui import HELP_TEXTS, NEW_UI


# =========================
# ТЕКСТЫ ИНТЕРФЕЙСА ПО ЯЗЫКУ ПОЛЬЗОВАТЕЛЯ (kz / ru / en)
# =========================
UI = {
    "found_n": {
        "kz": "🔍 Табылды: {n} кітап (көрсетілген: {k})",
        "ru": "🔍 Найдено книг: {n} (показано: {k})",
        "en": "🔍 Books found: {n} (showing: {k})",
    },
    "fuzzy_head": {
        "kz": "🔍 Дәл сәйкестік жоқ, мүмкін, мынаны іздедіңіз бе?",
        "ru": "🔍 Точного совпадения нет, возможно, вы искали:",
        "en": "🔍 No exact match. Maybe you meant:",
    },
    "vol_word": {"kz": "том", "ru": "тома", "en": "vol."},
    "vol_btn": {"kz": "том", "ru": "Том", "en": "Vol."},
    "series_volumes": {"kz": "Томдар:", "ru": "Тома:", "en": "Volumes:"},
    "choose": {
        "kz": "👇 Таңдаңыз:",
        "ru": "👇 Выберите:",
        "en": "👇 Choose:",
    },
    "not_found": {
        "kz": ("❌ Кітап табылмады\n\n"
               "📚 Бұл кітапты табу үшін:\n\n"
               "👉 Администраторға жазыңыз: {admin}\n\n"
               "━━━━━━━━━━━━━━━━━━━━━━\n"
               "📌 Немесе пәннің атын жазыңыз:\n"
               "• Гиста / Анат / Биохим\n"
               "• Физиол / Патфиз / Патанат\n"
               "• Синельников / Netter / Афанасьев..."),
        "ru": ("❌ Книга не найдена\n\n"
               "📚 Чтобы найти эту книгу:\n\n"
               "👉 Напишите администратору: {admin}\n\n"
               "━━━━━━━━━━━━━━━━━━━━━━\n"
               "📌 Или напишите название предмета:\n"
               "• Гиста / Анат / Биохим\n"
               "• Физиол / Патфиз / Патанат\n"
               "• Синельников / Netter / Афанасьев..."),
        "en": ("❌ Book not found\n\n"
               "📚 To find this book:\n\n"
               "👉 Message the admin: {admin}\n\n"
               "━━━━━━━━━━━━━━━━━━━━━━\n"
               "📌 Or type a subject name:\n"
               "• Histology / Anatomy / Biochemistry\n"
               "• Physiology / Pathophysiology / Pathoanatomy\n"
               "• Netter / Sinelnikov / Robbins..."),
    },
    "btn_admin": {
        "kz": "✉️ Администраторға жазу",
        "ru": "✉️ Написать администратору",
        "en": "✉️ Message the admin",
    },
    "wish_btn": {
        "kz": "🔔 Пайда болғанда хабарлау",
        "ru": "🔔 Сообщить, когда появится",
        "en": "🔔 Notify me when it's added",
    },
    "wish_ok": {
        "kz": "🔔 Жақсы! Кітап қосылса, сізге хабарлаймыз.",
        "ru": "🔔 Готово! Сообщим, когда книга появится.",
        "en": "🔔 Done! We'll tell you when the book is added.",
    },
    "wish_gone": {
        "kz": "ℹ️ Бұл сұраныс жабылды. Іздеуді қайталаңыз.",
        "ru": "ℹ️ Этот запрос уже закрыт. Повторите поиск.",
        "en": "ℹ️ This request is closed. Please search again.",
    },
    "wish_limit": {
        "kz": "⚠️ Күтіп тұрған кітаптар тым көп (20). Біреуі шыққанша күте тұрыңыз.",
        "ru": "⚠️ Слишком много ожидаемых книг (20). Дождитесь, пока появится одна из них.",
        "en": "⚠️ Too many pending books (20). Wait until one of them appears.",
    },
    "wish_found": {
        "kz": "🎉 Сіз іздеген «{q}» кітабы пайда болды!\n\n👇 Таңдаңыз:",
        "ru": "🎉 Книга, которую вы искали — «{q}», появилась!\n\n👇 Выберите:",
        "en": "🎉 The book you were looking for — “{q}” — is now available!\n\n👇 Choose:",
    },
    "list_header": {
        "kz": "{name} — Кітаптар\n{lang}\n\n👇 Таңдаңыз ({n} кітап):",
        "ru": "{name} — Книги\n{lang}\n\n👇 Выберите ({n} книг):",
        "en": "{name} — Books\n{lang}\n\n👇 Choose ({n} books):",
    },
    "card_subject": {"kz": "Пән:", "ru": "Предмет:", "en": "Subject:"},
    "card_lang":    {"kz": "Тіл:", "ru": "Язык:", "en": "Language:"},
    "fav_add_btn": {
        "kz": "⭐ Таңдаулыға қосу",
        "ru": "⭐ В избранное",
        "en": "⭐ Add to favorites",
    },
    "book_nf_alert": {
        "kz": "❌ Кітап табылмады!",
        "ru": "❌ Книга не найдена!",
        "en": "❌ Book not found!",
    },
    "fav_added": {
        "kz": "⭐ Таңдаулыларға қосылды!",
        "ru": "⭐ Добавлено в избранное!",
        "en": "⭐ Added to favorites!",
    },
    "fav_exists": {
        "kz": "✅ Бұл кітап бұрын қосылған!",
        "ru": "✅ Эта книга уже в избранном!",
        "en": "✅ Already in your favorites!",
    },
    "fav_removed": {
        "kz": "🗑 Өшірілді!",
        "ru": "🗑 Удалено!",
        "en": "🗑 Removed!",
    },
    "favs_title": {
        "kz": "⭐ Сіздің таңдаулыларыңыз ({n}):",
        "ru": "⭐ Ваше избранное ({n}):",
        "en": "⭐ Your favorites ({n}):",
    },
}

def user_lang(user_id):
    """Язык интерфейса пользователя: kz / ru / en (если неизвестен — русский)."""
    lang = get_lang(user_id) if user_id else "ru"
    return lang if lang in ("kz", "ru", "en") else "ru"


def tl(ui_lang, key, /, **kw):
    """Текст по коду языка (kz / ru / en). Параметры позиционные: в текстах есть подстановка {lang}."""
    item = UI[key]
    text = item.get(ui_lang) or item.get("ru")
    return text.format(**kw) if kw else text


def tr(user_id, key, /, **kw):
    """Текст по языку пользователя. Если язык неизвестен — русский."""
    return tl(user_lang(user_id), key, **kw)


def esc(value):
    """Экранирует текст для parse_mode=HTML (имена людей, названия файлов)."""
    return html.escape(str(value or ""), quote=False)


LANG_NAMES = {"rus": "🇷🇺 Русский", "kaz": "🇰🇿 Қазақша", "eng": "🇬🇧 English"}

LANG_FLAGS = {"rus": "🇷🇺", "kaz": "🇰🇿", "eng": "🇬🇧"}

UI.update(NEW_UI)

# Старое имя оставлено для совместимости (раньше приветствие было обычным текстом в рамке).
WELCOME_TEXTS = {lang: UI["welcome"][lang] for lang in ("kz", "ru", "en")}


def welcome_text(lang, first_name):
    """Приветствие (HTML) с безопасно подставленным именем."""
    return tl(lang, "welcome", name=esc(first_name or "👋"))


def help_text(lang, bot_username):
    return HELP_TEXTS.get(lang, HELP_TEXTS["ru"]).replace("{bot}", esc(bot_username or "bot"))
