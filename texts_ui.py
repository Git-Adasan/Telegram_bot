"""Тексты нового интерфейса (HTML, parse_mode="HTML") на трёх языках.

Подключаются в texts.py через UI.update(NEW_UI). Чтобы поменять надпись — меняйте здесь.
В текстах с HTML любые имена и названия файлов подставляйте через esc() из texts.py.
"""

NEW_UI = {
    # --- общие кнопки ---
    "btn_back":     {"kz": "⬅️ Артқа", "ru": "⬅️ Назад", "en": "⬅️ Back"},
    "btn_menu":     {"kz": "🏠 Мәзір", "ru": "🏠 Меню", "en": "🏠 Menu"},
    "btn_channel":  {"kz": "📌 Арна", "ru": "📌 Канал", "en": "📌 Channel"},
    "btn_download": {"kz": "📥 Жүктеу", "ru": "📥 Скачать", "en": "📥 Download"},
    "btn_share":    {"kz": "📤 Бөлісу", "ru": "📤 Поделиться", "en": "📤 Share"},
    "btn_books":    {"kz": "📚 Кітаптар", "ru": "📚 Книги", "en": "📚 Books"},
    "btn_syllabus": {"kz": "📋 Силлабус", "ru": "📋 Силлабус", "en": "📋 Syllabus"},
    "btn_lecture":  {"kz": "🎓 Дәрістер", "ru": "🎓 Лекции", "en": "🎓 Lectures"},
    "btn_preps":    {"kz": "🔬 Препараттар", "ru": "🔬 Препараты", "en": "🔬 Slides"},
    "btn_video":    {"kz": "🎬 Бейнесабақтар", "ru": "🎬 Видеоуроки", "en": "🎬 Video lessons"},
    "btn_more_random":   {"kz": "🎲 Тағы біреу", "ru": "🎲 Ещё одну", "en": "🎲 Another one"},
    "btn_clear_history": {"kz": "🧹 Тарихты тазалау", "ru": "🧹 Очистить историю", "en": "🧹 Clear history"},
    "btn_feedback": {"kz": "💬 Админге жазу", "ru": "💬 Написать админу", "en": "💬 Message the admin"},
    "btn_cancel":   {"kz": "✖️ Бас тарту", "ru": "✖️ Отмена", "en": "✖️ Cancel"},
    "btn_lang":     {"kz": "🌐 Тілді ауыстыру", "ru": "🌐 Сменить язык", "en": "🌐 Change language"},
    "btn_help":     {"kz": "ℹ️ Көмек", "ru": "ℹ️ Помощь", "en": "ℹ️ Help"},
    "btn_search_inline": {"kz": "🔎 Кез келген чатта іздеу", "ru": "🔎 Искать в любом чате", "en": "🔎 Search in any chat"},

    # --- приветствие / меню ---
    "welcome": {
        "kz": ("╔══════════════════════╗\n   👋 <b>Сәлем, {name}!</b>\n╚══════════════════════╝\n\n"
               "🏥 <b>Adasan Medical Library</b> — медициналық кітапхана\n\n"
               "📚 Кітаптар  ·  📋 Силлабустар\n🎓 Дәрістер  ·  🔬 Препараттар\n\n"
               "<blockquote>🔎 Кітаптың немесе пәннің атын жаза беріңіз — қатесі болса да табамын.</blockquote>\n"
               "👇 Пәнді таңдаңыз:"),
        "ru": ("╔══════════════════════╗\n   👋 <b>Привет, {name}!</b>\n╚══════════════════════╝\n\n"
               "🏥 <b>Adasan Medical Library</b> — медицинская библиотека\n\n"
               "📚 Книги  ·  📋 Силлабусы\n🎓 Лекции  ·  🔬 Препараты\n\n"
               "<blockquote>🔎 Просто напишите название книги или предмета — найду даже с опечатками.</blockquote>\n"
               "👇 Выберите предмет:"),
        "en": ("╔══════════════════════╗\n   👋 <b>Hello, {name}!</b>\n╚══════════════════════╝\n\n"
               "🏥 <b>Adasan Medical Library</b> — medical library\n\n"
               "📚 Books  ·  📋 Syllabi\n🎓 Lectures  ·  🔬 Slides\n\n"
               "<blockquote>🔎 Just type a book or subject name — I'll find it even with typos.</blockquote>\n"
               "👇 Choose a subject:"),
    },
    "lang_saved": {"kz": "✅ Қазақ тілі таңдалды", "ru": "✅ Выбран русский язык", "en": "✅ English selected"},
    "keyboard_ready": {
        "kz": "⌨️ Төмендегі мәзір дайын 👇",
        "ru": "⌨️ Меню внизу обновлено 👇",
        "en": "⌨️ The menu below is ready 👇",
    },

    # --- предмет ---
    "subject_menu": {
        "kz": "╔══════════════════════╗\n   <b>{name}</b>\n╚══════════════════════╝\n\n📚 Кітаптар: <b>{n}</b>\n\n👇 Бөлімді таңдаңыз:",
        "ru": "╔══════════════════════╗\n   <b>{name}</b>\n╚══════════════════════╝\n\n📚 Книг: <b>{n}</b>\n\n👇 Выберите раздел:",
        "en": "╔══════════════════════╗\n   <b>{name}</b>\n╚══════════════════════╝\n\n📚 Books: <b>{n}</b>\n\n👇 Choose a section:",
    },
    "books_choose_lang": {
        "kz": "╔══════════════════════╗\n   <b>📚 {name}</b>\n╚══════════════════════╝\n\nБарлығы: <b>{n}</b> кітап\n\n👇 Кітаптардың тілін таңдаңыз:",
        "ru": "╔══════════════════════╗\n   <b>📚 {name}</b>\n╚══════════════════════╝\n\nВсего: <b>{n}</b> книг\n\n👇 Выберите язык книг:",
        "en": "╔══════════════════════╗\n   <b>📚 {name}</b>\n╚══════════════════════╝\n\nTotal: <b>{n}</b> books\n\n👇 Choose the book language:",
    },
    "coming_soon": {
        "kz": "<b>{name}</b> — {section}\n\n⏳ Жақында қосылады!\n<i>Әзірге кітап атын жазып іздеп көріңіз.</i>",
        "ru": "<b>{name}</b> — {section}\n\n⏳ Скоро будет доступно!\n<i>Пока можно поискать книгу по названию.</i>",
        "en": "<b>{name}</b> — {section}\n\n⏳ Coming soon!\n<i>Meanwhile, try searching a book by its title.</i>",
    },
    "section_card": {
        "kz": "╔══════════════════════╗\n   <b>{section}</b>\n╚══════════════════════╝\n\n📖 Пән: <b>{name}</b>\n\n{body}\n\n👇 Ашу үшін батырманы басыңыз:",
        "ru": "╔══════════════════════╗\n   <b>{section}</b>\n╚══════════════════════╝\n\n📖 Предмет: <b>{name}</b>\n\n{body}\n\n👇 Нажмите кнопку, чтобы открыть:",
        "en": "╔══════════════════════╗\n   <b>{section}</b>\n╚══════════════════════╝\n\n📖 Subject: <b>{name}</b>\n\n{body}\n\n👇 Tap the button to open:",
    },
    "body_syllabus": {
        "kz": "• Пәннің мақсаты мен міндеттері\n• Тақырыптар тізімі\n• Баға критерийлері\n• Әдебиеттер тізімі",
        "ru": "• Цели и задачи предмета\n• Список тем\n• Критерии оценки\n• Список литературы",
        "en": "• Course goals\n• List of topics\n• Grading criteria\n• Reading list",
    },
    "body_lecture_gist": {
        "kz": "• Толық лекция конспектілері\n• Схемалар мен кестелер\n• Емтиханға дайындық",
        "ru": "• Полные конспекты лекций\n• Схемы и таблицы\n• Подготовка к экзамену",
        "en": "• Full lecture notes\n• Diagrams and tables\n• Exam preparation",
    },
    "body_lecture_tarih": {
        "kz": "• 1-ден 15-ке дейінгі тақырыптар\n• Барлық лекциялар бір жерде",
        "ru": "• Темы с 1 по 15\n• Все лекции в одном месте",
        "en": "• Topics 1 to 15\n• All lectures in one place",
    },
    "body_preps": {
        "kz": "• Микроскопиялық препараттар\n• Атлас суреттері мен сипаттамасы\n• Практикалық сабаққа дайындық",
        "ru": "• Микроскопические препараты\n• Снимки атласа и описания\n• Подготовка к практическим",
        "en": "• Microscopic slides\n• Atlas images and descriptions\n• Practical class preparation",
    },
    "body_video_anat": {
        "kz": "🦴 Остеология · 💀 Бас сүйек\n💪 Миология · 🦵 Синдесмология",
        "ru": "🦴 Остеология · 💀 Череп\n💪 Миология · 🦵 Синдесмология",
        "en": "🦴 Osteology · 💀 Skull\n💪 Myology · 🦵 Syndesmology",
    },
    "body_video_surg": {
        "kz": "📹 Хирургиялық техникалар — арнада",
        "ru": "📹 Хирургические техники — в канале",
        "en": "📹 Surgical techniques — in the channel",
    },

    # --- карточка книги ---
    "book_card": {
        "kz": "╔══════════════════════╗\n   📖 <b>{title}</b>\n╚══════════════════════╝\n\n📚 Пән: {subject}\n🌐 Тіл: {lang}{extra}\n\n━━━━━━━━━━━━━━━━━━━━━━\n📌 @library_adasan",
        "ru": "╔══════════════════════╗\n   📖 <b>{title}</b>\n╚══════════════════════╝\n\n📚 Предмет: {subject}\n🌐 Язык: {lang}{extra}\n\n━━━━━━━━━━━━━━━━━━━━━━\n📌 @library_adasan",
        "en": "╔══════════════════════╗\n   📖 <b>{title}</b>\n╚══════════════════════╝\n\n📚 Subject: {subject}\n🌐 Language: {lang}{extra}\n\n━━━━━━━━━━━━━━━━━━━━━━\n📌 @library_adasan",
    },
    "list_header_html": {
        "kz": "<b>{name}</b> · {lang}\n━━━━━━━━━━━━━━━\n📚 {n} кітап{page}\n\n👇 Кітапты таңдаңыз:",
        "ru": "<b>{name}</b> · {lang}\n━━━━━━━━━━━━━━━\n📚 Книг: {n}{page}\n\n👇 Выберите книгу:",
        "en": "<b>{name}</b> · {lang}\n━━━━━━━━━━━━━━━\n📚 {n} books{page}\n\n👇 Choose a book:",
    },
    "list_page": {"kz": " · бет {p}/{t}", "ru": " · стр. {p}/{t}", "en": " · page {p}/{t}"},

    # --- избранное ---
    "fav_empty": {
        "kz": "⭐ <b>Таңдаулылар</b>\n\nӘзірге бос. Кітап карточкасын ашып, ⭐ батырмасын басыңыз.",
        "ru": "⭐ <b>Избранное</b>\n\nПока пусто. Откройте карточку книги и нажмите ⭐ «В избранное».",
        "en": "⭐ <b>Favorites</b>\n\nEmpty for now. Open a book card and tap ⭐ “Add to favorites”.",
    },
    "fav_caption": {
        "kz": "⭐ <b>Таңдаулылар</b> · {n}\n<i>📖 — ашу, 🗑 — өшіру</i>",
        "ru": "⭐ <b>Избранное</b> · {n}\n<i>📖 — открыть, 🗑 — удалить</i>",
        "en": "⭐ <b>Favorites</b> · {n}\n<i>📖 — open, 🗑 — remove</i>",
    },
    "fav_stale": {
        "kz": "Кітап өшірілген немесе тізім ескірген. Таңдаулыларды қайта ашыңыз.",
        "ru": "Книга уже удалена или список устарел. Откройте избранное заново.",
        "en": "Already removed or the list is outdated. Open favorites again.",
    },

    # --- история ---
    "history_empty": {
        "kz": "📖 <b>Тарих бос</b>\n\nАшқан кітаптарыңыз осында көрінеді.",
        "ru": "📖 <b>История пуста</b>\n\nЗдесь появятся книги, которые вы открывали.",
        "en": "📖 <b>History is empty</b>\n\nBooks you open will appear here.",
    },
    "history_title": {
        "kz": "📖 <b>Соңғы ашылған кітаптар</b> · {n}",
        "ru": "📖 <b>Недавно открытые книги</b> · {n}",
        "en": "📖 <b>Recently opened books</b> · {n}",
    },
    "history_cleared": {"kz": "🧹 Тарих тазаланды", "ru": "🧹 История очищена", "en": "🧹 History cleared"},

    # --- прочее ---
    "unknown_cmd": {
        "kz": "🤔 Мұндай команда жоқ. Барлық мүмкіндіктер: /help",
        "ru": "🤔 Такой команды нет. Все возможности: /help",
        "en": "🤔 Unknown command. See everything I can do: /help",
    },
    "too_long": {
        "kz": "🔎 Сұраныс тым ұзын. Қысқарақ жазыңыз (200 таңбаға дейін).",
        "ru": "🔎 Слишком длинный запрос. Напишите короче (до 200 символов).",
        "en": "🔎 The query is too long. Please keep it under 200 characters.",
    },
    "mat_warning": {
        "kz": "⚠️ Өтініш, боқтамаңыз. Қайталанса — бот сізді бұғаттайды.",
        "ru": "⚠️ Пожалуйста, без мата. При повторе бот заблокирует доступ.",
        "en": "⚠️ Please, no profanity. If it happens again, access will be blocked.",
    },
    "subscribe_first": {
        "kz": "🔒 Ботты пайдалану үшін біздің арнаға жазылыңыз, содан кейін «Жазылдым» батырмасын басыңыз.",
        "ru": "🔒 Чтобы пользоваться ботом, подпишитесь на наш канал и нажмите «Подписался».",
        "en": "🔒 To use the bot, subscribe to our channel and then tap “I subscribed”.",
    },

    # --- профиль ---
    "profile": {
        "kz": ("╔══════════════════════╗\n   👤 <b>Менің профилім</b>\n╚══════════════════════╝\n\n"
               "🌐 Тіл: {lang}\n📅 Ботта: {since} бастап · {days} күн\n\n"
               "📖 Ашылған кітаптар: <b>{opened}</b>\n⭐ Таңдаулылар: <b>{favs}</b>\n"
               "🔎 Іздеулер: <b>{searches}</b>\n👍 Бағалар: <b>{votes}</b>\n🔔 Күтілетін кітаптар: <b>{wishes}</b>\n\n"
               "{badge}"),
        "ru": ("╔══════════════════════╗\n   👤 <b>Мой профиль</b>\n╚══════════════════════╝\n\n"
               "🌐 Язык: {lang}\n📅 В боте с {since} · {days} дн.\n\n"
               "📖 Открыто книг: <b>{opened}</b>\n⭐ В избранном: <b>{favs}</b>\n"
               "🔎 Поисков: <b>{searches}</b>\n👍 Оценок: <b>{votes}</b>\n🔔 Жду книг: <b>{wishes}</b>\n\n"
               "{badge}"),
        "en": ("╔══════════════════════╗\n   👤 <b>My profile</b>\n╚══════════════════════╝\n\n"
               "🌐 Language: {lang}\n📅 With the bot since {since} · {days} days\n\n"
               "📖 Books opened: <b>{opened}</b>\n⭐ Favorites: <b>{favs}</b>\n"
               "🔎 Searches: <b>{searches}</b>\n👍 Ratings: <b>{votes}</b>\n🔔 Waiting for books: <b>{wishes}</b>\n\n"
               "{badge}"),
    },
    "badge_0": {"kz": "🌱 Деңгей: <b>Жаңадан бастаушы</b>", "ru": "🌱 Уровень: <b>Новичок</b>", "en": "🌱 Level: <b>Newcomer</b>"},
    "badge_1": {"kz": "📗 Деңгей: <b>Оқырман</b>", "ru": "📗 Уровень: <b>Читатель</b>", "en": "📗 Level: <b>Reader</b>"},
    "badge_2": {"kz": "📘 Деңгей: <b>Белсенді студент</b>", "ru": "📘 Уровень: <b>Активный студент</b>", "en": "📘 Level: <b>Active student</b>"},
    "badge_3": {"kz": "🏆 Деңгей: <b>Кітап құмар</b>", "ru": "🏆 Уровень: <b>Книжный марафонец</b>", "en": "🏆 Level: <b>Bookworm</b>"},
    "badge_next": {
        "kz": "\n<i>Келесі деңгейге дейін: {left} кітап</i>",
        "ru": "\n<i>До следующего уровня: {left} книг</i>",
        "en": "\n<i>To the next level: {left} books</i>",
    },

    # --- случайная книга ---
    "random_head": {
        "kz": "🎲 <b>Кездейсоқ кітап</b> — бүгін осыны оқып көріңіз 👇",
        "ru": "🎲 <b>Случайная книга</b> — попробуйте почитать сегодня 👇",
        "en": "🎲 <b>Random book</b> — give this one a try today 👇",
    },
    "random_empty": {"kz": "📭 Кітапхана әлі бос.", "ru": "📭 Библиотека пока пуста.", "en": "📭 The library is empty for now."},

    # --- отзыв ---
    "feedback_prompt": {
        "kz": "💬 <b>Пікір немесе ұсыныс</b>\n\nБір хабарламамен жазыңыз — админге жіберемін.\n<i>Мысалы: қандай кітап қосу керек, не ыңғайсыз.</i>",
        "ru": "💬 <b>Отзыв или идея</b>\n\nНапишите одним сообщением — я передам администратору.\n<i>Например: какую книгу добавить или что неудобно.</i>",
        "en": "💬 <b>Feedback or idea</b>\n\nWrite it in one message — I'll pass it to the admin.\n<i>For example: which book to add or what is inconvenient.</i>",
    },
    "feedback_sent": {
        "kz": "✅ Рахмет! Хабарламаңыз админге жіберілді.",
        "ru": "✅ Спасибо! Сообщение отправлено администратору.",
        "en": "✅ Thank you! Your message was sent to the admin.",
    },
    "feedback_cancel": {"kz": "Жақсы, болдырмадық.", "ru": "Хорошо, отменили.", "en": "Okay, cancelled."},
    "feedback_reply": {
        "kz": "📩 <b>Админнен жауап:</b>\n\n{text}",
        "ru": "📩 <b>Ответ администратора:</b>\n\n{text}",
        "en": "📩 <b>Reply from the admin:</b>\n\n{text}",
    },
    "feedback_cooldown": {
        "kz": "⏳ Келесі хабарламаны бір минуттан кейін жіберуге болады.",
        "ru": "⏳ Следующее сообщение можно отправить через минуту.",
        "en": "⏳ You can send the next message in a minute.",
    },

    # --- inline-режим ---
    "inline_nf": {"kz": "Ештеңе табылмады", "ru": "Ничего не найдено", "en": "Nothing found"},
    "inline_nf_desc": {
        "kz": "Басқаша жазып көріңіз немесе ботты ашыңыз",
        "ru": "Попробуйте написать иначе или откройте бота",
        "en": "Try different words or open the bot",
    },
    "inline_hint": {"kz": "🔎 Кітап атын жазыңыз", "ru": "🔎 Напишите название книги", "en": "🔎 Type a book title"},
}


HELP_TEXTS = {
    "kz": (
        "╔══════════════════════╗\n   ℹ️ <b>Боттың қолданылуы</b>\n╚══════════════════════╝\n\n"
        "🔎 Кітаптың немесе пәннің атын жазыңыз — қатесі болса да табамын.\n"
        "📚 Немесе төмендегі батырмалардан пәнді таңдаңыз.\n\n"
        "<b>Командалар</b>\n"
        "🏠 /menu — басты мәзір\n"
        "🔥 /popular — ең көп ашылған кітаптар\n"
        "🏆 /top5 — пәндер бойынша үздік 5\n"
        "📂 /catalog — барлық бөлімдер\n"
        "🎲 /random — кездейсоқ кітап\n"
        "⭐ /favorites — таңдаулылар\n"
        "📖 /history — соңғы ашылған кітаптар\n"
        "👤 /profile — менің профилім\n"
        "📤 /upload — материал жіберу\n"
        "💬 /feedback — админге жазу\n"
        "🌐 /lang — тілді ауыстыру\n\n"
        "<blockquote>💡 Кез келген чатта <code>@{bot} анатомия</code> деп жазып, кітаппен бөлісуге болады.</blockquote>\n"
        "📌 Арна: @library_adasan"
    ),
    "ru": (
        "╔══════════════════════╗\n   ℹ️ <b>Как пользоваться ботом</b>\n╚══════════════════════╝\n\n"
        "🔎 Напишите название книги или предмета — найду, даже если есть опечатки.\n"
        "📚 Или выберите предмет кнопками внизу.\n\n"
        "<b>Команды</b>\n"
        "🏠 /menu — главное меню\n"
        "🔥 /popular — самые открываемые книги\n"
        "🏆 /top5 — топ-5 по предметам\n"
        "📂 /catalog — все разделы\n"
        "🎲 /random — случайная книга\n"
        "⭐ /favorites — избранное\n"
        "📖 /history — недавно открытые книги\n"
        "👤 /profile — мой профиль\n"
        "📤 /upload — прислать свой материал\n"
        "💬 /feedback — написать администратору\n"
        "🌐 /lang — сменить язык\n\n"
        "<blockquote>💡 В любом чате напишите <code>@{bot} анатомия</code> — и поделитесь книгой с друзьями.</blockquote>\n"
        "📌 Канал: @library_adasan"
    ),
    "en": (
        "╔══════════════════════╗\n   ℹ️ <b>How to use the bot</b>\n╚══════════════════════╝\n\n"
        "🔎 Type a book or subject name — I'll find it, even with typos.\n"
        "📚 Or pick a subject with the buttons below.\n\n"
        "<b>Commands</b>\n"
        "🏠 /menu — main menu\n"
        "🔥 /popular — most opened books\n"
        "🏆 /top5 — top-5 by subject\n"
        "📂 /catalog — all sections\n"
        "🎲 /random — random book\n"
        "⭐ /favorites — favorites\n"
        "📖 /history — recently opened books\n"
        "👤 /profile — my profile\n"
        "📤 /upload — send your own material\n"
        "💬 /feedback — message the admin\n"
        "🌐 /lang — change language\n\n"
        "<blockquote>💡 In any chat type <code>@{bot} anatomy</code> to share a book with friends.</blockquote>\n"
        "📌 Channel: @library_adasan"
    ),
}
