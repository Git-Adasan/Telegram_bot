"""Базовые клавиатуры: главное меню, меню предмета, выбор языка, кнопка подписки."""

from aiogram.types import InlineKeyboardButton
from aiogram.types import InlineKeyboardMarkup
from aiogram.types import KeyboardButton
from aiogram.types import ReplyKeyboardMarkup

from buttons import LABELS, PLACEHOLDER
from subjects import NO_PREPARATY
from texts import tl

CHANNEL_URL = "https://t.me/library_adasan"

VIDEO_SUBJECTS = {"anatomiya", "hirurgiya"}

# Включён ли inline-режим у бота (BotFather → /setinline). main.py проверяет это при запуске через get_me().
# Без inline-режима кнопки «Поделиться» и «Искать в любом чате» не показываем — Telegram их отклонит.
BOT_INFO = {"inline": False, "username": ""}


def _lang(lang):
    return lang if lang in ("kz", "ru", "en") else "ru"


def menu_button(lang=None):
    """Кнопка «🏠 Меню» — одна на весь бот. С языком — на языке пользователя, без него — на трёх."""
    if lang in ("kz", "ru", "en"):
        return InlineKeyboardButton(text=tl(lang, "btn_menu"), callback_data="go_main_menu")
    return InlineKeyboardButton(text="🏠 Мәзір · Меню · Menu", callback_data="go_main_menu")


def back_button(lang, callback_data):
    return InlineKeyboardButton(text=tl(_lang(lang), "btn_back"), callback_data=callback_data)


def back_menu_row(lang, callback_data):
    """Одна строка «⬅️ Назад | 🏠 Меню» вместо двух отдельных строк — экран короче и аккуратнее."""
    return [back_button(lang, callback_data), menu_button(_lang(lang))]


# =========================
# КЛАВИАТУРЫ
# =========================
_KEYBOARD_SUBJECTS = {
    "kz": [
        ("🔬 Гистология", "🦴 Анатомия"), ("🧪 Биохимия", "⚡ Физиология"),
        ("🏥 Ішкі аурулар", "🔥 Патфиз"), ("🔭 Патанат", "🗺 Топанат"),
        ("💊 Фармакология", "🦠 Микробиология"), ("🧬 Генетика", "⚗️ Биофизика"),
        ("📜 Тарих", "✂️ Хирургия"),
    ],
    "ru": [
        ("🔬 Гистология", "🦴 Анатомия"), ("🧪 Биохимия", "⚡ Физиология"),
        ("🏥 Внутренние болезни", "🔥 Патофизиология"), ("🔭 Патанатомия", "🗺 Топографическая анатомия"),
        ("💊 Фармакология", "🦠 Микробиология"), ("🧬 Генетика", "⚗️ Биофизика"),
        ("📜 История Казахстана", "✂️ Хирургия"),
    ],
    "en": [
        ("🔬 Histology", "🦴 Anatomy"), ("🧪 Biochemistry", "⚡ Physiology"),
        ("🏥 Internal Medicine", "🔥 Pathophysiology"), ("🔭 Pathoanatomy", "🗺 Topographic Anatomy"),
        ("💊 Pharmacology", "🦠 Microbiology"), ("🧬 Genetics", "⚗️ Biophysics"),
        ("📜 Kazakhstan History", "✂️ Surgery"),
    ],
}


def main_menu_keyboard(lang="kz"):
    """Нижняя клавиатура: быстрые действия СВЕРХУ (их нажимают чаще всего), потом 14 предметов."""
    lang = _lang(lang)
    L = lambda key: KeyboardButton(text=LABELS[key][lang])          # noqa: E731
    rows = [
        [L("popular"), L("favorites")],
        [L("random"), L("history")],
    ]
    rows += [[KeyboardButton(text=a), KeyboardButton(text=b)] for a, b in _KEYBOARD_SUBJECTS[lang]]
    rows.append([L("profile"), L("upload")])
    rows.append([L("menu"), L("lang"), L("help")])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=True,                       # клавиатура не пропадает, пока пользователь сам не скроет
        input_field_placeholder=PLACEHOLDER[lang],
    )


# Совместимость со старыми вызовами; новые сообщения используют клавиатуру по языку.
main_menu = main_menu_keyboard("kz")


def subject_inline(code, lang="ru"):
    """Меню предмета: Книги / Силлабус / Лекции / Препараты / Видео — на языке пользователя."""
    lang = _lang(lang)
    rows = [[
        InlineKeyboardButton(text=tl(lang, "btn_books"), callback_data=f"books_{code}"),
        InlineKeyboardButton(text=tl(lang, "btn_syllabus"), callback_data=f"silabus_{code}"),
    ]]
    row2 = [InlineKeyboardButton(text=tl(lang, "btn_lecture"), callback_data=f"lektsiya_{code}")]
    if code not in NO_PREPARATY:
        row2.append(InlineKeyboardButton(text=tl(lang, "btn_preps"), callback_data=f"preparaty_{code}"))
    rows.append(row2)
    if code in VIDEO_SUBJECTS:
        rows.append([InlineKeyboardButton(text=tl(lang, "btn_video"), callback_data=f"video_{code}")])
    rows.append([
        menu_button(lang),
        InlineKeyboardButton(text=tl(lang, "btn_channel"), url=CHANNEL_URL),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def coming_soon_inline(back_code, lang="ru"):
    return InlineKeyboardMarkup(inline_keyboard=[back_menu_row(lang, f"subject_{back_code}")])


def start_inline(lang="kz"):
    """Кнопки под приветствием: быстрые действия, 8 основных предметов, язык и канал."""
    SUBJECT_LABELS = {
        "kz": ["🔬 Гистология", "🦴 Анатомия", "🧪 Биохимия", "⚡ Физиология",
               "🏥 Ішкі аурулар", "🔥 Патфиз", "🔭 Патанат", "🗺 Топанат"],
        "ru": ["🔬 Гистология", "🦴 Анатомия", "🧪 Биохимия", "⚡ Физиология",
               "🏥 Внутр. болезни", "🔥 Патфиз", "🔭 Патанат", "🗺 Топанат"],
        "en": ["🔬 Histology", "🦴 Anatomy", "🧪 Biochemistry", "⚡ Physiology",
               "🏥 Internal Med.", "🔥 Pathophysiology", "🔭 Pathoanatomy", "🗺 Topographic Anat."],
    }
    all_sections = {"kz": "📂 Барлық бөлімдер", "ru": "📂 Все разделы", "en": "📂 All sections"}
    codes = ["gistologiya", "anatomiya", "biohimiya", "fiziologiya",
             "ishki", "patfiz", "patanat", "toanat"]
    lang = _lang(lang)
    labels = SUBJECT_LABELS[lang]

    rows = [[
        InlineKeyboardButton(text=LABELS["popular"][lang], callback_data="go_popular"),
        InlineKeyboardButton(text=LABELS["favorites"][lang], callback_data="go_fav"),
    ], [
        InlineKeyboardButton(text=LABELS["random"][lang], callback_data="go_random"),
        InlineKeyboardButton(text=LABELS["profile"][lang], callback_data="go_profile"),
    ]]
    for i in range(0, 8, 2):
        rows.append([
            InlineKeyboardButton(text=labels[i],   callback_data=f"subject_{codes[i]}"),
            InlineKeyboardButton(text=labels[i+1], callback_data=f"subject_{codes[i+1]}"),
        ])
    # Раньше кнопка была только при наличии разделов из хэштегов, и 6 предметов из 14
    # (фармакология, микробиология…) из этого меню было не открыть. Теперь каталог есть всегда.
    rows.append([InlineKeyboardButton(text=all_sections[lang], callback_data="catalog_open")])
    bottom = [InlineKeyboardButton(text=LABELS["lang"][lang], callback_data="go_lang")]
    if BOT_INFO["inline"]:
        bottom.append(InlineKeyboardButton(text=tl(lang, "btn_search_inline"), switch_inline_query=""))
    rows.append(bottom)
    rows.append([InlineKeyboardButton(text=tl(lang, "btn_channel") + " @library_adasan", url=CHANNEL_URL)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def lang_select_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇰🇿 Қазақ тілі", callback_data="setlang_kz")],
        [InlineKeyboardButton(text="🇷🇺 Русский",    callback_data="setlang_ru")],
        [InlineKeyboardButton(text="🇬🇧 English",    callback_data="setlang_en")],
    ])


def subscribe_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📌 Каналға жазылу · Подписаться · Subscribe", url=CHANNEL_URL)],
        [InlineKeyboardButton(text="✅ Жазылдым · Подписался · Done", callback_data="check_sub")],
    ])


# =========================
# CALLBACK — Видеоуроки
# =========================
def anat_video_inline(lang="ru"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🦴 Остеология", url="https://t.me/library_adasan/473"),
         InlineKeyboardButton(text="💀 Топография черепа", url="https://t.me/library_adasan/363")],
        [InlineKeyboardButton(text="💀 Самай сүйек", url="https://t.me/library_adasan/354"),
         InlineKeyboardButton(text="💪 Қол бұлшықеті", url="https://t.me/library_adasan/369")],
        [InlineKeyboardButton(text="💪 Арқа бұлшықеті", url="https://t.me/library_adasan/368"),
         InlineKeyboardButton(text="💪 Мойын бұлшықеті", url="https://t.me/library_adasan/367")],
        [InlineKeyboardButton(text="🦵 Аяқ буыны", url="https://t.me/library_adasan/366"),
         InlineKeyboardButton(text="🦵 Шықшыт буыны", url="https://t.me/library_adasan/364")],
        back_menu_row(lang, "subject_anatomiya"),
    ])
