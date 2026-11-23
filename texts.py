"""Тексты интерфейса на трёх языках (UI), функция tr() и приветствие."""

from database import get_lang


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

def tr(user_id, key, **kw):
    """Текст по языку пользователя. Если язык неизвестен — русский."""
    lang = get_lang(user_id) if user_id else "ru"
    if lang not in ("kz", "ru", "en"):
        lang = "ru"
    text = UI[key][lang]
    return text.format(**kw) if kw else text

# =========================
# ТЕКСТЫ ПРИВЕТСТВИЯ
# =========================
WELCOME_TEXTS = {
    "ru": (
        "╔══════════════════════╗\n"
        "   👋 Привет, {name}!\n"
        "╚══════════════════════╝\n\n"
        "🏥 Добро пожаловать в Adasan Medical Library!\n\n"
        "📖 Я помогу вам найти:\n"
        "    📚 Медицинские книги\n"
        "    📋 Силлабусы\n"
        "    🎓 Лекции\n"
        "    🔬 Препараты\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "👇 Выберите предмет или напишите\n"
        "📌 @library_adasan"
    ),
    "kz": (
        "╔══════════════════════╗\n"
        "   👋 Сәлем, {name}!\n"
        "╚══════════════════════╝\n\n"
        "🏥 Adasan Medical Library-ға қош келдіңіз!\n\n"
        "📖 Мен сізге табуға көмектесемін:\n"
        "    📚 Медициналық кітаптар\n"
        "    📋 Силлабустар\n"
        "    🎓 Лекциялар\n"
        "    🔬 Препараттар\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "👇 Пәнді таңдаңыз немесе жазыңыз\n"
        "📌 @library_adasan"
    ),
    "en": (
        "╔══════════════════════╗\n"
        "   👋 Hello, {name}!\n"
        "╚══════════════════════╝\n\n"
        "🏥 Welcome to Adasan Medical Library!\n\n"
        "📖 I can help you find:\n"
        "    📚 Medical books\n"
        "    📋 Syllabuses\n"
        "    🎓 Lectures\n"
        "    🔬 Preparations\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "👇 Choose a subject or type\n"
        "📌 @library_adasan"
    ),
}


# =========================
# СПРАВКА (/help)
# =========================
HELP_TEXTS = {
    "kz": (
        "ℹ️ Боттың қолданылуы\n\n"
        "🔎 Кітаптың немесе пәннің атын жазыңыз — қатесі болса да табамын.\n"
        "📚 Төмендегі батырмалардан пәнді таңдаңыз: кітаптар, силлабус, дәрістер.\n\n"
        "🔥 /popular — ең көп ашылған кітаптар\n"
        "⭐ /favorites — таңдаған кітаптарыңыз\n"
        "📖 /history — соңғы ашылған кітаптар\n"
        "📤 /upload — өз материалыңызды жіберу\n"
        "🌐 /lang — тілді ауыстыру\n"
        "🏠 /menu — басты мәзір\n\n"
        "📌 Арна: @library_adasan"
    ),
    "ru": (
        "ℹ️ Как пользоваться ботом\n\n"
        "🔎 Напишите название книги или предмета — найду, даже если есть опечатки.\n"
        "📚 Выберите предмет кнопками внизу: книги, силлабусы, лекции.\n\n"
        "🔥 /popular — самые открываемые книги\n"
        "⭐ /favorites — ваша подборка\n"
        "📖 /history — последние открытые книги\n"
        "📤 /upload — прислать свой материал\n"
        "🌐 /lang — сменить язык\n"
        "🏠 /menu — главное меню\n\n"
        "📌 Канал: @library_adasan"
    ),
    "en": (
        "ℹ️ How to use the bot\n\n"
        "🔎 Type a book or subject name — I will find it, even with typos.\n"
        "📚 Pick a subject with the buttons below: books, syllabi, lectures.\n\n"
        "🔥 /popular — most opened books\n"
        "⭐ /favorites — your collection\n"
        "📖 /history — recently opened books\n"
        "📤 /upload — send your own material\n"
        "🌐 /lang — change language\n"
        "🏠 /menu — main menu\n\n"
        "📌 Channel: @library_adasan"
    ),
}
