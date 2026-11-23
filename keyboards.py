"""Базовые клавиатуры: главное меню, меню предмета, выбор языка, кнопка подписки."""

from aiogram.types import InlineKeyboardButton
from aiogram.types import InlineKeyboardMarkup
from aiogram.types import KeyboardButton
from aiogram.types import ReplyKeyboardMarkup

from books import _DYN_NAMES
from buttons import LABELS, PLACEHOLDER
from subjects import NO_PREPARATY

CHANNEL_URL = "https://t.me/library_adasan"


def menu_button():
    """Кнопка «🏠 Меню» — одна на весь бот (раньше текст был скопирован в 25 местах)."""
    return InlineKeyboardButton(text="🏠 Мәзір · Меню · Menu", callback_data="go_main_menu")



# =========================
# КЛАВИАТУРЫ
# =========================
def main_menu_keyboard(lang="kz"):
    """Нижняя клавиатура: 14 предметов (на языке интерфейса) + строки быстрых действий."""
    labels = {
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
    lang = lang if lang in labels else "ru"
    rows = [[KeyboardButton(text=a), KeyboardButton(text=b)] for a, b in labels[lang]]
    # Быстрые действия (надписи — в buttons.py, там же их понимают обработчики)
    rows.append([KeyboardButton(text=LABELS["popular"][lang]), KeyboardButton(text=LABELS["favorites"][lang])])
    rows.append([KeyboardButton(text=LABELS["history"][lang]), KeyboardButton(text=LABELS["upload"][lang])])
    rows.append([KeyboardButton(text=LABELS["menu"][lang]), KeyboardButton(text=LABELS["lang"][lang])])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=True,                       # клавиатура не пропадает, пока пользователь сам не скроет
        input_field_placeholder=PLACEHOLDER[lang],
    )

# Совместимость со старыми вызовами; новые сообщения используют клавиатуру по языку.
main_menu = main_menu_keyboard("kz")

def subject_inline(code):
    VIDEO_SUBJECTS = {"anatomiya", "hirurgiya"}
    rows = []

    # Строка 1: Книги + Силлабус
    rows.append([
        InlineKeyboardButton(text="📚 Кітаптар / Книги / Books", callback_data=f"books_{code}"),
        InlineKeyboardButton(text="📋 Силлабус", callback_data=f"silabus_{code}"),
    ])

    # Строка 2: Лекция + Препараты (если есть)
    row2 = [InlineKeyboardButton(text="🎓 Дәріс / Лекция / Lecture", callback_data=f"lektsiya_{code}")]
    if code not in NO_PREPARATY:
        row2.append(InlineKeyboardButton(text="🔬 Препараттар / Препараты", callback_data=f"preparaty_{code}"))
    rows.append(row2)

    if code in VIDEO_SUBJECTS:
        rows.append([InlineKeyboardButton(text="🎬 Бейнесабақ / Видеоурок", callback_data=f"video_{code}")])

    rows.append([
        menu_button(),
        InlineKeyboardButton(text="📌 Канал", url="https://t.me/library_adasan"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def coming_soon_inline(back_code):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅ Артқа / Назад / Back", callback_data=f"subject_{back_code}")],
        [menu_button()],
    ])

def start_inline(lang="kz"):
    """Кнопки под приветствием: быстрые действия, 8 основных предметов, язык и канал."""
    SUBJECT_LABELS = {
        "kz": ["🔬 Гистология", "🦴 Анатомия", "🧪 Биохимия", "⚡ Физиология",
               "🏥 Ішкі аурулар", "🔥 Патфиз", "🔭 Патанат", "🗺 Топанат"],
        "ru": ["🔬 Гистология", "🦴 Анатомия", "🧪 Биохимия", "⚡ Физиология",
               "🏥 Внутр. болезни", "🔥 Патфиз", "🔭 Патанат", "🗺 Топанат"],
        "en": ["🔬 Histology", "🦴 Anatomy", "🧪 Biochemistry", "⚡ Physiology",
               "🏥 Internal Medicine", "🔥 Pathophysiology", "🔭 Pathoanatomy", "🗺 Topographic Anat."],
    }
    more_sections = {"kz": "📂 Қосымша бөлімдер", "ru": "📂 Ещё разделы", "en": "📂 More sections"}
    codes = ["gistologiya", "anatomiya", "biohimiya", "fiziologiya",
             "ishki", "patfiz", "patanat", "toanat"]
    lang = lang if lang in SUBJECT_LABELS else "kz"
    labels = SUBJECT_LABELS[lang]

    rows = [[
        InlineKeyboardButton(text=LABELS["popular"][lang], callback_data="go_popular"),
        InlineKeyboardButton(text=LABELS["favorites"][lang], callback_data="go_fav"),
    ]]
    for i in range(0, 8, 2):
        rows.append([
            InlineKeyboardButton(text=labels[i],   callback_data=f"subject_{codes[i]}"),
            InlineKeyboardButton(text=labels[i+1], callback_data=f"subject_{codes[i+1]}"),
        ])
    if _DYN_NAMES:                      # разделы из хэштегов канала — только если они есть
        rows.append([InlineKeyboardButton(text=more_sections[lang], callback_data="catalog_open")])
    rows.append([
        InlineKeyboardButton(text=LABELS["lang"][lang], callback_data="go_lang"),
        InlineKeyboardButton(text="📌 Канал", url=CHANNEL_URL),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def lang_select_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇰🇿 Қазақ тілі", callback_data="setlang_kz")],
        [InlineKeyboardButton(text="🇷🇺 Русский",    callback_data="setlang_ru")],
        [InlineKeyboardButton(text="🇬🇧 English",    callback_data="setlang_en")],
    ])

def subscribe_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📌 Каналға жазылу / Подписаться", url="https://t.me/library_adasan")],
        [InlineKeyboardButton(text="✅ Жазылдым! / Подписался!", callback_data="check_sub")],
    ])

# =========================
# CALLBACK — Видеоуроки
# =========================
def anat_video_inline():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🦴 Остеология", url="https://t.me/library_adasan/473")],
        [InlineKeyboardButton(text="💀 Топография черепа", url="https://t.me/library_adasan/363")],
        [InlineKeyboardButton(text="💀 Самай сүйек", url="https://t.me/library_adasan/354")],
        [InlineKeyboardButton(text="💪 Қол бұлшықеті", url="https://t.me/library_adasan/369")],
        [InlineKeyboardButton(text="💪 Арқа бұлшықеті", url="https://t.me/library_adasan/368")],
        [InlineKeyboardButton(text="💪 Мойын бұлшықеті", url="https://t.me/library_adasan/367")],
        [InlineKeyboardButton(text="🦵 Синдесмология аяқ буыны", url="https://t.me/library_adasan/366")],
        [InlineKeyboardButton(text="🦵 Шықшыт буыны", url="https://t.me/library_adasan/364")],
        [InlineKeyboardButton(text="⬅ Артқа / Назад / Back", callback_data="subject_anatomiya")],
        [menu_button()],
    ])
