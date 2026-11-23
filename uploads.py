"""Материалы от студентов: настройки загрузки, состояние, клавиатуры модерации."""

from aiogram import types
from aiogram.types import InlineKeyboardButton
from aiogram.types import InlineKeyboardMarkup

from core import ADMIN_ID, bot, logger
from database import get_submission


SUBJECT_HASHTAGS = {
    "gistologiya": "#гистология", "anatomiya": "#анатомия", "biohimiya": "#биохимия",
    "fiziologiya": "#физиология", "ishki": "#ішкіаурулар", "patfiz": "#патфиз",
    "patanat": "#патанат", "toanat": "#топанат", "farmakologiya": "#фармакология",
    "mikrobiologiya": "#микробиология", "genetika": "#генетика", "biofizika": "#биофизика",
    "tarih": "#тарих", "hirurgiya": "#хирургия",
}

LANG_LABELS = {"rus": "🇷🇺 Русский", "kaz": "🇰🇿 Қазақша", "eng": "🇬🇧 English"}

LANG_CAPTION = {"rus": "Русский", "kaz": "Қазақша", "eng": "English"}

UPLOAD_EXT = (".pdf", ".doc", ".docx", ".ppt", ".pptx", ".txt", ".epub", ".djvu")

MAX_UPLOAD_BYTES = 45 * 1024 * 1024

UPLOAD_COOLDOWN_SECONDS = 3

MAX_PENDING_PER_USER = 5

_upload_state = set()  # user_id, которые нажали «Материал жіберу»

_upload_last_time = {}

# ---------- Материалы от студентов ----------
UPLOAD_CANCEL_KB = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="✖ Бас тарту / Отмена", callback_data="upl_cancel")]
])

async def start_upload(message: types.Message):
    if message.chat.type != "private":
        await message.answer("📤 Материалды бота жеке чатта жіберіңіз / Отправьте файл боту в личный чат.")
        return
    _upload_state.add(message.from_user.id)
    await message.answer(
        "📤 Конспект немесе шпаргалка жібергіңіз келе ме?\n"
        "Хотите поделиться конспектом или шпаргалкой?\n\n"
        "Файлды осы чатқа жіберіңіз / Отправьте файл в этот чат.\n"
        "Форматтар / Форматы: PDF, DOC(X), PPT(X), TXT, EPUB, DJVU\n\n"
        "Админ тексереді, содан кейін кітапханаға қосылады.\n"
        "Админ проверит файл, и он попадёт в библиотеку.",
        reply_markup=UPLOAD_CANCEL_KB
    )

def submission_admin_kb(sub_id):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Одобрить", callback_data=f"sbm_ok_{sub_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"sbm_no_{sub_id}"),
    ]])

def _parse_sub(callback, prefix):
    """Только админ; возвращает (sub, rest_parts) или (None, None)."""
    if callback.from_user.id != ADMIN_ID:
        return None, None
    parts = callback.data[len(prefix):].split("_")
    try:
        sub = get_submission(int(parts[0]))
    except ValueError:
        return None, None
    return sub, parts[1:]

async def _notify_user(user_id, text):
    try:
        await bot.send_message(user_id, text)
    except Exception as e:
        logger.warning(f"cannot notify {user_id}: {e}")
