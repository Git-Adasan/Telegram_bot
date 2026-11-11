from aiogram import Bot, Dispatcher, types, BaseMiddleware, F
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile,
    ReplyKeyboardMarkup,
    KeyboardButton,
    TelegramObject,
)
import asyncio
import logging
import os
import sqlite3
import re
import time
from datetime import datetime
from dotenv import load_dotenv
from collections import defaultdict
from typing import Callable, Any

_LOG_LEVEL = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(
    level=_LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# =========================
# АНТИФЛУД
# =========================
_last_message_time = defaultdict(float)
_last_callback_time = defaultdict(float)

def is_flood(user_id: int) -> bool:
    now = time.time()
    if now - _last_message_time[user_id] < 5:
        return True
    _last_message_time[user_id] = now
    return False

def is_flood_callback(user_id: int) -> bool:
    now = time.time()
    if now - _last_callback_time[user_id] < 2:
        return True
    _last_callback_time[user_id] = now
    return False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(ENV_PATH, override=False)
if os.name != "nt":
    os.umask(0o077)
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID_RAW = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")

if not API_ID_RAW or not API_HASH:
    raise RuntimeError(
        f"API_ID или API_HASH не найдены. Проверь файл: {ENV_PATH}. "
        "В нём должны быть строки API_ID=... и API_HASH=... (имя файла именно .env, не .env.txt)."
    )

try:
    API_ID = int(API_ID_RAW.strip())
except ValueError as exc:
    raise RuntimeError("API_ID должен быть числом. Проверь строку API_ID в .env") from exc

# =========================
# ADMIN
# =========================
ADMIN_ID_RAW = os.getenv("ADMIN_ID", "6277436867").strip()
try:
    ADMIN_ID = int(ADMIN_ID_RAW)
    if ADMIN_ID <= 0:
        raise ValueError
except ValueError as exc:
    raise RuntimeError("ADMIN_ID должен быть положительным Telegram ID.") from exc
ADMIN_URL   = "https://t.me/Tg_Adasan"
ADMIN_NAME  = "@Tg_Adasan"
CHANNEL     = "@library_adasan"

# =========================
# БД
# =========================
DB_PATH = os.getenv("DB_PATH") or os.path.join(BASE_DIR, "adasan.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        lang TEXT DEFAULT 'ru',
        joined_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        subject TEXT,
        query TEXT,
        created_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS favorites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        subject_code TEXT,
        lang TEXT,
        book_idx INTEGER,
        book_name TEXT,
        book_url TEXT,
        added_at TEXT
    )""")
    # История поиска книг
    c.execute("""CREATE TABLE IF NOT EXISTS book_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        subject_code TEXT,
        lang TEXT,
        book_idx INTEGER,
        book_name TEXT,
        book_url TEXT,
        opened_at TEXT
    )""")
    # Заблокированные пользователи
    c.execute("""CREATE TABLE IF NOT EXISTS banned_users (
        user_id INTEGER PRIMARY KEY,
        banned_at TEXT,
        reason TEXT
    )""")
    # Счётчик открытий книг
    c.execute("""CREATE TABLE IF NOT EXISTS book_stats (
        book_url TEXT PRIMARY KEY,
        book_name TEXT,
        subject_code TEXT,
        lang TEXT,
        opens INTEGER DEFAULT 0
    )""")
    # Оценки 👍/👎 (один голос от одного пользователя на книгу)
    c.execute("""CREATE TABLE IF NOT EXISTS book_ratings (
        user_id INTEGER,
        book_url TEXT,
        vote INTEGER,
        created_at TEXT,
        PRIMARY KEY (user_id, book_url)
    )""")
    # Материалы от студентов
    c.execute("""CREATE TABLE IF NOT EXISTS submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        first_name TEXT,
        file_id TEXT,
        file_name TEXT,
        status TEXT DEFAULT 'pending',
        subject_code TEXT,
        lang TEXT,
        created_at TEXT
    )""")
    conn.commit()
    conn.close()

def add_user(user_id, username, first_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO users (user_id, username, first_name, lang, joined_at) VALUES (?,?,?,?,?)",
        (user_id, username, first_name, "ru", datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def log_stat(user_id, subject, query=""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO stats (user_id, subject, query, created_at) VALUES (?,?,?,?)",
              (user_id, subject, query, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def add_favorite(user_id, subject_code, lang, book_idx, book_name, book_url):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM favorites WHERE user_id=? AND book_url=?", (user_id, book_url))
    if c.fetchone():
        conn.close()
        return False
    c.execute(
        "INSERT INTO favorites (user_id,subject_code,lang,book_idx,book_name,book_url,added_at) VALUES (?,?,?,?,?,?,?)",
        (user_id, subject_code, lang, book_idx, book_name, book_url, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return True

def remove_favorite(user_id, book_url):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM favorites WHERE user_id=? AND book_url=?", (user_id, book_url))
    conn.commit()
    conn.close()

def get_favorites(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT subject_code,lang,book_idx,book_name,book_url FROM favorites WHERE user_id=? ORDER BY added_at DESC",
        (user_id,)
    )
    rows = c.fetchall()
    conn.close()
    return rows

def save_lang(user_id, lang):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET lang=? WHERE user_id=?", (lang, user_id))
    conn.commit()
    conn.close()

def get_lang(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT lang FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row and row[0] else "ru"


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

def get_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(DISTINCT user_id) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT subject, COUNT(*) as cnt FROM stats GROUP BY subject ORDER BY cnt DESC LIMIT 5")
    top_subjects = c.fetchall()
    c.execute("SELECT COUNT(*) FROM stats")
    total_searches = c.fetchone()[0]
    conn.close()
    return total_users, total_searches, top_subjects

# =========================
# НОВЫЕ DB ФУНКЦИИ
# =========================

def add_book_history(user_id, subject_code, lang, book_idx, book_name, book_url):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Удаляем дубликат если уже есть
    c.execute("DELETE FROM book_history WHERE user_id=? AND book_url=?", (user_id, book_url))
    c.execute(
        "INSERT INTO book_history (user_id,subject_code,lang,book_idx,book_name,book_url,opened_at) VALUES (?,?,?,?,?,?,?)",
        (user_id, subject_code, lang, book_idx, book_name, book_url, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def get_book_history(user_id, limit=10):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT subject_code,lang,book_idx,book_name,book_url,opened_at FROM book_history WHERE user_id=? ORDER BY opened_at DESC LIMIT ?",
        (user_id, limit)
    )
    rows = c.fetchall()
    conn.close()
    return rows

def is_banned(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM banned_users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row is not None

def ban_user(user_id, reason=""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO banned_users (user_id, banned_at, reason) VALUES (?,?,?)",
              (user_id, datetime.now().isoformat(), reason))
    conn.commit()
    conn.close()

def unban_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM banned_users WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def get_banned_list():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT b.user_id, u.username, u.first_name, b.banned_at, b.reason FROM banned_users b LEFT JOIN users u ON b.user_id=u.user_id ORDER BY b.banned_at DESC")
    rows = c.fetchall()
    conn.close()
    return rows


def get_detailed_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(DISTINCT user_id) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM stats")
    total_searches = c.fetchone()[0]
    c.execute("SELECT subject, COUNT(*) as cnt FROM stats GROUP BY subject ORDER BY cnt DESC LIMIT 5")
    top_subjects = c.fetchall()
    # Активность по дням (последние 7 дней)
    c.execute("""SELECT DATE(created_at) as day, COUNT(*) as cnt
                 FROM stats WHERE created_at >= DATE('now', '-7 days')
                 GROUP BY day ORDER BY day DESC""")
    daily = c.fetchall()
    # Новые пользователи за 7 дней
    c.execute("""SELECT COUNT(*) FROM users WHERE joined_at >= DATE('now', '-7 days')""")
    new_users = c.fetchone()[0]
    # Топ книги из истории
    c.execute("""SELECT book_name, COUNT(*) as cnt FROM book_history
                 GROUP BY book_name ORDER BY cnt DESC LIMIT 5""")
    top_books = c.fetchall()
    conn.close()
    return total_users, total_searches, top_subjects, daily, new_users, top_books

def get_monthly_activity():
    """Поиски и новые пользователи по месяцам за ВСЁ время."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""SELECT SUBSTR(created_at,1,7) AS m, COUNT(*), COUNT(DISTINCT user_id)
                 FROM stats WHERE created_at IS NOT NULL GROUP BY m ORDER BY m""")
    searches = c.fetchall()
    c.execute("""SELECT SUBSTR(joined_at,1,7) AS m, COUNT(*)
                 FROM users WHERE joined_at IS NOT NULL GROUP BY m""")
    joined = dict(c.fetchall())
    conn.close()
    return searches, joined

def get_users_list():
    """Все пользователи: id, username, имя, язык, дата входа, число поисков."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""SELECT u.user_id, u.username, u.first_name, u.lang, u.joined_at,
                        (SELECT COUNT(*) FROM stats s WHERE s.user_id = u.user_id) AS n
                 FROM users u ORDER BY u.joined_at DESC""")
    rows = c.fetchall()
    conn.close()
    return rows

def get_all_user_ids():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    rows = [r[0] for r in c.fetchall()]
    conn.close()
    return rows

def record_book_open(book_url, book_name, subject_code, lang):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """INSERT INTO book_stats (book_url, book_name, subject_code, lang, opens)
           VALUES (?,?,?,?,1)
           ON CONFLICT(book_url) DO UPDATE SET opens = opens + 1, book_name = excluded.book_name""",
        (book_url, book_name, subject_code, lang)
    )
    conn.commit()
    conn.close()

def get_top_books(limit=10):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT book_url, book_name, opens FROM book_stats ORDER BY opens DESC, book_name LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def set_vote(user_id, book_url, vote):
    """vote = 1 или -1. Повторное нажатие той же кнопки снимает голос. Возвращает итоговый голос (1/-1/0)."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT vote FROM book_ratings WHERE user_id=? AND book_url=?", (user_id, book_url))
    row = c.fetchone()
    if row and row[0] == vote:
        c.execute("DELETE FROM book_ratings WHERE user_id=? AND book_url=?", (user_id, book_url))
        result = 0
    else:
        c.execute("INSERT OR REPLACE INTO book_ratings (user_id, book_url, vote, created_at) VALUES (?,?,?,?)",
                  (user_id, book_url, vote, datetime.now().isoformat()))
        result = vote
    conn.commit()
    conn.close()
    return result

def get_votes(book_url):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""SELECT COALESCE(SUM(CASE WHEN vote=1 THEN 1 ELSE 0 END),0),
                        COALESCE(SUM(CASE WHEN vote=-1 THEN 1 ELSE 0 END),0)
                 FROM book_ratings WHERE book_url=?""", (book_url,))
    up, down = c.fetchone()
    conn.close()
    return up, down

def add_submission(user_id, username, first_name, file_id, file_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """INSERT INTO submissions (user_id, username, first_name, file_id, file_name, status, created_at)
           VALUES (?,?,?,?,?,'pending',?)""",
        (user_id, username or "", first_name or "", file_id, file_name, datetime.now().isoformat())
    )
    sub_id = c.lastrowid
    conn.commit()
    conn.close()
    return sub_id

def get_submission(sub_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM submissions WHERE id=?", (sub_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def set_submission_status(sub_id, status, subject_code=None, lang=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE submissions SET status=?, subject_code=COALESCE(?,subject_code), lang=COALESCE(?,lang) WHERE id=?",
              (status, subject_code, lang, sub_id))
    conn.commit()
    conn.close()

def count_pending_by_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM submissions WHERE user_id=? AND status='pending'", (user_id,))
    n = c.fetchone()[0]
    conn.close()
    return n

def get_extra_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT book_name, opens FROM book_stats ORDER BY opens DESC LIMIT 5")
    top_opens = c.fetchall()
    c.execute("""SELECT COALESCE(s.book_name, r.book_url),
                        SUM(CASE WHEN r.vote=1 THEN 1 ELSE 0 END) AS up,
                        SUM(CASE WHEN r.vote=-1 THEN 1 ELSE 0 END) AS down
                 FROM book_ratings r LEFT JOIN book_stats s ON s.book_url = r.book_url
                 GROUP BY r.book_url ORDER BY up DESC, down ASC LIMIT 5""")
    top_rated = c.fetchall()
    c.execute("SELECT status, COUNT(*) FROM submissions GROUP BY status")
    subs = dict(c.fetchall())
    conn.close()
    return top_opens, top_rated, subs

def migrate_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Миграция users
    c.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in c.fetchall()]
    if "lang" not in columns:
        c.execute("ALTER TABLE users ADD COLUMN lang TEXT DEFAULT 'ru'")
        conn.commit()

    # Миграция favorites — пересоздаём если структура неправильная
    c.execute("PRAGMA table_info(favorites)")
    fav_cols = [row[1] for row in c.fetchall()]
    expected = {"user_id", "subject_code", "lang", "book_idx", "book_name", "book_url", "added_at"}
    if not expected.issubset(set(fav_cols)):
        # Удаляем старую таблицу и создаём новую
        c.execute("DROP TABLE IF EXISTS favorites")
        c.execute("""CREATE TABLE favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            subject_code TEXT,
            lang TEXT,
            book_idx INTEGER,
            book_name TEXT,
            book_url TEXT,
            added_at TEXT
        )""")
        conn.commit()
        logger.info("✅ favorites table recreated")

    conn.close()

init_db()
migrate_db()

import json as _json
_books_db_path = os.path.join(BASE_DIR, "books_db.json")
if os.path.exists(_books_db_path):
    with open(_books_db_path, "r", encoding="utf-8") as _f:
        BOOKS_DB = _json.load(_f)
else:
    BOOKS_DB = {}

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# =========================
# MIDDLEWARE — бан + флуд
# =========================
class BanAndFloodMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable, event: TelegramObject, data: dict) -> Any:
        user = getattr(event, 'from_user', None)
        if not user:
            return await handler(event, data)
        user_id = user.id
        # Бан — полное молчание
        if is_banned(user_id):
            # Для callback закрываем spinner
            if hasattr(event, 'answer') and hasattr(event, 'data'):
                try:
                    await event.answer()
                except Exception:
                    pass
            return
        if user_id == ADMIN_ID:
            return await handler(event, data)
        # Флуд
        if hasattr(event, 'data'):  # callback
            if is_flood_callback(user_id):
                try:
                    await event.answer()
                except Exception:
                    pass
                return
        else:  # message
            if not getattr(event, "document", None) and is_flood(user_id):
                return
        return await handler(event, data)

dp.message.middleware(BanAndFloodMiddleware())
dp.callback_query.middleware(BanAndFloodMiddleware())

# Антиспам трекер
spam_tracker = {}  # {user_id: [datetime, ...]}

# Список матов (русский + казахский)
MAT_WORDS = [
    "блять", "бля", "сука", "пизд", "ёбан", "ебан", "еба", "ёба",
    "хуй", "хуе", "хуи", "пизд", "пиздо", "пизда", "мразь", "залупа",
    "шлюха", "шлюх", "ублюдок", "ублюд", "мудак", "мудил", "пидор",
    "пидар", "гондон", "гнида", "тварь", "выблядок", "выеб",
    "ахуе", "охуе", "нахуй", "пошел нахуй", "иди нахуй",
    "шайтан", "нокта", "сорай кет", "ит",
]


# Мат ищем по целым словам: короткие слова — только точное совпадение,
# длинные корни — по началу слова. Раньше проверялось «слово внутри текста»,
# и «ит» банило за «цитология», «лейкоцит», «Литвицкий», а «бля» — за «бляшка».
_MAT_EXACT = {
    "бля", "блять", "блядь", "сука", "суки", "ит", "тварь", "мразь", "гнида", "нокта",
    "шайтан", "еба", "залупа", "шлюха", "мудак", "ублюдок", "гондон", "пидор", "пидар",
    "выблядок",
}
_MAT_PREFIX = (
    "пизд", "ебан", "хуй", "хуе", "хуи", "нахуй", "ахуе", "охуе", "выеб",
    "мудил", "ублюд", "шлюх", "бляд", "пидор", "пидар",
)

def find_profanity(text):
    t = text.lower().replace("ё", "е")
    words = re.findall(r"\w+", t)
    for w in words:
        if w in _MAT_EXACT or w.startswith(_MAT_PREFIX):
            return w
    if "сорай кет" in t:
        return "сорай кет"
    return None

# =========================
# КЛАВИАТУРЫ
# =========================
def main_menu_keyboard(lang="kz"):
    """Reply-клавиатура: названия предметов отображаются на языке интерфейса."""
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
    common = {
        "kz": [("⭐ Таңдаулылар", "📋 Барлық пәндер"), ("📖 Іздеу тарихы", "🔥 Танымал"), ("📤 Материал жіберу",)],
        "ru": [("⭐ Избранное", "📋 Все предметы"), ("📖 История поиска", "🔥 Популярное"), ("📤 Отправить материал",)],
        "en": [("⭐ Favorites", "📋 All subjects"), ("📖 Search history", "🔥 Popular"), ("📤 Submit material",)],
    }[lang]
    rows.extend([[KeyboardButton(text=x) for x in row] for row in common])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

# Совместимость со старыми вызовами; новые сообщения используют клавиатуру по языку.
main_menu = main_menu_keyboard("kz")

SUBJECTS = {
    "🔬 гистология": "gistologiya",
    "🦴 анатомия": "anatomiya",
    "🧪 биохимия": "biohimiya",
    "⚡ физиология": "fiziologiya",
    "🏥 ішкі аурулар": "ishki",
    "🔥 патфиз": "patfiz",
    "🔭 патанат": "patanat",
    "🗺 топанат": "toanat",
    "💊 фармакология": "farmakologiya",
    "🦠 микробиология": "mikrobiologiya",
    "🧬 генетика": "genetika",
    "⚗️ биофизика": "biofizika",
    "📜 тарих": "tarih",
    "✂️ хирургия": "hirurgiya",
}

# Тексты кнопок для трёх языков ведут в те же разделы.
SUBJECTS.update({
    "🔬 histology": "gistologiya", "🦴 anatomy": "anatomiya",
    "🧪 biochemistry": "biohimiya", "⚡ physiology": "fiziologiya",
    "🏥 internal medicine": "ishki", "🔥 pathophysiology": "patfiz",
    "🔭 pathoanatomy": "patanat", "🗺 topographic anatomy": "toanat",
    "💊 pharmacology": "farmakologiya", "🦠 microbiology": "mikrobiologiya",
    "🧬 genetics": "genetika", "⚗️ biophysics": "biofizika",
    "📜 kazakhstan history": "tarih", "✂️ surgery": "hirurgiya",
    "🏥 внутренние болезни": "ishki", "🔥 патофизиология": "patfiz",
    "🔭 патанатомия": "patanat", "🗺 топографическая анатомия": "toanat",
    "📜 история казахстана": "tarih",
})

SUBJECT_NAMES = {
    "gistologiya":    "🔬 Гистология",
    "anatomiya":      "🦴 Анатомия",
    "biohimiya":      "🧪 Биохимия",
    "fiziologiya":    "⚡ Физиология",
    "ishki":          "🏥 Ішкі аурулар",
    "patfiz":         "🔥 Патфиз",
    "patanat":        "🔭 Патанат",
    "toanat":         "🗺 Топанат",
    "farmakologiya":  "💊 Фармакология",
    "mikrobiologiya": "🦠 Микробиология",
    "genetika":       "🧬 Генетика",
    "biofizika":      "⚗️ Биофизика",
    "tarih":          "📜 Тарих",
    "hirurgiya":      "✂️ Хирургия",
}

SUBJECT_PHOTOS = {
    "gistologiya":    "Гистология.jpg",
    "anatomiya":      "анатомия.jpg",
    "biohimiya":      "Биохимия.jpg",
    "fiziologiya":    "Физиология.jpg",
    "ishki":          "Пропедевтика.jpg",
    "patfiz":         "Патфизиология.jpg",
    "patanat":        "Патанатомия.jpg",
    "toanat":         "Топанатомия.jpg",
    "farmakologiya":  "Фармакология.jpg",
    "mikrobiologiya": "Микробиология.jpg",
    "genetika":       "Генетика.jpg",
    "biofizika":      "Биофизика.jpg",
    "tarih":          "Тарих.jpg",
    "hirurgiya":      "Хирургия.jpg",
    "stomatologiya":  "Стоматология.jpg",
    "epidemiologiya": "Эпидемиология.jpg",
    "immunologiya":   "Иммунология.jpg",
    "radiologiya":    "Лучевая Диагностика.jpg",
    "embriologiya":   "Эмбриология.jpg",
}

SUBJECT_KEYWORDS = {
    "gistologiya": ["гист","гиста","гисто","гистология","гистологию","hist","gist","gisto","гистол","цитология","эмбриология","цито","эмбрио"],
    "anatomiya":   ["анат","анато","анатомия","анатомию","anat","anatom","анатом"],
    "biohimiya":   ["биох","биохим","биохимия","биохимию","биохи","биоким","биокимия","biohim","biochem","biochemistry","bkh","бхим","бх"],
    "fiziologiya": ["физ","физио","физиол","физиология","физиологию","fiziol","fizyo"],
    "ishki":       ["ішкі","ішкі аурулар","ішкі ауру","ішкі аур","внутренние","внутренние болезни","внутренняя медицина","internal medicine","ішкіаурулар","ishki","терапия","терап","пропедевтика","пропедевт","пропед"],
    "patfiz":      ["патфиз","пат физ","патофизиология","патофизиол","patfiz","патфизиол"],
    "patanat":     ["патанат","пат анат","патологическая анатомия","патанатомия","patanat","патанатом"],
    "toanat":      ["топанат","топ анат","топографическая анатомия","топографич","toanat"],
    "farmakologiya":  ["фармак","фарма","фармо","фармакология","фармакологию","фармако","pharmacology","pharmacological","pharmaco","pharmac","pharma","farmak"],
    "mikrobiologiya": ["микроб","microb","микробио"],
    "genetika":    ["генет","genet","генетика"],
    "biofizika":   ["биофиз","biofiz","биофизика"],
    "tarih":       ["тарих","tarih","история казах","қазақстан тарих"],
    "hirurgiya":   ["хирург","hirurg","жалпы хир"],
    "stomatologiya": ["стоматология","стоматологию","стомат","стом","stomatology","dentistry"],
}

# Английские названия предметов (чем длиннее совпадение, тем оно точнее)
_EN_SUBJECT_KEYWORDS = {
    "gistologiya":    ["histology", "cytology", "embryology"],
    "fiziologiya":    ["physiology"],
    "patfiz":         ["pathophysiology", "pathological physiology", "pathologic physiology"],
    "patanat":        ["pathoanatomy", "pathanatomy", "pathological anatomy", "pathologic anatomy"],
    "toanat":         ["topographic anatomy", "topographical anatomy"],
    "ishki":          ["propedeutics"],
    "biofizika":      ["biophysics"],
    "hirurgiya":      ["surgery", "surgical"],
    "tarih":          ["history of kazakhstan", "kazakhstan history", "kazakh history"],
}
for _code, _extra in _EN_SUBJECT_KEYWORDS.items():
    SUBJECT_KEYWORDS.setdefault(_code, []).extend(_extra)

# =========================
# МЕНЮ ПРЕДМЕТА (3 языка в кнопках)
# =========================

# Предметы БЕЗ препаратов
NO_PREPARATY = {"biohimiya", "fiziologiya", "ishki", "farmakologiya",
                "mikrobiologiya", "genetika", "biofizika", "tarih"}

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
        InlineKeyboardButton(text="🏠 Таңдаулар / Меню / Menu", callback_data="go_main_menu"),
        InlineKeyboardButton(text="📌 Канал", url="https://t.me/library_adasan"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def coming_soon_inline(back_code):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅ Артқа / Назад / Back", callback_data=f"subject_{back_code}")],
        [InlineKeyboardButton(text="🏠 Таңдаулар / Меню / Menu", callback_data="go_main_menu")],
    ])

def start_inline(lang="kz"):
    SUBJECT_LABELS = {
        "kz": ["🔬 Гистология", "🦴 Анатомия", "🧪 Биохимия", "⚡ Физиология",
               "🏥 Ішкі аурулар", "🔥 Патфиз", "🔭 Патанат", "🗺 Топанат"],
        "ru": ["🔬 Гистология", "🦴 Анатомия", "🧪 Биохимия", "⚡ Физиология",
               "🏥 Внутр. болезни", "🔥 Патфиз", "🔭 Патанат", "🗺 Топанат"],
        "en": ["🔬 Histology", "🦴 Anatomy", "🧪 Biochemistry", "⚡ Physiology",
               "🏥 Internal Medicine", "🔥 Pathophysiology", "🔭 Pathoanatomy", "🗺 Topographic Anat."],
    }
    codes = ["gistologiya", "anatomiya", "biohimiya", "fiziologiya",
             "ishki", "patfiz", "patanat", "toanat"]
    labels = SUBJECT_LABELS.get(lang, SUBJECT_LABELS["kz"])
    lib_text = {"kz": "📚 Кітапхана", "ru": "📚 Библиотека", "en": "📚 Library"}.get(lang, "📚 Кітапхана")

    rows = [
        [
            InlineKeyboardButton(text=lib_text, callback_data="open_subjects"),
            InlineKeyboardButton(text="📌 Канал", url="https://t.me/library_adasan"),
        ]
    ]
    for i in range(0, 8, 2):
        rows.append([
            InlineKeyboardButton(text=labels[i],   callback_data=f"subject_{codes[i]}"),
            InlineKeyboardButton(text=labels[i+1], callback_data=f"subject_{codes[i+1]}"),
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

CHANNEL_USERNAME = "@library_adasan"

_sub_ok_until = {}      # user_id -> до какого времени считаем «подписан» (кэш)
SUB_CACHE_SECONDS = 600  # как часто перепроверять подписчика (10 минут)

async def check_subscription(user_id):
    """True — подписан (или проверить не удалось). Подписанных кэшируем на 10 минут."""
    if _sub_ok_until.get(user_id, 0) > time.time():
        return True
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        if member.status == "restricted":
            ok = bool(getattr(member, "is_member", True))
        else:
            ok = member.status not in ["left", "kicked", "banned"]
    except Exception as e:
        # Бот должен быть АДМИНОМ канала, иначе Telegram не даёт проверить подписку.
        # Чтобы не заблокировать всех из-за сбоя — пропускаем, но пишем в лог.
        logger.warning(f"Проверка подписки не удалась (бот админ канала?): {e}")
        return True
    if ok:
        _sub_ok_until[user_id] = time.time() + SUB_CACHE_SECONDS
    return ok


class SubscriptionMiddleware(BaseMiddleware):
    """Не пускает в бота (в личке) тех, кто не подписан на канал."""
    async def __call__(self, handler: Callable, event: TelegramObject, data: dict) -> Any:
        user = getattr(event, "from_user", None)
        is_callback = hasattr(event, "data")
        chat = (event.message.chat if is_callback and event.message else getattr(event, "chat", None))

        # Пропускаем: нет пользователя, не личка, админ, /start, кнопка «Подписался»
        if (not user or not chat or chat.type != "private" or user.id == ADMIN_ID
                or (not is_callback and (getattr(event, "text", "") or "").startswith("/start"))
                or (is_callback and event.data == "check_sub")):
            return await handler(event, data)

        if await check_subscription(user.id):
            return await handler(event, data)

        text = ("🔒 Ботты пайдалану үшін біздің каналға жазылу керек!\n"
                "Для использования бота нужно подписаться на канал.\n\n"
                "👇 Жазылып, «Жазылдым» батырмасын басыңыз / Подпишитесь и нажмите «Подписался»")
        try:
            if is_callback:
                await event.answer("🔒 Алдымен каналға жазылыңыз / Сначала подпишитесь на канал", show_alert=True)
                await bot.send_message(chat.id, text, reply_markup=subscribe_keyboard())
            else:
                await event.answer(text, reply_markup=subscribe_keyboard())
        except Exception as e:
            logger.warning(f"Не удалось отправить запрос подписки: {e}")
        return  # дальше в обработчики не пускаем

dp.message.middleware(SubscriptionMiddleware())
dp.callback_query.middleware(SubscriptionMiddleware())

# =========================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =========================
def find_book(query):
    # Поиск теперь через books_db.json
    return None

# Составные названия: ВСЕ основы должны встретиться в запросе (в любом порядке и падеже).
# Ловят «патологическая физиология», «патологический физиология», «патологиялық анатомия» и т.п.
SUBJECT_COMBOS = {
    "patfiz":  [("патолог", "физиол"), ("пат", "физ")],
    "patanat": [("патолог", "анатом"), ("пат", "анат")],
    "toanat":  [("топограф", "анатом"), ("топ", "анат")],
}

def _norm_q(s):
    s = s.lower().replace("ё", "е")
    return re.sub(r"[^\w\s]", " ", s).strip()

def find_subject(query):
    """Выбирает самое ТОЧНОЕ совпадение, а не первое.
    Раньше «анат» (анатомия) находилось внутри «патанат» и «топанат»,
    а «физ» (физиология) — внутри «патфиз», поэтому бот путал предметы."""
    q = _norm_q(query)
    if not q:
        return None
    best_code, best_score = None, 0

    # 1. Прямые ключевые слова: чем длиннее совпадение, тем оно точнее
    for code, keywords in SUBJECT_KEYWORDS.items():
        for kw in keywords:
            kw = _norm_q(kw)
            matched = (kw in q) if len(kw) >= 4 else bool(re.search(r"(?<!\w)" + re.escape(kw) + r"(?!\w)", q))
            if kw and matched and len(kw) > best_score:
                best_code, best_score = code, len(kw)

    # 2. Составные названия — приоритетнее обычных ключевых слов
    for code, combos in SUBJECT_COMBOS.items():
        for stems in combos:
            if all(re.search(r"(?<!\w)" + re.escape(st), q) for st in stems):
                score = 100 + sum(len(st) for st in stems)
                if score > best_score:
                    best_code, best_score = code, score

    if best_code is None:          # раздел из хэштегов: «стоматология», «пропедевтика»…
        for code, title in _DYN_NAMES.items():
            t = _norm_q(title)
            if len(q) >= 4 and (q in t or t in q):
                return code
    return best_code



# =========================
# АНГЛИЙСКИЕ КНИГИ: определение по имени файла
# (раньше всё без пометки «каз/eng» считалось русским)
# =========================
_EN_STOP = {"the", "of", "and", "for", "with", "in", "to", "an", "by", "on", "from", "at", "vs"}
_EN_MED = {
    "textbook", "atlas", "anatomy", "physiology", "biochemistry", "pharmacology", "pathology",
    "clinical", "medical", "essential", "essentials", "review", "guide", "handbook", "principles",
    "edition", "volume", "surgery", "histology", "immunology", "microbiology", "genetics", "basic",
    "illustrated", "medicine", "diagnosis", "therapy", "disease", "diseases", "human", "molecular",
    "biology", "neuroscience", "embryology", "pathophysiology", "pediatrics", "manual",
    "fundamentals", "concise", "comprehensive", "lecture", "notes",
}
_EN_KNOWN = {
    "pathoma", "netter", "sobotta", "gray", "guyton", "harper", "robbins", "junqueira",
    "lippincott", "usmle", "kaplan", "costanzo", "boron", "ganong", "brs",
    "gilroy", "chaurasia", "chaurasiae",
}

def _is_english_filename(fname):
    """True, если имя файла выглядит английским (кириллицы нет, есть английские слова).
    Транслит русских слов (Kommunalnaya_gigiena) сюда не попадает."""
    name = re.sub(r"\.[A-Za-z0-9]{2,5}$", "", fname or "")
    letters = re.findall(r"[^\W\d_]", name)
    if len(letters) < 6 or any("\u0400" <= ch <= "\u04FF" for ch in letters):
        return False
    words = [w.lower() for w in re.findall(r"[A-Za-z]+", name)]
    if any(w in _EN_KNOWN for w in words) or {"first", "aid"} <= set(words):
        return True
    stop = sum(1 for w in words if w in _EN_STOP)
    med = sum(1 for w in words if w in _EN_MED)
    return stop >= 1 or med >= 2

# =========================
# УМНЫЙ ПОИСК КНИГ (опечатки + латиница)
# =========================
from functools import lru_cache

_LAT_MULTI = [
    ("shch", "щ"), ("sch", "ш"), ("sh", "ш"), ("ch", "ч"), ("zh", "ж"),
    ("kh", "х"), ("ts", "ц"), ("ya", "я"), ("yu", "ю"), ("yo", "е"),
    ("ye", "е"), ("ph", "ф"), ("th", "т"), ("ck", "к"),
]
_LAT_SINGLE = {
    "a": "а", "b": "б", "c": "к", "d": "д", "e": "е", "f": "ф", "g": "г",
    "h": "х", "i": "и", "j": "ж", "k": "к", "l": "л", "m": "м", "n": "н",
    "o": "о", "p": "п", "q": "к", "r": "р", "s": "с", "t": "т", "u": "у",
    "v": "в", "w": "в", "x": "кс", "y": "и", "z": "с",
}
# «Звуковое» упрощение: похожие по звучанию буквы считаются одной
_PHON_MAP = str.maketrans({
    "ё": "и", "е": "и", "э": "и", "ы": "и", "і": "и", "й": "и",
    "я": "а", "о": "а", "ә": "а", "ө": "а",
    "ю": "у", "ү": "у", "ұ": "у",
    "қ": "к", "ғ": "г", "ң": "н", "һ": "х",
    "щ": "ш", "ч": "ш", "ж": "ш", "ц": "с",
    "б": "п", "в": "ф", "г": "к", "д": "т", "з": "с",
    "ъ": "", "ь": "",
})


@lru_cache(maxsize=50000)
def _phon_key(word):
    """Слово -> 'звуковой ключ'. Латиница и кириллица приводятся к одному виду."""
    w = word.lower()
    for a, b in _LAT_MULTI:
        w = w.replace(a, b)
    w = "".join(_LAT_SINGLE.get(ch, ch) for ch in w)
    w = w.translate(_PHON_MAP)
    return re.sub(r"(.)\1+", r"\1", w)  # двойные буквы -> одна


# Слова-«мусор» в запросах: «дайте книгу», «есть учебник» и т.п.
_STOP_WORDS = {
    "книга", "книгу", "книги", "книгa", "учебник", "учебника", "скачать", "дайте", "есть",
    "пожалуйста", "кто", "нужна", "нужен", "нужно", "ищу", "где", "pdf", "kitap", "кітап",
    "кітабы", "кітапты", "керек", "бар", "ма", "book", "the", "and", "прошу", "скиньте",
    "скинь", "кинь", "кинте", "жіберіңіз", "салыңыз", "привет", "здравствуйте", "салем",
}

def _tokens(text):
    return [w for w in re.findall(r"[^\W\d_]+", text.lower())
            if len(w) >= 3 and w not in _STOP_WORDS]


def _edit_sim(a, b):
    """Похожесть слов 0..1 (расстояние Дамерау-Левенштейна, перестановка = 1 ошибка)."""
    la, lb = len(a), len(b)
    if not la or not lb:
        return 0.0
    prev2, prev = None, list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        prev2, prev = prev, cur
    return 1 - prev[lb] / max(la, lb)


def _word_score(qk, bk):
    if qk == bk:
        return 1.0
    if len(qk) >= 4 and bk.startswith(qk):   # человек ввёл начало слова
        return 0.95
    if len(qk) >= 4 and qk in bk:
        return 0.9
    thr = 0.85 if len(qk) <= 4 else (0.75 if len(qk) <= 6 else 0.7)
    if abs(len(qk) - len(bk)) > max(len(qk), len(bk)) * (1 - thr):
        return 0.0
    s = _edit_sim(qk, bk)
    return s if s >= thr else 0.0


_fuzzy_cache = {"sig": None, "index": {}}


def _books_signature():
    return (id(BOOKS_DB), tuple(
        (sc, lg, len(bks)) for sc, langs in BOOKS_DB.items() for lg, bks in langs.items()
    ))


def _get_fuzzy_index():
    """Индекс: звуковой ключ слова -> книги. Пересобирается, когда меняется BOOKS_DB."""
    sig = _books_signature()
    if _fuzzy_cache["sig"] != sig:
        index = {}
        for sc, langs in BOOKS_DB.items():
            for lg, bks in langs.items():
                for idx, bk in enumerate(bks):
                    text = f'{bk.get("file_name", "")} {bk.get("caption", "")}'
                    for w in _tokens(text):
                        k = _phon_key(w)
                        if k:
                            index.setdefault(k, set()).add((sc, lg, idx))
        _fuzzy_cache["index"] = index
        _fuzzy_cache["sig"] = sig
    return _fuzzy_cache["index"]


def fuzzy_find_books(query, limit=5, min_score=0.0):
    """Ищет книги, даже если запрос с опечатками или написан латиницей.
    Возвращает (всего_найдено, [(sc, lang, idx, book), ...])."""
    q_keys = [k for k in (_phon_key(w) for w in _tokens(query)) if k]
    if not q_keys:
        return 0, []
    index = _get_fuzzy_index()

    per_book = {}  # (sc, lg, idx) -> [оценки по словам запроса]
    for qk in q_keys:
        best = {}
        for bk_key, books in index.items():
            s = _word_score(qk, bk_key)
            if s:
                for b in books:
                    if s > best.get(b, 0):
                        best[b] = s
        for b, s in best.items():
            per_book.setdefault(b, []).append(s)

    need = (len(q_keys) + 1) // 2  # минимум половина слов запроса должна совпасть
    ranked = []
    for (sc, lg, idx), scores in per_book.items():
        if len(scores) >= need and sum(scores) / len(scores) >= min_score:
            ranked.append((len(scores), sum(scores) / len(scores), sc, lg, idx))
    ranked.sort(key=lambda r: (-r[0], -r[1]))
    results = [(sc, lg, idx, BOOKS_DB[sc][lg][idx]) for _, _, sc, lg, idx in ranked[:limit]]
    return len(ranked), results


# Синонимы предметов для поиска книг: пользователь может писать на русском,
# казахском, английском или латиницей. Каталог книг при этом не переименовывается.
_SEARCH_ALIAS_GROUPS = [
    ("гистология", "histology", "гисто", "гиста", "histologia", "гисталогия"),
    ("анатомия", "anatomy", "anatomi", "анат", "анато"),
    ("биохимия", "biochemistry", "biochem", "биохим", "биокимия"),
    ("физиология", "physiology", "fiziologiya", "физиол", "физио"),
    ("патофизиология", "pathophysiology", "pathophysiolgy", "патфиз", "патофиз"),
    ("патанатомия", "pathoanatomy", "pathological anatomy", "патанат"),
    ("топографическая анатомия", "topographic anatomy", "topographical anatomy", "топанат"),
    ("фармакология", "pharmacology", "pharmacolgy", "фарма", "фармак"),
    ("микробиология", "microbiology", "microbiolgy", "микробио"),
    ("генетика", "genetics", "genetic", "генет"),
    ("биофизика", "biophysics", "биофиз"),
    ("хирургия", "surgery", "surgical", "хирург"),
    ("внутренние болезни", "internal medicine", "ішкі аурулар", "пропедевтика"),
    ("история казахстана", "kazakhstan history", "kazakh history", "қазақстан тарихы"),
]

def expand_search_queries(query):
    """Добавляет языковые варианты предметных слов, в том числе внутри названия книги."""
    original = query.strip()
    normalized_query = _norm_q(original)
    variants = [original]
    query_tokens = normalized_query.split()

    for group in _SEARCH_ALIAS_GROUPS:
        aliases = [_norm_q(alias) for alias in group if _norm_q(alias)]
        matched_token = None

        # Сначала ищем точное название/фразу.
        if normalized_query in aliases:
            matched_token = normalized_query
        else:
            # Затем ищем отдельное слово в запросе (например, "Junqueira Histolgy").
            for token in query_tokens:
                for alias in aliases:
                    if " " in alias:
                        continue
                    if token == alias:
                        matched_token = token
                        break
                    if len(alias) >= 6:
                        threshold = 0.84 if len(alias) <= 9 else 0.78
                        if _edit_sim(token, alias) >= threshold:
                            matched_token = token
                            break
                if matched_token:
                    break

        if matched_token:
            if normalized_query == matched_token:
                variants.extend(group)
            else:
                # Сохраняем имя автора/прочие слова и заменяем только найденный термин.
                for alias in group:
                    variants.append(re.sub(
                        re.escape(matched_token), alias, original, count=1, flags=re.IGNORECASE
                    ))

    out, seen = [], set()
    for item in variants:
        key = _norm_q(item)
        if key and key not in seen:
            seen.add(key)
            out.append(item)
    return out[:20]


def find_subject_fuzzy(query):
    """Находит раздел по английскому названию и небольшим опечаткам."""
    q = _norm_q(query)
    if not q:
        return None
    # Фраза из нескольких слов считается названием раздела только при точном совпадении.
    if len(q.split()) > 1:
        for code, aliases in SUBJECT_KEYWORDS.items():
            if any(q == _norm_q(alias) for alias in aliases):
                return code
        for code, combos in SUBJECT_COMBOS.items():
            if any(q == _norm_q(" ".join(stems)) for stems in combos):
                return code
        return None
    direct = find_subject(query)
    if direct:
        return direct
    best_code, best_score = None, 0.0
    for code, aliases in SUBJECT_KEYWORDS.items():
        for alias in aliases:
            a = _norm_q(alias)
            if len(a) < 6 or " " in a:
                continue
            score = _edit_sim(q, a)
            threshold = 0.84 if len(a) <= 9 else 0.78
            if score >= threshold and score > best_score:
                best_code, best_score = code, score
    return best_code


async def search_books_multilingual(query, limit=5):
    """Сначала ищет точные вхождения по языковым вариантам, затем fuzzy-совпадения."""
    variants = expand_search_queries(query)
    exact = {}
    for variant in variants:
        q = variant.lower().strip()
        if not q:
            continue
        for sc, langs in BOOKS_DB.items():
            for book_lang, books in langs.items():
                for idx, bk in enumerate(books):
                    fname = bk.get("file_name", "").lower()
                    cap = bk.get("caption", "").lower()
                    if q in fname or q in cap:
                        exact[(sc, book_lang, idx)] = (sc, book_lang, idx, bk)
    if exact:
        results = list(exact.values())
        return len(results), results[:limit], False

    fuzzy = {}
    for variant in variants:
        total, found = await asyncio.to_thread(fuzzy_find_books, variant, limit * 2)
        for sc, book_lang, idx, bk in found:
            fuzzy[(sc, book_lang, idx)] = (sc, book_lang, idx, bk)
    results = list(fuzzy.values())[:limit]
    return len(fuzzy), results, bool(results)


async def send_subject_menu(chat_id, code):
    name = SUBJECT_NAMES.get(code, "📚 Другое")
    photo_file = SUBJECT_PHOTOS.get(code)
    photo_path = os.path.join(BASE_DIR, photo_file) if photo_file else None
    if photo_path and os.path.exists(photo_path):
        await bot.send_photo(chat_id=chat_id, photo=FSInputFile(photo_path),
                             caption=f"{name}\n\nВыберите раздел / Бөлімді таңдаңыз:",
                             reply_markup=subject_inline(code))
    else:
        await bot.send_message(chat_id=chat_id,
                               text=f"{name}\n\nВыберите раздел / Бөлімді таңдаңыз:",
                               reply_markup=subject_inline(code))

# =========================
# КОМАНДЫ
# =========================
@dp.message(Command("start"))
async def start(message: types.Message):
    add_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    is_subscribed = await check_subscription(message.from_user.id)
    if not is_subscribed:
        await message.answer_photo(
            photo=FSInputFile(os.path.join(BASE_DIR, "adasan.jpg")),
            caption=(
                "👋 Сәлем!\n\n"
                "🔒 Ботты пайдалану үшін\n"
                "біздің каналға жазылу керек!\n\n"
                "👇 Төмендегі батырманы басыңыз:"
            ),
            reply_markup=subscribe_keyboard()
        )
        return
    await message.answer_photo(
        photo=FSInputFile(os.path.join(BASE_DIR, "adasan.jpg")),
        caption="🌐 Тілді таңдаңыз\nВыберите язык\nChoose language:",
        reply_markup=lang_select_keyboard()
    )

@dp.message(Command("menu"))
async def menu_command(message: types.Message):
    lang = get_lang(message.from_user.id)
    welcome = WELCOME_TEXTS.get(lang, WELCOME_TEXTS["kz"]).format(name=message.from_user.first_name)
    await message.answer_photo(
        photo=FSInputFile(os.path.join(BASE_DIR, "adasan.jpg")),
        caption=welcome,
        reply_markup=start_inline(lang)
    )

@dp.message(Command("chanel"))
async def channel(message: types.Message):
    await message.answer(
        "📌 Біздің кітапхана каналы:\n\n"
        "👉 @library_adasan\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Барлық кітаптар мен материалдар сонда! 📚",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📌 Каналға өту", url="https://t.me/library_adasan")],
        ])
    )

@dp.message(Command("favorites"))
async def favorites_command(message: types.Message):
    favs = get_favorites(message.from_user.id)
    if not favs:
        await message.answer(
            "⭐ Таңдаулылар\n\nСіздің таңдаулыларыңыз жоқ.\n\nКітапты оқып жатқанда ⭐ батырмасын басыңыз!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Таңдаулар / Меню / Menu", callback_data="go_main_menu")]
            ])
        )
        return
    rows = []
    for sc, lg, bi, bn, bu in favs:
        rows.append([
            InlineKeyboardButton(text=f"📖 {bn[:30]}", callback_data=f"bk_{sc}_{lg}_{bi}"),
            InlineKeyboardButton(text="🗑", callback_data=f"fav_del_{bu}"),
        ])
    rows.append([InlineKeyboardButton(text="🏠 Таңдаулар / Меню / Menu", callback_data="go_main_menu")])
    lang = get_lang(message.from_user.id)
    fav_title = {
        "kz": f"⭐ Сіздің таңдаулыларыңыз ({len(favs)}):",
        "ru": f"⭐ Ваши избранные ({len(favs)}):",
        "en": f"⭐ Your favorites ({len(favs)}):",
    }.get(lang, f"⭐ Сіздің таңдаулыларыңыз ({len(favs)}):")
    await message.answer(fav_title,
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

# =========================
# CALLBACK — выбор языка
# =========================
@dp.callback_query(lambda c: c.data and c.data.startswith("setlang_"))
async def setlang_handler(callback: types.CallbackQuery):
    lang = callback.data.replace("setlang_", "")
    save_lang(callback.from_user.id, lang)
    name = callback.from_user.first_name
    welcome = WELCOME_TEXTS.get(lang, WELCOME_TEXTS["kz"]).format(name=name)
    await callback.message.delete()
    await bot.send_photo(
        chat_id=callback.message.chat.id,
        photo=FSInputFile(os.path.join(BASE_DIR, "adasan.jpg")),
        caption=welcome,
        reply_markup=start_inline(lang)
    )
    await bot.send_message(chat_id=callback.message.chat.id, text="👇", reply_markup=main_menu_keyboard(lang))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "check_sub")
async def check_sub_handler(callback: types.CallbackQuery):
    if await check_subscription(callback.from_user.id):
        await callback.message.delete()
        await bot.send_photo(
            chat_id=callback.message.chat.id,
            photo=FSInputFile(os.path.join(BASE_DIR, "adasan.jpg")),
            caption="🌐 Тілді таңдаңыз\nВыберите язык\nChoose language:",
            reply_markup=lang_select_keyboard()
        )
    else:
        await callback.answer("❌ Сіз әлі жазылмадыңыз!", show_alert=True)

# =========================
# CALLBACK — Главное меню
# =========================
@dp.callback_query(lambda c: c.data == "go_main_menu")
async def go_main_menu(callback: types.CallbackQuery):
    lang = get_lang(callback.from_user.id)
    welcome = WELCOME_TEXTS.get(lang, WELCOME_TEXTS["kz"]).format(name=callback.from_user.first_name)
    await bot.send_photo(
        chat_id=callback.message.chat.id,
        photo=FSInputFile(os.path.join(BASE_DIR, "adasan.jpg")),
        caption=welcome,
        reply_markup=start_inline(lang)
    )
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()

@dp.callback_query(lambda c: c.data == "open_subjects")
async def open_subjects(callback: types.CallbackQuery):
    await callback.message.edit_caption(
        caption="📚 Пәнді таңдаңыз / Выберите предмет / Choose subject:",
        reply_markup=start_inline()
    )
    await callback.answer()

# =========================
# CALLBACK — предмет
# =========================
@dp.callback_query(lambda c: c.data and c.data.startswith("subject_"))
async def back_to_subject(callback: types.CallbackQuery):
    code = callback.data.replace("subject_", "")
    await send_subject_menu(callback.message.chat.id, code)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()

# =========================
# CALLBACK — Книги
# =========================
@dp.callback_query(lambda c: c.data and c.data.startswith("books_"))
async def books_handler(callback: types.CallbackQuery):
    code = callback.data.replace("books_", "")
    name = SUBJECT_NAMES.get(code, "📚 Другое")
    photo_path = os.path.join(BASE_DIR, SUBJECT_PHOTOS.get(code, "adasan.jpg"))
    langs = BOOKS_DB.get(code, {})
    total = sum(len(v) for v in langs.values())

    if total > 0:
        caption = (
            f"╔══════════════════════╗\n"
            f"       📚 КІТАПТАР — {name}\n"
            f"╚══════════════════════╝\n\n"
            f"📖 Барлығы: {total} кітап\n\n"
            f"👇 Тілді таңдаңыз / Выберите язык / Choose language:\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 @library_adasan"
        )
        await bot.send_photo(
            chat_id=callback.message.chat.id,
            photo=FSInputFile(photo_path),
            caption=caption,
            reply_markup=lang_inline(code, callback.from_user.id)
        )
        try:
            await callback.message.delete()
        except Exception:
            pass
    else:
        try:
            await callback.message.edit_caption(
                caption=f"{name} — Книги\n\n⏳ Скоро будет доступно!",
                reply_markup=coming_soon_inline(code)
            )
        except:
            await callback.message.edit_text(
                text=f"{name} — Книги\n\n⏳ Скоро будет доступно!",
                reply_markup=coming_soon_inline(code)
            )
    await callback.answer()

# =========================
# CALLBACK — Силлабус
# =========================
@dp.callback_query(lambda c: c.data and c.data.startswith("silabus_"))
async def silabus_handler(callback: types.CallbackQuery):
    code = callback.data.replace("silabus_", "")
    name = SUBJECT_NAMES.get(code, "📚 Другое")
    photo_path = os.path.join(BASE_DIR, SUBJECT_PHOTOS.get(code, "adasan.jpg"))
    SILABUS_URLS = {
        "gistologiya": "https://t.me/library_adasan/436",
        "fiziologiya": "https://t.me/library_adasan/437",
        "biofizika":   "https://t.me/library_adasan/437",
        "biohimiya":   "https://t.me/library_adasan/437",
        "anatomiya":   "https://t.me/library_adasan/437",
        "genetika":    "https://t.me/library_adasan/437",
    }
    if code in SILABUS_URLS:
        caption = (
            f"╔══════════════════════╗\n"
            f"      📋 СИЛЛАБУС — {name}\n"
            f"╚══════════════════════╝\n\n"
            f"📖 Пән: {name}\n"
            f"🎯 Силлабуста не бар:\n"
            f"    • Пәннің мақсаты мен міндеттері\n"
            f"    • Тақырыптар тізімі\n"
            f"    • Баға критерийлері\n"
            f"    • Әдебиеттер тізімі\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 @library_adasan"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📥 Силлабусты жүктеу / Скачать", url=SILABUS_URLS[code])],
            [InlineKeyboardButton(text="⬅ Артқа / Назад / Back", callback_data=f"subject_{code}")],
            [InlineKeyboardButton(text="🏠 Таңдаулар / Меню / Menu", callback_data="go_main_menu")],
        ])
        await bot.send_photo(chat_id=callback.message.chat.id,
                             photo=FSInputFile(photo_path), caption=caption, reply_markup=keyboard)
        try:
            await callback.message.delete()
        except Exception:
            pass
    else:
        try:
            await callback.message.edit_caption(
                caption=f"{name} — Силлабус\n\n⏳ Скоро будет доступно!",
                reply_markup=coming_soon_inline(code)
            )
        except:
            await callback.message.edit_text(
                f"{name} — Силлабус\n\n⏳ Скоро будет доступно!",
                reply_markup=coming_soon_inline(code)
            )
    await callback.answer()

# =========================
# CALLBACK — Лекция
# =========================
@dp.callback_query(lambda c: c.data and c.data.startswith("lektsiya_"))
async def lektsiya_handler(callback: types.CallbackQuery):
    code = callback.data.replace("lektsiya_", "")
    if code == "gistologiya":
        photo_path = os.path.join(BASE_DIR, "gistologiya.jpg")
        caption = (
            "╔══════════════════════╗\n"
            "       🎓 ЛЕКЦИЯ — ГИСТОЛОГИЯ\n"
            "╚══════════════════════╝\n\n"
            "📖 Пән: Гистология, Эмбриология, Цитология\n"
            "🎯 Лекцияда не бар:\n"
            "    • Толық лекция конспектілері\n"
            "    • Схемалар мен кестелер\n"
            "    • Сурет материалдары\n"
            "    • Емтиханға дайындық\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 @library_adasan"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📥 Лекцияны жүктеу / Скачать", url="https://t.me/library_adasan/319")],
            [InlineKeyboardButton(text="⬅ Артқа / Назад / Back", callback_data="subject_gistologiya")],
            [InlineKeyboardButton(text="🏠 Таңдаулар / Меню / Menu", callback_data="go_main_menu")],
        ])
        await bot.send_photo(chat_id=callback.message.chat.id,
                             photo=FSInputFile(photo_path), caption=caption, reply_markup=keyboard)
        try:
            await callback.message.delete()
        except Exception:
            pass
    elif code == "tarih":
        photo_path = os.path.join(BASE_DIR, SUBJECT_PHOTOS.get(code, "adasan.jpg"))
        caption = (
            "╔══════════════════════╗\n"
            "       📖 ЛЕКЦИЯ — ТАРИХ\n"
            "╚══════════════════════╝\n\n"
            "📚 1-тақырыптан 15-тақырыпқа дейін\n"
            "🎯 Барлық лекциялар қосылған\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 @library_adasan"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📖 Барлық лекциялар", url="https://t.me/library_adasan/471")],
            [InlineKeyboardButton(text="⬅ Артқа / Назад / Back", callback_data="subject_tarih")],
            [InlineKeyboardButton(text="🏠 Таңдаулар / Меню / Menu", callback_data="go_main_menu")],
        ])
        await bot.send_photo(chat_id=callback.message.chat.id,
                             photo=FSInputFile(photo_path), caption=caption, reply_markup=keyboard)
        try:
            await callback.message.delete()
        except Exception:
            pass
    else:
        name = SUBJECT_NAMES.get(code, "📚 Другое")
        try:
            await callback.message.edit_caption(
                caption=f"{name} — Лекция\n\n⏳ Скоро будет доступно!",
                reply_markup=coming_soon_inline(code)
            )
        except:
            await callback.message.edit_text(
                f"{name} — Лекция\n\n⏳ Скоро будет доступно!",
                reply_markup=coming_soon_inline(code)
            )
    await callback.answer()

# =========================
# CALLBACK — Препараты
# =========================
@dp.callback_query(lambda c: c.data and c.data.startswith("preparaty_"))
async def preparaty_handler(callback: types.CallbackQuery):
    code = callback.data.replace("preparaty_", "")
    if code == "gistologiya":
        photo_path = os.path.join(BASE_DIR, "gistologiya.jpg")
        caption = (
            "╔══════════════════════╗\n"
            "      🔬 ПРЕПАРАТЫ — ГИСТОЛОГИЯ\n"
            "╚══════════════════════╝\n\n"
            "📖 Пән: Гистология, Эмбриология, Цитология\n"
            "🎯 Препараттарда не бар:\n"
            "    • Микроскопиялық препараттар\n"
            "    • Атлас суреттері\n"
            "    • Препараттарды сипаттау\n"
            "    • Практикалық сабаққа дайындық\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 @library_adasan"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📥 Препараттарды жүктеу / Скачать", url="https://t.me/library_adasan/268")],
            [InlineKeyboardButton(text="⬅ Артқа / Назад / Back", callback_data="subject_gistologiya")],
            [InlineKeyboardButton(text="🏠 Таңдаулар / Меню / Menu", callback_data="go_main_menu")],
        ])
        await bot.send_photo(chat_id=callback.message.chat.id,
                             photo=FSInputFile(photo_path), caption=caption, reply_markup=keyboard)
        try:
            await callback.message.delete()
        except Exception:
            pass
    else:
        name = SUBJECT_NAMES.get(code, "📚 Другое")
        try:
            await callback.message.edit_caption(
                caption=f"{name} — Препараты\n\n⏳ Скоро будет доступно!",
                reply_markup=coming_soon_inline(code)
            )
        except:
            await callback.message.edit_text(
                f"{name} — Препараты\n\n⏳ Скоро будет доступно!",
                reply_markup=coming_soon_inline(code)
            )
    await callback.answer()

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
        [InlineKeyboardButton(text="🏠 Таңдаулар / Меню / Menu", callback_data="go_main_menu")],
    ])

@dp.callback_query(lambda c: c.data and c.data.startswith("video_"))
async def video_handler(callback: types.CallbackQuery):
    code = callback.data.replace("video_", "")
    photo_path = os.path.join(BASE_DIR, SUBJECT_PHOTOS.get(code, "adasan.jpg"))
    if code == "anatomiya":
        caption = (
            "╔══════════════════════╗\n"
            "   🎬 БЕЙНЕСАБАҚ — АНАТОМИЯ\n"
            "╚══════════════════════╝\n\n"
            "📹 Тақырыптар:\n"
            "    🦴 Остеология\n"
            "    💀 Бас сүйек топографиясы\n"
            "    💪 Миология\n"
            "    🦵 Синдесмология\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 @library_adasan"
        )
        keyboard = anat_video_inline()
    elif code == "hirurgiya":
        caption = (
            "╔══════════════════════╗\n"
            "   🎬 БЕЙНЕСАБАҚ — ХИРУРГИЯ\n"
            "╚══════════════════════╝\n\n"
            "📹 Хирургиялық техникалар\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 @library_adasan"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📌 Каналдан қарау", url="https://t.me/library_adasan")],
            [InlineKeyboardButton(text="⬅ Артқа / Назад / Back", callback_data="subject_hirurgiya")],
            [InlineKeyboardButton(text="🏠 Таңдаулар / Меню / Menu", callback_data="go_main_menu")],
        ])
    else:
        await callback.answer("⏳ Скоро будет!")
        return
    await bot.send_photo(chat_id=callback.message.chat.id,
                         photo=FSInputFile(photo_path), caption=caption, reply_markup=keyboard)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()


# =========================
# INLINE — язык книг из BOOKS_DB
# =========================
def lang_inline(subject_code, uid=None):
    by_lang = {}
    langs = BOOKS_DB.get(subject_code, {})
    if langs.get("rus"):
        by_lang["rus"] = InlineKeyboardButton(
            text=f"🇷🇺 Русский ({len(langs['rus'])})", callback_data=f"bl_{subject_code}_rus")
    if langs.get("kaz"):
        by_lang["kaz"] = InlineKeyboardButton(
            text=f"🇰🇿 Қазақша ({len(langs['kaz'])})", callback_data=f"bl_{subject_code}_kaz")
    if langs.get("eng"):
        by_lang["eng"] = InlineKeyboardButton(
            text=f"🇬🇧 English ({len(langs['eng'])})", callback_data=f"bl_{subject_code}_eng")
    order = ["rus", "kaz", "eng"]
    if uid and get_lang(uid) == "en":
        order = ["eng", "rus", "kaz"]      # английский интерфейс: English первым, остальные доступны
    buttons = [by_lang[l] for l in order if l in by_lang]
    rows = [[b] for b in buttons]
    rows.append([InlineKeyboardButton(text="⬅ Артқа / Назад / Back", callback_data=f"subject_{subject_code}")])
    rows.append([InlineKeyboardButton(text="🏠 Таңдаулар / Меню / Menu", callback_data="go_main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def booklist_inline(subject_code, lang, page=0):
    books = BOOKS_DB.get(subject_code, {}).get(lang, [])
    per_page = 8
    start = page * per_page
    end = start + per_page
    rows = []
    for i, book in enumerate(books[start:end]):
        name = book["file_name"].replace(".pdf","").replace(".djvu","").replace("_"," ")[:40]
        rows.append([InlineKeyboardButton(
            text=f"📖 {name}", callback_data=f"bk_{subject_code}_{lang}_{start+i}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅", callback_data=f"bp_{subject_code}_{lang}_{page-1}"))
    if end < len(books):
        nav.append(InlineKeyboardButton(text="➡", callback_data=f"bp_{subject_code}_{lang}_{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="⬅ Артқа / Назад / Back", callback_data=f"books_{subject_code}")])
    rows.append([InlineKeyboardButton(text="🏠 Таңдаулар / Меню / Menu", callback_data="go_main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

@dp.callback_query(lambda c: c.data and c.data.startswith("bl_"))
async def booklang_handler(callback: types.CallbackQuery):
    _, subject_code, lang = callback.data.split("_", 2)
    books = BOOKS_DB.get(subject_code, {}).get(lang, [])
    name = SUBJECT_NAMES.get(subject_code, "📚 Другое")
    lang_name = {"rus": "🇷🇺 Русский", "kaz": "🇰🇿 Қазақша", "eng": "🇬🇧 English"}.get(lang, lang)
    try:
        await callback.message.edit_caption(
            caption=tr(callback.from_user.id, "list_header", name=name, lang=lang_name, n=len(books)),
            reply_markup=booklist_inline(subject_code, lang, 0)
        )
    except:
        await callback.message.edit_text(
            text=tr(callback.from_user.id, "list_header", name=name, lang=lang_name, n=len(books)),
            reply_markup=booklist_inline(subject_code, lang, 0)
        )
    await callback.answer()

@dp.callback_query(lambda c: c.data and c.data.startswith("bp_"))
async def bookpage_handler(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    subject_code = parts[1]
    lang = parts[2]
    page = int(parts[3])
    name = SUBJECT_NAMES.get(subject_code, "📚 Другое")
    lang_name = {"rus": "🇷🇺 Русский", "kaz": "🇰🇿 Қазақша", "eng": "🇬🇧 English"}.get(lang, lang)
    books = BOOKS_DB.get(subject_code, {}).get(lang, [])
    try:
        await callback.message.edit_caption(
            caption=tr(callback.from_user.id, "list_header", name=name, lang=lang_name, n=len(books)),
            reply_markup=booklist_inline(subject_code, lang, page)
        )
    except:
        await callback.message.edit_text(
            text=tr(callback.from_user.id, "list_header", name=name, lang=lang_name, n=len(books)),
            reply_markup=booklist_inline(subject_code, lang, page)
        )
    await callback.answer()

def book_card_keyboard(subject_code, lang, idx, url, uid=None):
    likes, dislikes = get_votes(url)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Жүктеу / Скачать / Download", url=url)],
        [InlineKeyboardButton(text=tr(uid, "fav_add_btn") if uid else "⭐ Таңдаулыға қосу", callback_data=f"fav_add_{subject_code}_{lang}_{idx}")],
        [
            InlineKeyboardButton(text=f"👍 {likes}", callback_data=f"rate_up_{subject_code}_{lang}_{idx}"),
            InlineKeyboardButton(text=f"👎 {dislikes}", callback_data=f"rate_dn_{subject_code}_{lang}_{idx}"),
        ],
        [InlineKeyboardButton(text="⬅ Артқа / Назад / Back", callback_data=f"bl_{subject_code}_{lang}")],
        [InlineKeyboardButton(text="🏠 Таңдаулар / Меню / Menu", callback_data="go_main_menu")],
    ])

@dp.callback_query(lambda c: c.data and c.data.startswith("bk_"))
async def bookopen_handler(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    subject_code = parts[1]
    lang = parts[2]
    idx = int(parts[3])
    books_list = BOOKS_DB.get(subject_code, {}).get(lang, [])
    if idx >= len(books_list):
        await callback.answer(tr(callback.from_user.id, "book_nf_alert"), show_alert=True)
        return
    book = books_list[idx]
    name = book["file_name"].replace(".pdf","").replace(".djvu","").replace("_"," ")
    lang_name = {"rus": "🇷🇺 Русский", "kaz": "🇰🇿 Қазақша", "eng": "🇬🇧 English"}.get(lang, lang)
    subject_name = SUBJECT_NAMES.get(subject_code, "📚 Другое")
    caption = (
        f"╔══════════════════════╗\n"
        f"  📖 {name[:40]}\n"
        f"╚══════════════════════╝\n\n"
        f"📚 {tr(callback.from_user.id, 'card_subject')} {subject_name}\n"
        f"🌐 {tr(callback.from_user.id, 'card_lang')} {lang_name}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 @library_adasan"
    )
    keyboard = book_card_keyboard(subject_code, lang, idx, book["url"], callback.from_user.id)
    sent = False
    cover_id = book.get("photo_message_id")
    source_chat = f"@{CHANNEL.lstrip('@')}"
    if cover_id:
        # Сначала копируем обложку с карточкой. Если Telegram не разрешит копирование,
        # пробуем переслать исходное фото отдельным сообщением.
        try:
            await bot.copy_message(
                chat_id=callback.message.chat.id,
                from_chat_id=source_chat,
                message_id=int(cover_id),
                caption=caption,
                reply_markup=keyboard,
            )
            sent = True
        except Exception as e:
            logger.warning(f"Обложка не скопировалась (пост {cover_id}): {e}")
            try:
                await bot.forward_message(
                    chat_id=callback.message.chat.id,
                    from_chat_id=source_chat,
                    message_id=int(cover_id),
                )
                await bot.send_message(
                    chat_id=callback.message.chat.id,
                    text=caption,
                    reply_markup=keyboard,
                )
                sent = True
            except Exception as forward_error:
                logger.warning(f"Обложка не переслалась (пост {cover_id}): {forward_error}")
    if not sent:
        # Не показываем тематическую иллюстрацию как будто это обложка книги.
        # Если настоящий снимок недоступен, отправляем исходный пост с книгой.
        try:
            await bot.copy_message(
                chat_id=callback.message.chat.id,
                from_chat_id=source_chat,
                message_id=int(book["message_id"]),
                caption=caption,
                reply_markup=keyboard,
            )
            sent = True
        except Exception as e:
            logger.warning(f"Пост книги не скопировался ({book.get('message_id')}): {e}")
    if not sent:
        await bot.send_message(
            chat_id=callback.message.chat.id,
            text=caption,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📥 Жүктеу / Скачать", url=book["url"])],
                [InlineKeyboardButton(text="⬅ Артқа / Назад / Back", callback_data=f"bl_{subject_code}_{lang}")],
            ]),
        )
    # Сохраняем в историю
    book_name_short = name[:50]
    add_book_history(callback.from_user.id, subject_code, lang, idx, book_name_short, book["url"])
    record_book_open(book["url"], book_name_short, subject_code, lang)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()

# =========================
# CALLBACK — Избранное
# =========================
@dp.callback_query(lambda c: c.data and c.data.startswith("fav_add_"))
async def fav_add_handler(callback: types.CallbackQuery):
    parts = callback.data.replace("fav_add_", "").split("_")
    subject_code = parts[0]
    lang = parts[1]
    idx = int(parts[2])
    db_books = BOOKS_DB.get(subject_code, {}).get(lang, [])
    if idx >= len(db_books):
        await callback.answer(tr(callback.from_user.id, "book_nf_alert"), show_alert=True)
        return
    book = db_books[idx]
    book_name = book["file_name"].replace(".pdf","").replace(".djvu","").replace("_"," ")[:50]
    book_url = book["url"]
    added = add_favorite(callback.from_user.id, subject_code, lang, idx, book_name, book_url)
    if added:
        await callback.answer(tr(callback.from_user.id, "fav_added"), show_alert=True)
    else:
        await callback.answer(tr(callback.from_user.id, "fav_exists"), show_alert=True)


async def fav_del_handler(callback: types.CallbackQuery):
    url = callback.data.replace("fav_del_", "")
    remove_favorite(callback.from_user.id, url)
    await callback.answer(tr(callback.from_user.id, "fav_removed"), show_alert=True)
    favs = get_favorites(callback.from_user.id)
    if not favs:
        try:
            await callback.message.edit_text(
                "⭐ Таңдаулылар\n\nСіздің таңдаулыларыңыз жоқ.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 Таңдаулар / Меню / Menu", callback_data="go_main_menu")]
                ])
            )
        except:
            pass
        return
    rows = []
    for sc, lg, bi, bn, bu in favs:
        rows.append([
            InlineKeyboardButton(text=f"📖 {bn[:30]}", callback_data=f"bk_{sc}_{lg}_{bi}"),
            InlineKeyboardButton(text="🗑", callback_data=f"fav_del_{bu}"),
        ])
    rows.append([InlineKeyboardButton(text="🏠 Таңдаулар / Меню / Menu", callback_data="go_main_menu")])
    try:
        await callback.message.edit_text(
            f"⭐ Таңдаулылар ({len(favs)} кітап):",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )
    except:
        pass


# =========================
# КНОПКИ НИЖНЕЙ КЛАВИАТУРЫ
# =========================
@dp.message(lambda m: m.text and m.text.lower() == "📖 история")
async def history_button(message: types.Message):
    history = get_book_history(message.from_user.id, limit=10)
    if not history:
        await message.answer(
            "📖 История пуста\n\nАшқан кітаптарыңыз осында көрінеді.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Меню", callback_data="go_main_menu")]
            ])
        )
        return
    rows = []
    for sc, lg, bi, bn, bu, opened_at in history:
        date_str = opened_at[:10] if opened_at else ""
        flag = {"rus": "🇷🇺", "kaz": "🇰🇿", "eng": "🇬🇧"}.get(lg, "📖")
        rows.append([InlineKeyboardButton(
            text=f"{flag} {bn[:28]} ({date_str})",
            callback_data=f"bk_{sc}_{lg}_{bi}"
        )])
    rows.append([InlineKeyboardButton(text="🏠 Меню", callback_data="go_main_menu")])
    await message.answer(
        f"📖 Соңғы {len(history)} кітап / Последние {len(history)} книг:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )


@dp.message(lambda m: m.text and m.text.lower() in SUBJECTS)
async def open_subject(message: types.Message):
    code = SUBJECTS[message.text.lower()]
    await send_subject_menu(message.chat.id, code)

@dp.message(lambda m: m.text and m.text.lower() == "⭐ таңдаулылар")
async def favorites_button(message: types.Message):
    favs = get_favorites(message.from_user.id)
    if not favs:
        await message.answer(
            "⭐ Таңдаулылар\n\nСіздің таңдаулыларыңыз жоқ.\n\nКітапты оқып жатқанда ⭐ батырмасын басыңыз!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Таңдаулар / Меню / Menu", callback_data="go_main_menu")]
            ])
        )
        return
    rows = []
    for sc, lg, bi, bn, bu in favs:
        rows.append([
            InlineKeyboardButton(text=f"📖 {bn[:30]}", callback_data=f"bk_{sc}_{lg}_{bi}"),
            InlineKeyboardButton(text="🗑", callback_data=f"fav_del_{bu}"),
        ])
    rows.append([InlineKeyboardButton(text="🏠 Таңдаулар / Меню / Menu", callback_data="go_main_menu")])
    await message.answer(tr(message.from_user.id, "favs_title", n=len(favs)),
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

@dp.message(lambda m: m.text and m.text.lower() == "📋 барлық пәндер")
async def all_subjects_button(message: types.Message):
    await send_catalog(message)   # 14 предметов + разделы из хэштегов
    return
    await message.answer(
        "📋 Барлық пәндер / Все предметы / All subjects:\n\nПәнді таңдаңыз:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔬 Гистология", callback_data="subject_gistologiya"),
             InlineKeyboardButton(text="🦴 Анатомия",   callback_data="subject_anatomiya")],
            [InlineKeyboardButton(text="🧪 Биохимия",   callback_data="subject_biohimiya"),
             InlineKeyboardButton(text="⚡ Физиология", callback_data="subject_fiziologiya")],
            [InlineKeyboardButton(text="🏥 Ішкі аурулар", callback_data="subject_ishki"),
             InlineKeyboardButton(text="🔥 Патфиз",       callback_data="subject_patfiz")],
            [InlineKeyboardButton(text="🔭 Патанат", callback_data="subject_patanat"),
             InlineKeyboardButton(text="🗺 Топанат", callback_data="subject_toanat")],
            [InlineKeyboardButton(text="💊 Фармакология", callback_data="subject_farmakologiya"),
             InlineKeyboardButton(text="🦠 Микробиология", callback_data="subject_mikrobiologiya")],
            [InlineKeyboardButton(text="🧬 Генетика", callback_data="subject_genetika"),
             InlineKeyboardButton(text="⚗️ Биофизика", callback_data="subject_biofizika")],
            [InlineKeyboardButton(text="📜 Тарих", callback_data="subject_tarih"),
             InlineKeyboardButton(text="✂️ Хирургия", callback_data="subject_hirurgiya")],
        ])
    )

# =========================
# КОМАНДА — история книг
# =========================
@dp.message(Command("history"))
async def history_command(message: types.Message):
    history = get_book_history(message.from_user.id, limit=10)
    if not history:
        await message.answer(
            "📖 История пуста\n\nАшқан кітаптарыңыз осында көрінеді.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Меню", callback_data="go_main_menu")]
            ])
        )
        return
    rows = []
    for sc, lg, bi, bn, bu, opened_at in history:
        date_str = opened_at[:10] if opened_at else ""
        flag = {"rus": "🇷🇺", "kaz": "🇰🇿", "eng": "🇬🇧"}.get(lg, "📖")
        rows.append([InlineKeyboardButton(
            text=f"{flag} {bn[:28]} ({date_str})",
            callback_data=f"bk_{sc}_{lg}_{bi}"
        )])
    rows.append([InlineKeyboardButton(text="🏠 Меню", callback_data="go_main_menu")])
    await message.answer(
        f"📖 Соңғы {len(history)} кітап / Последние {len(history)} книг:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )

# =========================
# КОМАНДА — рассылка (только админ)
# =========================
@dp.message(Command("broadcast"))
async def broadcast_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Рұқсат жоқ!")
        return
    text = message.text.replace("/broadcast", "", 1).strip()
    if not text:
        await message.answer(
            "📢 Использование:\n/broadcast Ваш текст сообщения\n\nПример:\n/broadcast 📚 Жаңа кітаптар қосылды!"
        )
        return
    user_ids = get_all_user_ids()
    sent = 0
    failed = 0
    await message.answer(f"⏳ Рассылка начата... ({len(user_ids)} пользователей)")
    for uid in user_ids:
        try:
            await bot.send_message(chat_id=uid, text=f"📢 Adasan Bot\n\n{text}")
            sent += 1
            await asyncio.sleep(0.05)  # Anti-flood
        except Exception:
            failed += 1
    await message.answer(f"✅ Рассылка завершена!\n\n✔️ Отправлено: {sent}\n❌ Не доставлено: {failed}")

# =========================
# КОМАНДА — детальная статистика (только админ)
# =========================
@dp.message(Command("stats"))
async def stats_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Рұқсат жоқ!")
        return
    total_users, total_searches, top_subjects, daily, new_users, top_books = get_detailed_stats()
    emoji_map = {"gistologiya":"🔬","anatomiya":"🦴","biohimiya":"🧪","fiziologiya":"⚡",
                 "ishki":"🏥","patfiz":"🔥","farmakologiya":"💊","mikrobiologiya":"🦠",
                 "genetika":"🧬","tarih":"📜","hirurgiya":"✂️","biofizika":"⚗️"}
    text = (
        "📊 ДЕТАЛЬНАЯ СТАТИСТИКА\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Барлық пайдаланушылар: {total_users}\n"
        f"🆕 Жаңа (7 күн): {new_users}\n"
        f"🔍 Барлық іздеулер: {total_searches}\n\n"
        "🏆 Танымал пәндер:\n"
    )
    for i, (subj, cnt) in enumerate(top_subjects, 1):
        em = emoji_map.get(subj, "📚")
        text += f"  {i}. {em} {subj}: {cnt}\n"
    text += "\n📅 Белсенділік (7 күн):\n"
    for day, cnt in daily:
        bar = "█" * min(cnt, 20)
        text += f"  {day}: {bar} {cnt}\n"
    monthly, joined = get_monthly_activity()
    if monthly:
        text += "\n🗓 Барлық уақыт, айлар бойынша (іздеу | белсенді | жаңа):\n"
        for m, n_search, n_active in monthly[-24:]:
            text += f"  {m}: 🔍{n_search} | 👤{n_active} | 🆕{joined.get(m, 0)}\n"
    if top_books:
        text += "\n📖 Танымал кітаптар:\n"
        for i, (bname, cnt) in enumerate(top_books, 1):
            text += f"  {i}. {bname[:30]}: {cnt} рет\n"
    top_opens, top_rated, subs = get_extra_stats()
    if top_opens:
        text += "\n🔥 Ашылу саны (есептегіш):\n"
        for i, (bname, cnt) in enumerate(top_opens, 1):
            text += f"  {i}. {bname[:30]}: {cnt}\n"
    if top_rated:
        text += "\n👍👎 Рейтинг:\n"
        for i, (bname, up, down) in enumerate(top_rated, 1):
            text += f"  {i}. {bname[:30]}: 👍{up} 👎{down}\n"
    if subs:
        text += (
            "\n📤 Студент материалдары:\n"
            f"  ⏳ күтуде: {subs.get('pending', 0)} | ✅ қабылданды: {subs.get('approved', 0)} | ❌ қайтарылды: {subs.get('rejected', 0)}\n"
        )
    await message.answer(text)

# =========================
# КОМАНДА — бан пользователя (только админ)
# =========================
@dp.message(Command("users"))
async def users_command(message: types.Message):
    """Админ: список всех пользователей бота (кто пользуется)."""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Рұқсат жоқ!")
        return
    rows = get_users_list()
    if not rows:
        await message.answer("Пока нет пользователей.")
        return
    from html import escape
    header = f"👥 <b>Пайдаланушылар: {len(rows)}</b>\n\n"
    lines = []
    for i, (uid, uname, fname, lang, joined, n) in enumerate(rows, 1):
        name = escape((fname or "—").strip() or "—")
        if uname:
            link = f'<a href="https://t.me/{escape(uname)}">@{escape(uname)}</a>'
        else:
            link = f'<a href="tg://user?id={uid}">профиль</a>'
        lines.append(f"{i}. {name} — {link}")
    chunk = header
    for line in lines:
        if len(chunk) + len(line) + 1 > 3800:   # лимит Telegram 4096
            await message.answer(chunk, parse_mode="HTML", disable_web_page_preview=True)
            chunk = ""
        chunk += line + "\n"
    if chunk.strip():
        await message.answer(chunk, parse_mode="HTML", disable_web_page_preview=True)

@dp.message(Command("ban"))
async def ban_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Рұқсат жоқ!")
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer(
            "Использование:\n"
            "/ban @username [причина]\n"
            "/ban 123456789 [причина]\n\n"
            "Пример:\n/ban @vasya Спам"
        )
        return
    target_input = parts[1]
    reason = parts[2] if len(parts) > 2 else "Без причины"
    target_id = None
    target_name = target_input
    if target_input.startswith("@"):
        username = target_input.lstrip("@")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT user_id, first_name FROM users WHERE username=?", (username,))
        row = c.fetchone()
        conn.close()
        if row:
            target_id = row[0]
            target_name = f"{row[1]} ({target_input})"
        else:
            await message.answer(
                f"❌ Пайдаланушы табылмады: {target_input}\n\n"
                f"⚠️ Пайдаланушы ботты кем дегенде бір рет қолданған болуы керек."
            )
            return
    else:
        try:
            target_id = int(target_input)
        except ValueError:
            await message.answer("❌ @username немесе ID (сан) жазыңыз!")
            return
    ban_user(target_id, reason)
    try:
        await bot.send_message(
            target_id,
            f"🚫 Сіз бұғатталдыңыз / Вы заблокированы администратором.\n\n"
            f"📝 Себеп / Причина: {reason}\n\n"
            f"Егер қате болса / Если это ошибка:\n"
            f"👉 @Tg_Adasan"
        )
    except Exception:
        pass
    await message.answer(
        f"✅ Пайдаланушы бұғатталды!\n\n"
        f"👤 Кім: {target_name}\n"
        f"🆔 ID: {target_id}\n"
        f"📝 Себеп: {reason}"
    )

@dp.message(Command("unban"))
async def unban_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Рұқсат жоқ!")
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Использование: /unban <user_id>")
        return
    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("❌ user_id должен быть числом!")
        return
    unban_user(target_id)
    try:
        await bot.send_message(target_id, "✅ Сіздің бұғатыңыз алынды / Ваша блокировка снята.")
    except Exception:
        pass
    await message.answer(f"✅ Пайдаланушы бұғаттан шығарылды! ID: {target_id}")

@dp.message(Command("banlist"))
async def banlist_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Рұқсат жоқ!")
        return
    banned = get_banned_list()
    if not banned:
        await message.answer("✅ Бұғатталған пайдаланушылар жоқ.")
        return
    text = f"🚫 Бұғатталғандар ({len(banned)}):\n\n"
    rows = []
    for uid, username, fname, banned_at, reason in banned:
        uname = f"@{username}" if username else f"id:{uid}"
        fname = fname or "?"
        date_str = banned_at[:10] if banned_at else "?"
        text += f"👤 {fname} ({uname})\n🆔 {uid}\n📅 {date_str}\n📝 {reason}\n\n"
        rows.append([InlineKeyboardButton(
            text=f"🔓 Разблокировать {fname[:15]}",
            callback_data=f"unban_{uid}"
        )])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

@dp.callback_query(lambda c: c.data and c.data.startswith("unban_"))
async def unban_callback(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Рұқсат жоқ!", show_alert=True)
        return
    target_id = int(callback.data.replace("unban_", ""))
    unban_user(target_id)
    try:
        await bot.send_message(target_id, "✅ Сіздің бұғатыңыз алынды / Ваша блокировка снята.")
    except Exception:
        pass
    await callback.answer(f"✅ {target_id} бұғаттан шығарылды!", show_alert=True)
    try:
        await callback.message.delete()
    except Exception:
        pass


@dp.callback_query(lambda c: c.data == "noop")
async def noop_callback(callback: types.CallbackQuery):
    await callback.answer()

# =========================
# КОМАНДА — обновить базу книг (только админ)
# =========================
@dp.message(Command("update_books"))
async def update_books_command(message: types.Message):
    global BOOKS_DB
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Рұқсат жоқ!")
        return

    await message.answer("⏳ Канал оқылуда... 2-5 минут күтіңіз")

    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto
        import json as _json2
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _telethon_client(session):
            """Подключается БЕЗ интерактивного входа.

            `async with TelegramClient(...)` вызывает start(), а он при неавторизованной
            сессии сам просит телефон/код через input() — на сервере это зависает и
            Telegram шлёт «лишние» коды. Здесь только connect() + проверка авторизации.
            """
            client = TelegramClient(
                session, API_ID, API_HASH,
                lang_code="ru", system_lang_code="ru-RU",
            )
            await client.connect()
            try:
                if not await client.is_user_authorized():
                    raise RuntimeError(
                        "Telethon-сессия не авторизована. Создайте новую: "
                        "python create_telethon_string.py (вход по QR), затем задайте "
                        "TELETHON_SESSION_STRING."
                    )
                yield client
            finally:
                await client.disconnect()

        HASHTAG_MAP = {
            "#гистология": "gistologiya", "#анатомия": "anatomiya",
            "#анат": "anatomiya", "#anat": "anatomiya", "#anatom": "anatomiya", "#anatomy": "anatomiya",
            "#биохимия": "biohimiya", "#биохим": "biohimiya", "#биох": "biohimiya", "#бхим": "biohimiya", "#бх": "biohimiya", "#bkh": "biohimiya", "#biochem": "biohimiya", "#biochemistry": "biohimiya",
            "#физиология": "fiziologiya",
            "#ішкіаурулар": "ishki", "#ішкі": "ishki",
            "#пропедевтика": "ishki", "#пропедевтики": "ishki", "#пропед": "ishki",
            "#внутренниеболезни": "ishki", "#внутренние": "ishki",
            "#патфиз": "patfiz", "#патанат": "patanat",
            "#топанат": "toanat", "#фармакология": "farmakologiya",
            "#фарма": "farmakologiya", "#фармо": "farmakologiya", "#фармако": "farmakologiya",
            "#pharmacology": "farmakologiya", "#pharmaco": "farmakologiya", "#pharma": "farmakologiya",
            "#микробиология": "mikrobiologiya", "#хирургия": "hirurgiya",
            "#генетика": "genetika", "#биофизика": "biofizika",
            "#тарих": "tarih",
        }
        SUBJECT_KW = {
            "anatomiya":      ["анатом","anatom","нетт","netter","синельник","сапин","билич","гайворон"],
            "gistologiya":    ["гистол","histol","цитол","эмбриол","ажаев","афанас","аяпов","тұңғыш"],
            "biohimiya":      ["биохим","биохи","биоким","biochem","biochemistry","bkh","северин","harper"],
            "fiziologiya":    ["физиол","physiol","гайтон","судаков"],
            "ishki":          ["ішкі","ishki","внутренн","терапи","пропедевт","пропед","неотложн"],
            "patfiz":         ["патофиз","patofiz","патфиз"],
            "patanat":        ["патанат","патологич","роббинс","струков"],
            "toanat":         ["топограф","топка","оперативн"],
            "farmakologiya":  ["фармакол","фарма","фармо","фармако","pharmacology","pharmaco","pharmac","pharma","катцунг","харкевич"],
            "hirurgiya":      ["хирург","hirurg"],
            "mikrobiologiya": ["микробиол","microbiol"],
            "genetika":       ["генет","genet"],
            "biofizika":      ["биофиз","biofiz"],
            "tarih":          ["тарих","tarih"],
        }
        LANG_KW = {
            "kaz": ["қаз","каз","қазақ","кітап","оқу","адам","жалпы","медициналық"],
            "eng": ["eng","english","netter","sobotta","gray","high-yield","textbook"],
        }

        def detect_subj(text):
            tl = text.lower().replace("ё", "е")
            # Проверяем каждый реальный хэштег отдельно и сначала сводим алиасы к предмету.
            # Например, #анат и #анатомия дают один код, а #патанат не путается с #анат.
            tag_tokens = ["#" + tag for tag in re.findall(r"(?<!\w)#(\w+)", tl)]
            tag_codes = list(dict.fromkeys(HASHTAG_MAP[tag] for tag in tag_tokens if tag in HASHTAG_MAP))
            if len(tag_codes) == 1:
                return tag_codes[0]
            if len(tag_codes) > 1:
                text_without_tags = re.sub(r"#\w+", " ", tl)
                best_tag_code, best_tag_len = None, 0
                for subj, kws in SUBJECT_KW.items():
                    for kw in kws:
                        kw = kw.lower()
                        if kw in text_without_tags and len(kw) > best_tag_len:
                            best_tag_code, best_tag_len = subj, len(kw)
                return best_tag_code or tag_codes[0]
            # составные названия
            if "патолог" in tl and "физиол" in tl:
                return "patfiz"
            if "патолог" in tl and "анатом" in tl:
                return "patanat"
            if "топограф" in tl and "анатом" in tl:
                return "toanat"
            # обычные ключевые слова: самое длинное совпадение
            best, best_len = None, 0
            for subj, kws in SUBJECT_KW.items():
                for kw in kws:
                    kw = kw.lower()
                    if kw in tl and len(kw) > best_len:
                        best, best_len = subj, len(kw)
            if best:
                return best
            # Последний общий разбор использует те же короткие/многоязычные синонимы,
            # что и поиск предмета (например, «БХ», «Биохим», «pharma»).
            alias_code = find_subject(text)
            return alias_code if alias_code in SUBJECTS.values() else "other"

        def detect_lang(text):
            tl = text.lower()
            for lang, kws in LANG_KW.items():
                for kw in kws:
                    if kw.lower() in tl:
                        return lang
            return "rus"

        def get_fname(doc):
            for attr in doc.attributes:
                if hasattr(attr, "file_name") and attr.file_name:
                    return attr.file_name
            return "unknown"

        result = {"new_db": {}, "total": 0, "covers": 0, "error": None}

        async def collect():
            try:
                new_db = {}
                total = 0
                timeline = []       # (id, фото, документ, дата, id_альбома) — посты канала
                book_entries = []   # (запись_книги, id_поста, дата, id_альбома)
                session_string = os.getenv("TELETHON_SESSION_STRING", "").strip()
                if session_string:
                    session = StringSession(session_string)
                else:
                    session_path = os.getenv(
                        "TELETHON_SESSION_PATH",
                        os.path.join(BASE_DIR, "update_session"),
                    )
                    if not os.path.isfile(session_path + ".session"):
                        raise RuntimeError(
                            "Для обновления каталога задайте TELETHON_SESSION_STRING "
                            "в переменных хостинга или подключите защищённый файл "
                            "сессии через TELETHON_SESSION_PATH."
                        )
                    session = session_path
                async with _telethon_client(session) as client:
                    async for msg in client.iter_messages(CHANNEL, limit=5000):
                        is_document = bool(msg.media and isinstance(msg.media, MessageMediaDocument))
                        is_photo = bool(msg.media and isinstance(msg.media, MessageMediaPhoto))
                        if is_document and getattr(msg.media.document, "mime_type", "").startswith("image/"):
                            is_photo, is_document = True, False
                        grouped_id = getattr(msg, "grouped_id", None)
                        timeline.append((msg.id, is_photo, is_document, msg.date, grouped_id))
                        if not (msg.media and isinstance(msg.media, MessageMediaDocument)):
                            continue
                        doc = msg.media.document
                        fname = get_fname(doc)
                        mime = getattr(doc, "mime_type", "")
                        is_book = (
                            mime in ["application/pdf", "application/epub+zip"] or
                            any(fname.endswith(ext) for ext in [".pdf", ".djvu", ".epub"])
                        )
                        if not is_book:
                            continue
                        caption = msg.text or ""
                        subj = detect_subj(fname + " " + caption)
                        lang = detect_lang(fname + " " + caption)
                        if lang == "rus" and _is_english_filename(fname):
                            lang = "eng"
                        if subj not in new_db:
                            new_db[subj] = {"rus": [], "kaz": [], "eng": []}
                        entry = {
                            "message_id": msg.id,
                            "file_name":  fname,
                            "caption":    caption[:300],
                            "url":        f"https://t.me/library_adasan/{msg.id}",
                        }
                        new_db[subj][lang].append(entry)
                        book_entries.append((entry, msg.id, msg.date, grouped_id))
                        total += 1

                # Берём ближайший фото-пост перед файлом (до 10 минут), даже если
                # между обложкой и PDF стоит короткое текстовое сообщение. Через другой
                # документ обложку не переносим, чтобы не прикрепить чужое фото.
                timeline.sort(key=lambda t: t[0])
                entries_by_id = {mid: (entry, mdate, grouped_id)
                                 for entry, mid, mdate, grouped_id in book_entries}
                album_photo = {}
                for mid, is_photo, _is_document, _mdate, grouped_id in timeline:
                    if is_photo and grouped_id:
                        album_photo.setdefault(grouped_id, mid)
                covers = 0
                for entry, _mid, _mdate, grouped_id in book_entries:
                    if grouped_id and grouped_id in album_photo:
                        entry["photo_message_id"] = album_photo[grouped_id]
                        covers += 1

                last_photo = None
                last_document_id = 0
                for mid, is_photo, is_document, mdate, _grouped_id in timeline:
                    if is_photo:
                        last_photo = (mid, mdate)
                    if not is_document:
                        continue
                    book_item = entries_by_id.get(mid)
                    if book_item:
                        entry, book_date, _book_group = book_item
                        if (not entry.get("photo_message_id") and last_photo and
                                last_photo[0] > last_document_id and
                                0 <= (book_date - last_photo[1]).total_seconds() <= 600):
                            entry["photo_message_id"] = last_photo[0]
                            covers += 1
                    last_document_id = mid
                result["covers"] = covers
                result["new_db"] = new_db
                result["total"]  = total
            except Exception as e:
                result["error"] = str(e)

        import threading as _threading
        import asyncio as _asyncio

        def run_collect():
            loop = _asyncio.new_event_loop()
            _asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(collect())
            finally:
                loop.close()
                _asyncio.set_event_loop(None)

        t = _threading.Thread(target=run_collect)
        t.start()
        t.join(timeout=300)

        if result["error"]:
            await message.answer(f"❌ Қате: {result['error'][:300]}")
            return

        new_db = result["new_db"]
        total  = result["total"]
        normalize_existing_catalog(new_db)  # синонимы и тома одной серии без ручной сортировки
        inherit_series_covers(new_db)   # у следующих томов — обложка серии
        build_dynamic_catalog(new_db)   # разделы из хэштегов (#пропедевтика и т.д.)
        apply_sort_overrides(new_db)   # ручная сортировка из /sort_other не сбрасывается
        _refresh_catalog_names(new_db)

        db_path = os.path.join(BASE_DIR, "books_db.json")
        with open(db_path, "w", encoding="utf-8") as f:
            _json2.dump(new_db, f, ensure_ascii=False, indent=2)

        BOOKS_DB = new_db

        stats_text = "\n".join([
            f"  📚 {s}: {len(l.get('rus',[]))} рус | {len(l.get('kaz',[]))} қаз | {len(l.get('eng',[]))} eng"
            for s, l in sorted(new_db.items()) if s != "other"
        ])

        await message.answer(
            f"✅ Жаңартылды!\n\n"
            f"📖 Барлығы: {total} кітап\n"
            f"🖼 Мұқабасы бар / С обложкой: {result['covers']}\n\n"
            f"{stats_text}"
        )

    except ImportError:
        await message.answer("❌ telethon орнатылмаған!\npip install telethon")
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logging.error(tb)
        print(tb)
        await message.answer(f"❌ Қате: {str(e)[:300]}")

# =========================
# ПОПУЛЯРНОЕ / ОЦЕНКИ / МАТЕРИАЛЫ ОТ СТУДЕНТОВ
# =========================
import html as _html

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

def find_book_by_url(url):
    for sc, langs in BOOKS_DB.items():
        for lg, books in langs.items():
            for i, bk in enumerate(books):
                if bk.get("url") == url:
                    return sc, lg, i
    return None

def save_books_db():
    path = os.path.join(BASE_DIR, "books_db.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        _json.dump(BOOKS_DB, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

# =========================
# РАЗБОР РАЗДЕЛА "other" (/sort_other, только админ)
# =========================
# --- sort_other: logic ---
_sort_overrides_path = os.path.join(BASE_DIR, "sort_overrides.json")
_sort_skipped = set()   # message_id, пропущенные до перезапуска бота

def _load_sort_overrides():
    try:
        with open(_sort_overrides_path, encoding="utf-8") as f:
            return _json.load(f)
    except Exception:
        return {}

def _save_sort_overrides(ov):
    tmp = _sort_overrides_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        _json.dump(ov, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _sort_overrides_path)

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

@dp.message(Command("sort_other"))
async def sort_other_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Рұқсат жоқ!")
        return
    text, kb = _sort_card()
    await message.answer(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)

@dp.callback_query(lambda c: c.data and c.data.startswith("srt_"))
async def sort_other_callback(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Рұқсат жоқ!", show_alert=True)
        return
    try:
        _, code, mid_s = callback.data.split("_", 2)
        mid = int(mid_s)
    except ValueError:
        await callback.answer("Қате / Ошибка данных")
        return

    if code == "files":
        await callback.answer("💾 Отправляю файлы")
        await _sort_send_files()
        return
    if code == "skip":
        _sort_skipped.add(mid)
        note = "⏭ Пропущено"
    elif code == "keep":
        ov = _load_sort_overrides()
        ov[str(mid)] = "other"
        _save_sort_overrides(ov)
        note = "📦 Остаётся в other"
    elif code in SUBJECTS.values():
        note = f"✅ → {code}" if _sort_move(mid, code) else "⚠️ Книга уже перенесена"
    else:
        await callback.answer("Неизвестный предмет")
        return

    await callback.answer(note)
    text, kb = _sort_card()
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb,
                                         disable_web_page_preview=True)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb,
                                      disable_web_page_preview=True)
    if kb is None:               # разбор закончен — сразу присылаем файлы
        await _sort_send_files()

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

_DYN_NAMES = {}            # code -> «📖 Название» для разделов, созданных из хэштегов
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

_orig_send_subject_menu = send_subject_menu
async def send_subject_menu(chat_id, code):
    """Раздел из хэштегов открывается сразу списком языков (без силлабусов и препаратов)."""
    if code in _DYN_NAMES:
        total = sum(len(v) for v in BOOKS_DB.get(code, {}).values())
        await bot.send_message(
            chat_id,
            f"{_DYN_NAMES[code]}\n\n📖 Барлығы: {total} кітап\n\n"
            "👇 Тілді таңдаңыз / Выберите язык / Choose language:",
            reply_markup=lang_inline(code, chat_id)
        )
        return
    await _orig_send_subject_menu(chat_id, code)

_orig_lang_inline = lang_inline
def lang_inline(subject_code, uid=None):
    kb = _orig_lang_inline(subject_code, uid)
    if subject_code not in _DYN_NAMES:
        return kb
    rows = []
    for row in kb.inline_keyboard:                   # «Назад» ведёт в каталог, а не в меню предмета
        rows.append([
            InlineKeyboardButton(text=b.text, callback_data="catalog_open")
            if b.callback_data == f"subject_{subject_code}" else b
            for b in row
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

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
    rows.append([InlineKeyboardButton(text="🏠 Таңдаулар / Меню / Menu", callback_data="go_main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

CATALOG_TEXT = "📋 Барлық пәндер / Все предметы / All subjects:\n\nПәнді таңдаңыз:"

async def send_catalog(message: types.Message):
    await message.answer(CATALOG_TEXT, reply_markup=catalog_keyboard())

@dp.message(Command("catalog"))
async def catalog_command(message: types.Message):
    await send_catalog(message)

@dp.callback_query(lambda c: c.data == "catalog_open")
async def catalog_open_callback(callback: types.CallbackQuery):
    await bot.send_message(callback.message.chat.id, CATALOG_TEXT, reply_markup=catalog_keyboard())
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()

# =========================
# ОБЛОЖКИ ТОМОВ: у 2-го, 3-го, 4-го тома нет своего фото-поста — берём обложку серии
# =========================
# --- covers: logic ---
_VOL_RE = re.compile(
    r"(?<!\w)(?:часть|ч|том|т[oо]м|т|бөлім|t[oо]m|vol(?:ume)?|volume|part|pt)\.?\s*\d+(?!\w)"
    r"|(?<!\w)\d+\s*-?\s*(?:й|я|ый|ая|ой|ий)?\s*(?:том|т[oо]м|часть|т|ч|t[oо]m|vol(?:ume)?|volume|part|pt)(?!\w)\.?"
    r"|(?<=[^\W\d_])\d+\s*-?\s*(?:й|я|ый|ая|ой|ий)?\s*(?:том|т[oо]м|часть|т|ч)(?!\w)\.?",
    re.I
)
_VOLUME_NUMBER_RE = re.compile(
    r"(?<!\w)(?:часть|ч|том|т[oо]м|т|бөлім|t[oо]m|vol(?:ume)?|volume|part|pt)\.?\s*(\d+)(?!\w)"
    r"|(?<!\w)(\d+)\s*-?\s*(?:й|я|ый|ая|ой|ий)?\s*(?:том|т[oо]м|часть|т|ч|t[oо]m|vol(?:ume)?|volume|part|pt)(?!\w)"
    r"|(?<=[^\W\d_])(\d+)\s*-?\s*(?:й|я|ый|ая|ой|ий)?\s*(?:том|т[oо]м|часть|т|ч)(?!\w)",
    re.I
)

_CONFUSABLE_LATIN = str.maketrans({"a":"а", "e":"е", "o":"о", "p":"р", "c":"с", "x":"х", "y":"у", "k":"к", "m":"м", "t":"т", "b":"в", "h":"н"})

def _series_key(file_name):
    """Нормализует название серии и номер тома, включая латинские буквы-двойники."""
    t = (file_name or "").lower().replace("ё", "е")
    t = re.sub(r"\.(pdf|djvu|epub)$", "", t).replace("_", " ")
    has_vol = bool(_VOL_RE.search(t))
    t = _VOL_RE.sub(" ", t)
    # Например, в «2 тoм» латинская o часто попадает вместо кириллической о.
    if re.search(r"[а-яёәіңғүұқөһ]", t):
        t = t.translate(_CONFUSABLE_LATIN)
    has_vol = has_vol or bool(_VOL_RE.search(t))
    t = _VOL_RE.sub(" ", t)
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip(), has_vol


def _volume_number(file_name):
    t = (file_name or "").lower()
    t = re.sub(r"\.(pdf|djvu|epub)$", "", t)
    match = _VOLUME_NUMBER_RE.search(t)
    if not match and re.search(r"[а-яёәіңғүұқөһ]", t):
        match = _VOLUME_NUMBER_RE.search(t.translate(_CONFUSABLE_LATIN))
    if not match:
        return None
    try:
        return int(match.group(1) or match.group(2) or match.group(3))
    except (TypeError, ValueError):
        return None


def normalize_existing_catalog(db):
    """Автоматически объединяет распознанные варианты предметов и тома известных серий."""
    overrides = _load_sort_overrides()
    static_codes = set(SUBJECTS.values())
    entries = []
    for code, langs in db.items():
        for lang, books in langs.items():
            for book in books:
                if str(book.get("message_id")) in overrides:
                    continue
                key, has_volume = _series_key(book.get("file_name", ""))
                if has_volume and len(key) >= 5:
                    entries.append((key, code, lang, book))

    by_series = {}
    for item in entries:
        by_series.setdefault(item[0], []).append(item)

    moves = []
    for group in by_series.values():
        known = {code for _, code, _, _ in group if code in static_codes}
        if len(known) != 1:
            continue
        target = next(iter(known))
        moves.extend((code, lang, book, target) for _, code, lang, book in group if code == "other")

    # Уже имеющиеся неполные записи тоже раскладываются по тем же предметным синонимам,
    # которыми пользуются поиск и /update_books. Стоматология остаётся отдельным динамическим разделом.
    canonical_codes = static_codes | {"stomatologiya"}
    queued = {(str(book.get("message_id")), target) for _, _, book, target in moves}
    for source, langs in db.items():
        if source != "other" and source in static_codes:
            continue
        for lang, books in langs.items():
            for book in books:
                mid = str(book.get("message_id"))
                if mid in overrides or any(item[0] == mid for item in queued):
                    continue
                text = " ".join((source, book.get("subject_title", ""),
                                 book.get("file_name", ""), book.get("caption", "")))
                target = find_subject(text)
                if target in canonical_codes and source != target:
                    moves.append((source, lang, book, target))
                    queued.add((mid, target))

    changed = False
    for source, lang, book, target in moves:
        source_list = db.get(source, {}).get(lang, [])
        try:
            source_list.remove(book)
        except ValueError:
            continue
        if target == "stomatologiya":
            book["subject_title"] = "📖 Стоматология"
        target_list = db.setdefault(target, {}).setdefault(lang, [])
        if book not in target_list:
            target_list.append(book)
            target_list.sort(key=lambda item: item.get("message_id", 0), reverse=True)
        changed = True
    return changed

def inherit_series_covers(db):
    """Если у тома нет своей обложки, а у другого тома этой же серии она есть — берём её.
    Ищем по ВСЕМ предметам (1-й том может лежать в другом разделе). Возвращает число книг с новой обложкой."""
    donors, needy = {}, []
    for sc, langs in db.items():
        for lg, lst in langs.items():
            for b in lst:
                key, has_vol = _series_key(b.get("file_name", ""))
                if len(key) < 6:
                    continue
                if b.get("photo_message_id"):
                    donors.setdefault(key, []).append(b)
                elif has_vol:
                    needy.append((key, b))
    n = 0
    for key, b in needy:
        cands = donors.get(key)
        if cands:
            best = min(cands, key=lambda d: abs(d["message_id"] - b["message_id"]))
            b["photo_message_id"] = best["photo_message_id"]
            n += 1

    # В некоторых публикациях автор/название отсутствуют: файлы называются только
    # «том 1», «том 2» и т.д. Объединяем короткие подряд идущие серии по номерам.
    generic = []
    for sc, langs in db.items():
        for lg, lst in langs.items():
            for b in lst:
                key, has_vol = _series_key(b.get("file_name", ""))
                number = _volume_number(b.get("file_name", ""))
                if has_vol and not key and number is not None:
                    generic.append((b.get("message_id", 0), number, b))
    generic.sort(key=lambda x: x[0])
    clusters = []
    for item in generic:
        if not clusters or item[0] - clusters[-1][-1][0] > 8:
            clusters.append([item])
        else:
            clusters[-1].append(item)
    for group in clusters:
        numbers = [number for _, number, _ in group]
        if len(group) < 3 or len(set(numbers)) != len(numbers) or max(numbers) - min(numbers) + 1 != len(numbers):
            continue
        photo_donors = [b for _, _, b in group if b.get("photo_message_id")]
        if not photo_donors:
            continue
        for _, _, book in group:
            if book.get("photo_message_id"):
                continue
            donor = min(photo_donors, key=lambda d: abs(d["message_id"] - book["message_id"]))
            book["photo_message_id"] = donor["photo_message_id"]
            n += 1
    return n
# --- covers: handlers ---
_catalog_migrated = normalize_existing_catalog(BOOKS_DB)
_catalog_covers_added = inherit_series_covers(BOOKS_DB)
if _catalog_migrated:
    _refresh_catalog_names(BOOKS_DB)
if _catalog_migrated or _catalog_covers_added:
    save_books_db()

# ---------- Закладки убраны: ответ на старые кнопки в чатах ----------
@dp.message(lambda m: m.text and m.text.lower() == "📌 закладки")
async def legacy_bookmark_message(message: types.Message):
    # у части пользователей ещё висит старая клавиатура — обновляем её на новую
    await message.answer("📌 Закладки убрали. Меню обновлено 👇", reply_markup=main_menu_keyboard(get_lang(message.from_user.id)))

@dp.callback_query(lambda c: c.data and c.data.startswith(("bmark_", "bmdel_", "show_bookmarks")))
async def legacy_bookmark_callback(callback: types.CallbackQuery):
    await callback.answer("📌 Закладки убрали / Функция закладок удалена", show_alert=True)

# ---------- Популярное ----------
async def send_popular(message: types.Message):
    buttons = []
    for url, name, opens in get_top_books(10):
        loc = find_book_by_url(url)
        if not loc:
            continue
        sc, lg, bi = loc
        buttons.append([InlineKeyboardButton(
            text=f"🔥 {opens} · {name[:30]}", callback_data=f"bk_{sc}_{lg}_{bi}")])
    if not buttons:
        await message.answer(
            "🔥 Әзірге танымал кітаптар жоқ / Пока нет популярных книг.\n\n"
            "Кітаптарды ашқан сайын тізім толады / Список наполнится, когда книги начнут открывать."
        )
        return
    buttons.append([InlineKeyboardButton(text="🏠 Таңдаулар / Меню / Menu", callback_data="go_main_menu")])
    await message.answer(
        "🔥 Танымал кітаптар / Популярные книги\n\n👇 Таңдаңыз:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )

@dp.message(Command("popular"))
async def popular_command(message: types.Message):
    await send_popular(message)

@dp.message(lambda m: m.text and m.text == "🔥 Популярное")
async def popular_button(message: types.Message):
    await send_popular(message)

# ---------- Оценка 👍/👎 ----------
@dp.callback_query(lambda c: c.data and c.data.startswith("rate_"))
async def rate_handler(callback: types.CallbackQuery):
    try:
        _, direction, subject_code, lang, idx_raw = callback.data.split("_")
        idx = int(idx_raw)
        book = BOOKS_DB[subject_code][lang][idx]
    except (ValueError, KeyError, IndexError):
        await callback.answer(tr(callback.from_user.id, "book_nf_alert"), show_alert=True)
        return
    vote = 1 if direction == "up" else -1
    result = set_vote(callback.from_user.id, book["url"], vote)
    try:
        await callback.message.edit_reply_markup(
            reply_markup=book_card_keyboard(subject_code, lang, idx, book["url"], callback.from_user.id)
        )
    except Exception:
        pass
    if result == 0:
        await callback.answer("Дауыс алынды / Голос убран")
    else:
        await callback.answer("Рахмет! / Спасибо! 🙌")

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

@dp.message(Command("upload"))
async def upload_command(message: types.Message):
    await start_upload(message)

@dp.message(lambda m: m.text and m.text == "📤 Материал жіберу")
async def upload_button(message: types.Message):
    await start_upload(message)

@dp.callback_query(lambda c: c.data == "upl_cancel")
async def upload_cancel(callback: types.CallbackQuery):
    _upload_state.discard(callback.from_user.id)
    try:
        await callback.message.edit_text("Жақсы, болдырмадық / Хорошо, отменили.")
    except Exception:
        pass
    await callback.answer()

def submission_admin_kb(sub_id):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Одобрить", callback_data=f"sbm_ok_{sub_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"sbm_no_{sub_id}"),
    ]])

@dp.message(lambda m: m.document is not None and m.chat.type == "private" and m.from_user and m.from_user.id in _upload_state)
async def receive_material(message: types.Message):
    uid = message.from_user.id
    doc = message.document
    now = time.monotonic()
    if now - _upload_last_time.get(uid, 0) < UPLOAD_COOLDOWN_SECONDS:
        await message.answer("⏳ Подождите немного перед следующей отправкой файла.")
        return
    _upload_last_time[uid] = now
    if doc.file_size is not None and doc.file_size > MAX_UPLOAD_BYTES:
        await message.answer(
            "⚠️ Файл слишком большой. Максимальный размер — 45 МБ."
        )
        return
    fname = doc.file_name or "material"
    if not fname.lower().endswith(UPLOAD_EXT):
        await message.answer(
            "⚠️ Бұл формат қолдау таппайды / Этот формат не подходит.\n"
            "PDF, DOC(X), PPT(X), TXT, EPUB, DJVU жіберіңіз."
        )
        return
    if count_pending_by_user(uid) >= MAX_PENDING_PER_USER:
        _upload_state.discard(uid)
        await message.answer(
            "⏳ Алдыңғы файлдарыңыз әлі тексерілуде. Сәл күте тұрыңыз.\n"
            "Ваши предыдущие файлы ещё на проверке. Подождите немного."
        )
        return
    sub_id = add_submission(uid, message.from_user.username, message.from_user.first_name, doc.file_id, fname)
    who = f"@{message.from_user.username}" if message.from_user.username else (message.from_user.first_name or "—")
    admin_caption = (
        f"📤 Жаңа материал / Новый материал #{sub_id}\n"
        f"👤 {_html.escape(who)} (ID {uid})\n"
        f"📄 {_html.escape(fname)}"
    )
    try:
        await bot.send_document(
            ADMIN_ID, doc.file_id, caption=admin_caption, parse_mode="HTML",
            reply_markup=submission_admin_kb(sub_id)
        )
    except Exception as e:
        logger.error(f"submission to admin failed: {e}")
        set_submission_status(sub_id, "error")
        await message.answer("❌ Қате шықты, кейінірек қайталап көріңіз / Ошибка, попробуйте позже.")
        return
    _upload_state.discard(uid)
    await message.answer(
        "✅ Рахмет! Файл админге тексеруге жіберілді.\n"
        "Спасибо! Файл отправлен админу на проверку.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Таңдаулар / Меню / Menu", callback_data="go_main_menu")]
        ])
    )

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

@dp.callback_query(lambda c: c.data and c.data.startswith("sbm_ok_"))
async def sbm_approve_start(callback: types.CallbackQuery):
    sub, _ = _parse_sub(callback, "sbm_ok_")
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Рұқсат жоқ!", show_alert=True)
        return
    if not sub or sub["status"] != "pending":
        await callback.answer("Бұл өтінім өңделген / Уже обработано", show_alert=True)
        return
    codes = list(SUBJECT_NAMES.keys())
    rows = []
    for i in range(0, len(codes), 2):
        rows.append([
            InlineKeyboardButton(text=SUBJECT_NAMES[c], callback_data=f"sbm_sj_{sub['id']}_{c}")
            for c in codes[i:i + 2]
        ])
    rows.append([InlineKeyboardButton(text="⬅ Назад", callback_data=f"sbm_back_{sub['id']}")])
    try:
        await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except Exception:
        pass
    await callback.answer("Пәнді таңдаңыз / Выберите предмет")

@dp.callback_query(lambda c: c.data and c.data.startswith("sbm_back_"))
async def sbm_back(callback: types.CallbackQuery):
    sub, _ = _parse_sub(callback, "sbm_back_")
    if not sub:
        await callback.answer()
        return
    try:
        await callback.message.edit_reply_markup(reply_markup=submission_admin_kb(sub["id"]))
    except Exception:
        pass
    await callback.answer()

@dp.callback_query(lambda c: c.data and c.data.startswith("sbm_sj_"))
async def sbm_pick_subject(callback: types.CallbackQuery):
    sub, rest = _parse_sub(callback, "sbm_sj_")
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Рұқсат жоқ!", show_alert=True)
        return
    if not sub or sub["status"] != "pending" or not rest or rest[0] not in SUBJECT_HASHTAGS:
        await callback.answer("Бұл өтінім өңделген / Уже обработано", show_alert=True)
        return
    code = rest[0]
    rows = [[InlineKeyboardButton(text=label, callback_data=f"sbm_lg_{sub['id']}_{code}_{lg}")]
            for lg, label in LANG_LABELS.items()]
    rows.append([InlineKeyboardButton(text="⬅ Назад", callback_data=f"sbm_ok_{sub['id']}")])
    try:
        await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except Exception:
        pass
    await callback.answer(SUBJECT_NAMES.get(code, code))

@dp.callback_query(lambda c: c.data and c.data.startswith("sbm_lg_"))
async def sbm_publish(callback: types.CallbackQuery):
    sub, rest = _parse_sub(callback, "sbm_lg_")
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Рұқсат жоқ!", show_alert=True)
        return
    if (not sub or sub["status"] != "pending" or not rest or len(rest) < 2
            or rest[0] not in SUBJECT_HASHTAGS or rest[1] not in LANG_CAPTION):
        await callback.answer("Бұл өтінім өңделген / Уже обработано", show_alert=True)
        return
    code, lang = rest[0], rest[1]
    display_name = sub["file_name"].rsplit(".", 1)[0].replace("_", " ")
    caption = (
        f"📖 {display_name}\n\n"
        f"{SUBJECT_HASHTAGS[code]}\n"
        f"🌐 {LANG_CAPTION[lang]}\n"
        f"📤 Студенттен / От студента"
    )
    try:
        msg = await bot.send_document(CHANNEL, sub["file_id"], caption=caption)
    except Exception as e:
        logger.error(f"publish to channel failed: {e}")
        await callback.answer(
            f"❌ Каналға жариялау мүмкін болмады: {str(e)[:120]}\n"
            "Бот каналда админ болуы керек (хабар жариялау құқығымен).",
            show_alert=True
        )
        return
    BOOKS_DB.setdefault(code, {"rus": [], "kaz": [], "eng": []}).setdefault(lang, []).append({
        "message_id": msg.message_id,
        "file_name": sub["file_name"],
        "caption": caption[:300],
        "url": f"https://t.me/{CHANNEL.lstrip('@')}/{msg.message_id}",
    })
    save_books_db()
    set_submission_status(sub["id"], "approved", code, lang)
    try:
        await callback.message.edit_caption(
            caption=f"✅ Қабылданды / Одобрено #{sub['id']}\n📄 {sub['file_name']}\n"
                    f"{SUBJECT_NAMES.get(code, code)} · {LANG_LABELS[lang]}",
            reply_markup=None
        )
    except Exception:
        pass
    await _notify_user(
        sub["user_id"],
        "🎉 Рахмет! Сіздің материалыңыз кітапханаға қосылды.\n"
        "Спасибо! Ваш материал добавлен в библиотеку."
    )
    await callback.answer("✅ Жарияланды")

@dp.callback_query(lambda c: c.data and c.data.startswith("sbm_no_"))
async def sbm_reject(callback: types.CallbackQuery):
    sub, _ = _parse_sub(callback, "sbm_no_")
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Рұқсат жоқ!", show_alert=True)
        return
    if not sub or sub["status"] != "pending":
        await callback.answer("Бұл өтінім өңделген / Уже обработано", show_alert=True)
        return
    set_submission_status(sub["id"], "rejected")
    try:
        await callback.message.edit_caption(
            caption=f"❌ Қайтарылды / Отклонено #{sub['id']}\n📄 {sub['file_name']}",
            reply_markup=None
        )
    except Exception:
        pass
    await _notify_user(
        sub["user_id"],
        "Рахмет, файлды жібергеніңіз үшін! Бұл жолы кітапханаға қоса алмадық, "
        "бірақ басқа материалдарыңызды жіберуге болады.\n\n"
        "Спасибо, что отправили файл! В этот раз мы не смогли добавить его в библиотеку, "
        "но вы можете присылать другие материалы."
    )
    await callback.answer("Қайтарылды")

# =========================
# ПОИСК
# =========================
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


@dp.message(F.chat.type.in_({"group", "supergroup"}), F.text)
async def group_book_search(message: types.Message):
    # Не отвечаем автопересылкам постов канала и другим ботам.
    # Исключение: сообщение «от имени канала/группы» (sender_chat) — Telegram показывает
    # отправителем служебного бота, но писал живой админ.
    if not message.from_user or message.is_automatic_forward:
        return
    if message.from_user.is_bot and not message.sender_chat:
        return
    text = (message.text or "").strip()
    if len(text) < 4 or len(text) > 100 or text.startswith("/"):
        logger.debug("GROUP message skipped (length/command)")
        return

    now = time.time()
    uid = message.sender_chat.id if message.sender_chat else message.from_user.id
    cid = message.chat.id
    if now - _group_user_last.get(uid, 0) < GROUP_USER_COOLDOWN:
        return
    if now - _group_chat_last.get(cid, 0) < GROUP_CHAT_COOLDOWN:
        return

    total, found = await asyncio.to_thread(fuzzy_find_books, text, GROUP_MAX_RESULTS + 1, GROUP_MIN_SCORE)
    logger.info("GROUP search completed; results=%d", total)
    # Ничего не нашли или запрос слишком общий («анатомия») — молчим, не мешаем чату
    if not found or total > GROUP_MAX_RESULTS:
        return

    _group_user_last[uid] = now
    _group_chat_last[cid] = now
    for sc, lang, idx, bk in found:
        if await _send_book_to_group(message, sc, lang, idx, bk):
            try:
                nm = bk["file_name"].replace(".pdf", "").replace(".djvu", "").replace("_", " ")[:50]
                record_book_open(bk["url"], nm, sc, lang)
                if not message.sender_chat:
                    add_book_history(uid, sc, lang, idx, nm, bk["url"])
            except Exception:
                pass


@dp.message(lambda m: m.photo)
async def get_file_id(message: types.Message):
    if (not message.from_user or message.from_user.id != ADMIN_ID
            or message.chat.type != "private"):
        return
    file_id = message.photo[-1].file_id
    await message.answer(f"file_id:\n`{file_id}`", parse_mode="Markdown")

@dp.message()
async def search(message: types.Message):
    if not message.from_user or not message.text:
        return
    text = message.text.strip()
    if len(text) > 200:
        await message.answer("🔎 Слишком длинный запрос. Напишите название короче (до 200 символов).")
        return
    user_id = message.from_user.id

    # Игнорируем неизвестные команды (начинаются с /)
    if text.startswith("/"):
        return

    # Reply-кнопки предметов могут приходить на любом из трёх языков.
    normalized_button = _norm_q(text)
    for button_text, code in SUBJECTS.items():
        if _norm_q(button_text) == normalized_button:
            log_stat(message.from_user.id, code, text)
            await send_subject_menu(message.chat.id, code)
            return

    # =============================
    # АНТИСПАМ — автобан
    # =============================
    user_id = message.from_user.id
    now = datetime.now()
    if user_id not in spam_tracker:
        spam_tracker[user_id] = []
    spam_tracker[user_id] = [t for t in spam_tracker[user_id] if (now - t).total_seconds() < 10]
    spam_tracker[user_id].append(now)
    if len(spam_tracker[user_id]) >= 7:
        ban_user(user_id, "Автобан: спам")
        del spam_tracker[user_id]
        await message.answer(
            "🚫 Сіз спам үшін автоматты түрде бұғатталдыңыз!\n"
            "Вы автоматически заблокированы за спам!\n\n"
            "Егер қате болса / Если это ошибка:\n"
            "👉 @Tg_Adasan"
        )
        try:
            await bot.send_message(
                ADMIN_ID,
                f"⚠️ Автобан!\n\n"
                f"👤 {message.from_user.first_name}\n"
                f"🆔 ID: {user_id}\n"
                f"@{message.from_user.username or 'нет username'}\n\n"
                f"📝 Причина: спам (7+ сообщений за 10 сек)",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔓 Разбанить", callback_data=f"unban_{user_id}")]
                ])
            )
        except Exception:
            pass
        return
    # =============================

    # =============================
    # АВТОБАН ЗА МАТЫ
    # =============================
    mat = find_profanity(text) if user_id != ADMIN_ID else None
    if mat:
        ban_user(message.from_user.id, f"Автобан: мат ({mat})")
        spam_tracker.pop(message.from_user.id, None)
        await message.answer(
            "🚫 Сіз бұғатталдыңыз / Вы заблокированы за нецензурную лексику.\n\n"
            "Егер қате болса:\n"
            "Если это ошибка, обратитесь:\n\n"
            "👉 @Tg_Adasan"
        )
        try:
            await bot.send_message(
                ADMIN_ID,
                f"⚠️ Автобан за мат!\n\n"
                f"👤 {message.from_user.first_name}\n"
                f"🆔 ID: {message.from_user.id}\n"
                f"@{message.from_user.username or 'нет username'}\n\n"
                f"💬 Написал: {text[:100]}\n"
                f"📝 Мат: {mat}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔓 Разбанить", callback_data=f"unban_{message.from_user.id}")]
                ])
            )
        except Exception:
            pass
        return
    # =============================

    # 1. Ищем предмет
    subject_code = find_subject_fuzzy(text)
    if subject_code:
        log_stat(message.from_user.id, subject_code, text)
        await send_subject_menu(message.chat.id, subject_code)
        return

    # 3. Поиск в books_db.json: исходный запрос + языковые эквиваленты + fuzzy-поиск.
    total_found, found_books, is_fuzzy = await search_books_multilingual(text, 5)

    if found_books:
        results = found_books[:5]
        keyboard_rows = []
        for sc, lang, idx, bk in results:
            name = bk["file_name"].replace(".pdf","").replace(".djvu","").replace("_"," ")[:35]
            lang_flag = {"rus": "🇷🇺", "kaz": "🇰🇿", "eng": "🇬🇧"}.get(lang, "")
            keyboard_rows.append([InlineKeyboardButton(
                text=f"{lang_flag} {name}", callback_data=f"bk_{sc}_{lang}_{idx}"
            )])
        if is_fuzzy:
            head = tr(message.from_user.id, "fuzzy_head")
        else:
            head = tr(message.from_user.id, "found_n", n=total_found, k=len(results))
        await message.answer(
            f"{head}\n\n{tr(message.from_user.id, 'choose')}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
        )
        return

    # 4. Ничего не найдено
    await message.answer(
        tr(message.from_user.id, "not_found", admin=ADMIN_NAME),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=tr(message.from_user.id, "btn_admin"), url=ADMIN_URL)],
            [InlineKeyboardButton(text="🏠 Таңдаулар / Меню / Menu", callback_data="go_main_menu")],
        ])
    )

# =========================
# MAIN
# =========================
async def main():
    from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat

    # Обычные пользователи — без admin-команд
    await bot.set_my_commands([
        BotCommand(command="start",     description="Начало / Бастау / Start"),
        BotCommand(command="menu",      description="Меню / Мәзір / Menu"),
        BotCommand(command="favorites", description="⭐ Таңдаулылар"),
        BotCommand(command="chanel",    description="📌 Канал"),
        BotCommand(command="history",    description="📖 История книг"),
        BotCommand(command="popular",   description="🔥 Популярное"),
        BotCommand(command="catalog",   description="📋 Каталог / Все предметы"),
        BotCommand(command="upload",    description="📤 Материал жіберу"),
    ], scope=BotCommandScopeDefault())

    # Только админ видит эти команды
    await bot.set_my_commands([
        BotCommand(command="start",        description="Начало / Бастау / Start"),
        BotCommand(command="menu",         description="Меню / Мәзір / Menu"),
        BotCommand(command="favorites",    description="⭐ Таңдаулылар"),
        BotCommand(command="chanel",       description="📌 Канал"),
        BotCommand(command="popular",      description="🔥 Популярное"),
        BotCommand(command="catalog",      description="📋 Каталог / Все предметы"),
        BotCommand(command="upload",       description="📤 Материал жіберу"),
        BotCommand(command="stats",        description="📊 Статистика"),
        BotCommand(command="users",        description="👥 Список пользователей"),
        BotCommand(command="update_books", description="🔄 Кітаптарды жаңарту"),
        BotCommand(command="sort_other",   description="📦 Разобрать other"),
        BotCommand(command="broadcast",    description="📢 Рассылка"),
        BotCommand(command="ban",          description="🚫 Бан пользователя"),
        BotCommand(command="unban",        description="🔓 Разбан пользователя"),
        BotCommand(command="banlist",      description="📋 Список банов"),
    ], scope=BotCommandScopeChat(chat_id=ADMIN_ID))

    # Мини-веб-сервер: Render (Web Service) требует открытый порт
    from aiohttp import web
    async def _health(request):
        return web.Response(text="OK")
    _app = web.Application()
    _app.router.add_get("/", _health)
    _runner = web.AppRunner(_app)
    await _runner.setup()
    await web.TCPSite(_runner, "0.0.0.0", int(os.getenv("PORT", "10000"))).start()

    logger.info("✅ Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
