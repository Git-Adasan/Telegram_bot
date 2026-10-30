from aiogram import Bot, Dispatcher, types, BaseMiddleware, F
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
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
from typing import Callable, Awaitable, Any

logging.basicConfig(level=logging.INFO)
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
load_dotenv(ENV_PATH, override=True)
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
ADMIN_ID    = 6277436867
ADMIN_URL   = "https://t.me/Tg_Adasan"
ADMIN_NAME  = "@Tg_Adasan"
CHANNEL     = "@library_adasan"

# =========================
# БД
# =========================
DB_PATH = os.path.join(BASE_DIR, "adasan.db")

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
    # Закладки в книгах
    c.execute("""CREATE TABLE IF NOT EXISTS bookmarks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        book_name TEXT,
        book_url TEXT,
        page INTEGER,
        note TEXT,
        created_at TEXT
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

def add_bookmark(user_id, book_name, book_url, page, note=""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM bookmarks WHERE user_id=? AND book_url=?", (user_id, book_url))
    row = c.fetchone()
    if row:
        c.execute("UPDATE bookmarks SET page=?, note=?, created_at=? WHERE id=?",
                  (page, note, datetime.now().isoformat(), row[0]))
    else:
        c.execute("INSERT INTO bookmarks (user_id,book_name,book_url,page,note,created_at) VALUES (?,?,?,?,?,?)",
                  (user_id, book_name, book_url, page, note, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_bookmarks(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id,book_name,book_url,page,note,created_at FROM bookmarks WHERE user_id=? ORDER BY created_at DESC",
              (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def delete_bookmark(bookmark_id, user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM bookmarks WHERE id=? AND user_id=?", (bookmark_id, user_id))
    conn.commit()
    conn.close()

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

# Закладки — ожидание страницы от юзера
# {user_id: {"book_name": ..., "book_url": ...}}
_bookmark_state = {}

# =========================
# КЛАВИАТУРЫ
# =========================
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔬 Гистология"), KeyboardButton(text="🦴 Анатомия")],
        [KeyboardButton(text="🧪 Биохимия"), KeyboardButton(text="⚡ Физиология")],
        [KeyboardButton(text="🏥 Ішкі аурулар"), KeyboardButton(text="🔥 Патфиз")],
        [KeyboardButton(text="🔭 Патанат"), KeyboardButton(text="🗺 Топанат")],
        [KeyboardButton(text="💊 Фармакология"), KeyboardButton(text="🦠 Микробиология")],
        [KeyboardButton(text="🧬 Генетика"), KeyboardButton(text="⚗️ Биофизика")],
        [KeyboardButton(text="📜 Тарих"), KeyboardButton(text="✂️ Хирургия")],
        [KeyboardButton(text="⭐ Таңдаулылар"), KeyboardButton(text="📋 Барлық пәндер")],
        [KeyboardButton(text="📖 История"), KeyboardButton(text="📌 Закладки")],
        [KeyboardButton(text="🔥 Популярное"), KeyboardButton(text="📤 Материал жіберу")],
    ],
    resize_keyboard=True
)

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
    "gistologiya":    "gistologiya.jpg",
    "anatomiya":      "anatomiya.jpg",
    "biohimiya":      "biohimiya.jpg",
    "fiziologiya":    "fiziologiya.jpg",
    "ishki":          "ishki.jpg",
    "patfiz":         "patfiz.jpg",
    "patanat":        "patanat.jpg",
    "toanat":         "toanat.jpg",
    "farmakologiya":  "farmakologiya.jpg",
    "mikrobiologiya": "mikrobiologiya.jpg",
    "genetika":       "genetika.jpg",
    "biofizika":      "biofizika.jpg",
    "tarih":          "tarih.jpg",
    "hirurgiya":      "hirurgiya.jpg",
}

SUBJECT_KEYWORDS = {
    "gistologiya": ["гист","гиста","гисто","гистология","гистологию","hist","gist","gisto","гистол","цитология","эмбриология","цито","эмбрио"],
    "anatomiya":   ["анат","анато","анатомия","анатомию","anat","anatom","анатом"],
    "biohimiya":   ["биох","биохим","биохимия","биохимию","биохи","biohim","biochem","биоким","биокимия"],
    "fiziologiya": ["физ","физио","физиол","физиология","физиологию","fiziol","fizyo"],
    "ishki":       ["ішкі","ішкі аурулар","ішкі ауру","ішкі аур","внутренние","ішкіаурулар","ishki","терапия","терап"],
    "patfiz":      ["патфиз","пат физ","патофизиология","патофизиол","patfiz","патфизиол"],
    "patanat":     ["патанат","пат анат","патологическая анатомия","патанатомия","patanat","патанатом"],
    "toanat":      ["топанат","топ анат","топографическая анатомия","топографич","toanat"],
    "farmakologiya":  ["фармак","фарма","pharmac","farmak"],
    "mikrobiologiya": ["микроб","microb","микробио"],
    "genetika":    ["генет","genet","генетика"],
    "biofizika":   ["биофиз","biofiz","биофизика"],
    "tarih":       ["тарих","tarih","история казах","қазақстан тарих"],
    "hirurgiya":   ["хирург","hirurg","жалпы хир"],
}

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
            if kw and kw in q and len(kw) > best_score:
                best_code, best_score = code, len(kw)

    # 2. Составные названия — приоритетнее обычных ключевых слов
    for code, combos in SUBJECT_COMBOS.items():
        for stems in combos:
            if all(re.search(r"(?<!\w)" + re.escape(st), q) for st in stems):
                score = 100 + sum(len(st) for st in stems)
                if score > best_score:
                    best_code, best_score = code, score

    return best_code


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




async def send_subject_menu(chat_id, code):
    name = SUBJECT_NAMES.get(code, "📚 Предмет")
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
    await bot.send_message(chat_id=callback.message.chat.id, text="👇", reply_markup=main_menu)
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
    name = SUBJECT_NAMES.get(code, "📚 Предмет")
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
            reply_markup=lang_inline(code)
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
    name = SUBJECT_NAMES.get(code, "📚 Предмет")
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
        name = SUBJECT_NAMES.get(code, "📚 Предмет")
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
        name = SUBJECT_NAMES.get(code, "📚 Предмет")
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
def lang_inline(subject_code):
    buttons = []
    langs = BOOKS_DB.get(subject_code, {})
    if langs.get("rus"):
        buttons.append(InlineKeyboardButton(
            text=f"🇷🇺 Русский ({len(langs['rus'])})", callback_data=f"bl_{subject_code}_rus"))
    if langs.get("kaz"):
        buttons.append(InlineKeyboardButton(
            text=f"🇰🇿 Қазақша ({len(langs['kaz'])})", callback_data=f"bl_{subject_code}_kaz"))
    if langs.get("eng"):
        buttons.append(InlineKeyboardButton(
            text=f"🇬🇧 English ({len(langs['eng'])})", callback_data=f"bl_{subject_code}_eng"))
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
    name = SUBJECT_NAMES.get(subject_code, "📚 Предмет")
    lang_name = {"rus": "🇷🇺 Русский", "kaz": "🇰🇿 Қазақша", "eng": "🇬🇧 English"}.get(lang, lang)
    try:
        await callback.message.edit_caption(
            caption=f"{name} — Кітаптар\n{lang_name}\n\n👇 Таңдаңыз ({len(books)} кітап):",
            reply_markup=booklist_inline(subject_code, lang, 0)
        )
    except:
        await callback.message.edit_text(
            text=f"{name} — Кітаптар\n{lang_name}\n\n👇 Таңдаңыз ({len(books)} кітап):",
            reply_markup=booklist_inline(subject_code, lang, 0)
        )
    await callback.answer()

@dp.callback_query(lambda c: c.data and c.data.startswith("bp_"))
async def bookpage_handler(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    subject_code = parts[1]
    lang = parts[2]
    page = int(parts[3])
    name = SUBJECT_NAMES.get(subject_code, "📚 Предмет")
    lang_name = {"rus": "🇷🇺 Русский", "kaz": "🇰🇿 Қазақша", "eng": "🇬🇧 English"}.get(lang, lang)
    books = BOOKS_DB.get(subject_code, {}).get(lang, [])
    try:
        await callback.message.edit_caption(
            caption=f"{name} — Кітаптар\n{lang_name}\n\n👇 Таңдаңыз ({len(books)} кітап):",
            reply_markup=booklist_inline(subject_code, lang, page)
        )
    except:
        await callback.message.edit_text(
            text=f"{name} — Кітаптар\n{lang_name}\n\n👇 Таңдаңыз ({len(books)} кітап):",
            reply_markup=booklist_inline(subject_code, lang, page)
        )
    await callback.answer()

def book_card_keyboard(subject_code, lang, idx, url):
    likes, dislikes = get_votes(url)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Жүктеу / Скачать / Download", url=url)],
        [InlineKeyboardButton(text="⭐ Таңдаулыға қосу", callback_data=f"fav_add_{subject_code}_{lang}_{idx}")],
        [InlineKeyboardButton(text="📌 Закладка қосу / Добавить закладку", callback_data=f"bmark_start_{subject_code}_{lang}_{idx}")],
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
        await callback.answer("❌ Кітап табылмады!", show_alert=True)
        return
    book = books_list[idx]
    name = book["file_name"].replace(".pdf","").replace(".djvu","").replace("_"," ")
    lang_name = {"rus": "🇷🇺 Русский", "kaz": "🇰🇿 Қазақша", "eng": "🇬🇧 English"}.get(lang, lang)
    subject_name = SUBJECT_NAMES.get(subject_code, "📚 Предмет")
    caption = (
        f"╔══════════════════════╗\n"
        f"  📖 {name[:40]}\n"
        f"╚══════════════════════╝\n\n"
        f"📚 Пән: {subject_name}\n"
        f"🌐 Тіл: {lang_name}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 @library_adasan"
    )
    keyboard = book_card_keyboard(subject_code, lang, idx, book["url"])
    sent = False
    cover_id = book.get("photo_message_id")
    if cover_id:
        # Обложка берётся из канала (ничего не хранится в архиве бота)
        try:
            await bot.copy_message(
                chat_id=callback.message.chat.id,
                from_chat_id=f"@{CHANNEL.lstrip('@')}",
                message_id=int(cover_id),
                caption=caption,
                reply_markup=keyboard,
            )
            sent = True
        except Exception as e:
            logger.warning(f"Обложка не скопировалась (пост {cover_id}): {e}")
    if not sent:
        # Нет обложки (методичка, конспект, силабус) — фото предмета из папки бота
        photo_path = os.path.join(BASE_DIR, SUBJECT_PHOTOS.get(subject_code, "adasan.jpg"))
        await bot.send_photo(chat_id=callback.message.chat.id,
                             photo=FSInputFile(photo_path), caption=caption, reply_markup=keyboard)
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
        await callback.answer("❌ Кітап табылмады!", show_alert=True)
        return
    book = db_books[idx]
    book_name = book["file_name"].replace(".pdf","").replace(".djvu","").replace("_"," ")[:50]
    book_url = book["url"]
    added = add_favorite(callback.from_user.id, subject_code, lang, idx, book_name, book_url)
    if added:
        await callback.answer("⭐ Таңдаулыларға қосылды!", show_alert=True)
    else:
        await callback.answer("✅ Бұл кітап бұрын қосылған!", show_alert=True)

# =========================
# CALLBACK — Закладка (начало)
# =========================
@dp.callback_query(lambda c: c.data and c.data.startswith("bmark_start_"))
async def bmark_start_handler(callback: types.CallbackQuery):
    parts = callback.data.replace("bmark_start_", "").split("_")
    subject_code = parts[0]
    lang = parts[1]
    idx = int(parts[2])
    book = BOOKS_DB.get(subject_code, {}).get(lang, [])[idx]
    book_name = book["file_name"].replace(".pdf","").replace(".djvu","").replace("_"," ")[:50]
    book_url = book["url"]
    # Сохраняем состояние
    _bookmark_state[callback.from_user.id] = {
        "book_name": book_name,
        "book_url": book_url,
    }
    await callback.answer()
    await bot.send_message(
        chat_id=callback.message.chat.id,
        text=f"📌 <b>{book_name}</b>\n\n"
             f"Бет нөмірін жазыңыз / Напишите номер страницы:\n\n"
             f"Мысалы: <code>145</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Бас тарту / Отмена", callback_data="bmark_cancel")]
        ])
    )

@dp.callback_query(lambda c: c.data == "bmark_cancel")
async def bmark_cancel_handler(callback: types.CallbackQuery):
    _bookmark_state.pop(callback.from_user.id, None)
    await callback.message.delete()
    await callback.answer("❌ Отменено")


async def fav_del_handler(callback: types.CallbackQuery):
    url = callback.data.replace("fav_del_", "")
    remove_favorite(callback.from_user.id, url)
    await callback.answer("🗑 Өшірілді!", show_alert=True)
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
# CALLBACK — Показать закладки
# =========================
@dp.callback_query(lambda c: c.data == "show_bookmarks")
async def show_bookmarks_callback(callback: types.CallbackQuery):
    bmarks = get_bookmarks(callback.from_user.id)
    if not bmarks:
        await callback.answer("📌 Закладок нет", show_alert=True)
        return
    text = "📌 Сіздің бетбелгілеріңіз / Ваши закладки:\n\n"
    rows = []
    for bm_id, bn, bu, page, note, created_at in bmarks:
        date_str = created_at[:10] if created_at else ""
        text += f"📖 {bn[:30]} — бет/стр. <b>{page}</b> ({date_str})\n"
        rows.append([
            InlineKeyboardButton(text=f"📖 {bn[:25]} стр.{page}", url=bu),
            InlineKeyboardButton(text="🗑", callback_data=f"bmdel_{bm_id}"),
        ])
    rows.append([InlineKeyboardButton(text="🏠 Меню", callback_data="go_main_menu")])
    await callback.message.answer(text, parse_mode="HTML",
                                  reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()

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

@dp.message(lambda m: m.text and m.text.lower() == "📌 закладки")
async def bookmarks_button(message: types.Message):
    bmarks = get_bookmarks(message.from_user.id)
    if not bmarks:
        await message.answer(
            "📌 Закладок нет\n\nСохранить закладку:\n/bookmark 145 Синельников том 1",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Меню", callback_data="go_main_menu")]
            ])
        )
        return
    rows = []
    text = f"📌 Сіздің бетбелгілеріңіз / Ваши закладки ({len(bmarks)}):\n\n"
    for bm_id, bname, burl, page, note, created_at in bmarks:
        date_str = created_at[:10] if created_at else ""
        text += f"📖 {bname[:30]}\n📄 Бет: {page} | 📅 {date_str}\n\n"
        rows.append([
            InlineKeyboardButton(text=f"📖 {bname[:25]} — б.{page}", url=burl) if burl else
            InlineKeyboardButton(text=f"📖 {bname[:25]} — б.{page}", callback_data="noop"),
            InlineKeyboardButton(text="🗑", callback_data=f"bmdel_{bm_id}"),
        ])
    rows.append([InlineKeyboardButton(text="🏠 Меню", callback_data="go_main_menu")])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

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
    await message.answer(f"⭐ Сіздің таңдаулыларыңыз ({len(favs)}):",
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

@dp.message(lambda m: m.text and m.text.lower() == "📋 барлық пәндер")
async def all_subjects_button(message: types.Message):
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

# =========================
# КОМАНДА — закладки
# =========================
@dp.message(Command("bookmark"))
async def bookmark_command(message: types.Message):
    """Использование: /bookmark <страница> [название книги]
    Пример: /bookmark 145 Синельников том 1"""
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer(
            "📌 Закладка / Бетбелгі\n\n"
            "Использование:\n/bookmark <страница> [название книги]\n\n"
            "Пример:\n/bookmark 145 Синельников том 1\n\n"
            "Посмотреть закладки: /bookmarks"
        )
        return
    try:
        page = int(parts[1])
    except ValueError:
        await message.answer("❌ Страница должна быть числом!\nПример: /bookmark 145")
        return
    book_note = parts[2] if len(parts) > 2 else "Кітап / Книга"
    add_bookmark(message.from_user.id, book_note, "", page, "")
    await message.answer(
        f"📌 Закладка сохранена!\n\n"
        f"📖 Кітап: {book_note}\n"
        f"📄 Бет / Страница: {page}"
    )

@dp.message(Command("bookmarks"))
async def bookmarks_command(message: types.Message):
    bmarks = get_bookmarks(message.from_user.id)
    if not bmarks:
        await message.answer(
            "📌 Закладок нет\n\n"
            "Сохранить закладку:\n/bookmark 145 Синельников том 1",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Меню", callback_data="go_main_menu")]
            ])
        )
        return
    rows = []
    text = f"📌 Сіздің бетбелгілеріңіз / Ваши закладки ({len(bmarks)}):\n\n"
    for bm_id, bname, burl, page, note, created_at in bmarks:
        date_str = created_at[:10] if created_at else ""
        text += f"📖 {bname[:30]}\n📄 Бет: {page} | 📅 {date_str}\n\n"
        rows.append([
            InlineKeyboardButton(text=f"📖 {bname[:25]} — б.{page}", url=burl) if burl else
            InlineKeyboardButton(text=f"📖 {bname[:25]} — б.{page}", callback_data="noop"),
            InlineKeyboardButton(text="🗑", callback_data=f"bmdel_{bm_id}"),
        ])
    rows.append([InlineKeyboardButton(text="🏠 Меню", callback_data="go_main_menu")])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

@dp.callback_query(lambda c: c.data and c.data.startswith("bmdel_"))
async def bookmark_delete_callback(callback: types.CallbackQuery):
    bm_id = int(callback.data.replace("bmdel_", ""))
    delete_bookmark(bm_id, callback.from_user.id)
    await callback.answer("🗑 Өшірілді!", show_alert=True)
    # Обновляем список
    bmarks = get_bookmarks(callback.from_user.id)
    if not bmarks:
        try:
            await callback.message.edit_text(
                "📌 Закладок нет\n\nСохранить: /bookmark 145 Синельников том 1",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 Меню", callback_data="go_main_menu")]
                ])
            )
        except Exception:
            pass
        return
    rows = []
    text = f"📌 Закладки ({len(bmarks)}):\n\n"
    for bm_id2, bname, burl, page, note, created_at in bmarks:
        date_str = created_at[:10] if created_at else ""
        text += f"📖 {bname[:30]}\n📄 Бет: {page} | 📅 {date_str}\n\n"
        rows.append([
            InlineKeyboardButton(text=f"📖 {bname[:25]} — б.{page}", url=burl) if burl else
            InlineKeyboardButton(text=f"📖 {bname[:25]} — б.{page}", callback_data="noop"),
            InlineKeyboardButton(text="🗑", callback_data=f"bmdel_{bm_id2}"),
        ])
    rows.append([InlineKeyboardButton(text="🏠 Меню", callback_data="go_main_menu")])
    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
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
        from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto
        import json as _json2

        HASHTAG_MAP = {
            "#гистология": "gistologiya", "#анатомия": "anatomiya",
            "#биохимия": "biohimiya", "#физиология": "fiziologiya",
            "#ішкіаурулар": "ishki", "#ішкі": "ishki",
            "#патфиз": "patfiz", "#патанат": "patanat",
            "#топанат": "toanat", "#фармакология": "farmakologiya",
            "#микробиология": "mikrobiologiya", "#хирургия": "hirurgiya",
            "#генетика": "genetika", "#биофизика": "biofizika",
            "#тарих": "tarih",
        }
        SUBJECT_KW = {
            "anatomiya":      ["анатом","anatom","нетт","netter","синельник","сапин","билич","гайворон"],
            "gistologiya":    ["гистол","histol","цитол","эмбриол","ажаев","афанас","аяпов","тұңғыш"],
            "biohimiya":      ["биохим","biochem","северин","harper"],
            "fiziologiya":    ["физиол","physiol","гайтон","судаков"],
            "ishki":          ["ішкі","ishki","внутренн","терапи","пропедевт","неотложн"],
            "patfiz":         ["патофиз","patofiz","патфиз"],
            "patanat":        ["патанат","патологич","роббинс","струков"],
            "toanat":         ["топограф","топка","оперативн"],
            "farmakologiya":  ["фармакол","pharmacol","катцунг","харкевич"],
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
            # хэштеги: самый длинный — самый точный (#патанат раньше #анат)
            tag_hits = [(len(tag), code) for tag, code in HASHTAG_MAP.items() if tag in tl]
            if tag_hits:
                return max(tag_hits)[1]
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
            return best or "other"

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
                timeline = []       # (id, это_фото, дата) — все посты канала
                book_entries = []   # (запись_книги, id_поста, дата) — чтобы потом найти обложки
                session_path = os.path.join(BASE_DIR, "update_session")
                async with TelegramClient(
                    session_path,
                    API_ID,
                    API_HASH,
                    lang_code="ru",
                    system_lang_code="ru-RU",
                ) as client:
                    async for msg in client.iter_messages(CHANNEL, limit=5000):
                        timeline.append((msg.id, isinstance(msg.media, MessageMediaPhoto), msg.date))
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
                        if subj not in new_db:
                            new_db[subj] = {"rus": [], "kaz": [], "eng": []}
                        entry = {
                            "message_id": msg.id,
                            "file_name":  fname,
                            "caption":    caption[:300],
                            "url":        f"https://t.me/library_adasan/{msg.id}",
                        }
                        new_db[subj][lang].append(entry)
                        book_entries.append((entry, msg.id, msg.date))
                        total += 1

                # Обложка = фото-пост, который стоит ПРЯМО перед файлом (не позже 10 минут).
                # У методичек, конспектов и силабусов фото нет — поле photo_message_id не создаётся.
                timeline.sort(key=lambda t: t[0])
                prev_of = {timeline[i][0]: timeline[i - 1] for i in range(1, len(timeline))}
                covers = 0
                for entry, mid, mdate in book_entries:
                    p = prev_of.get(mid)
                    if p and p[1] and abs((mdate - p[2]).total_seconds()) <= 600:
                        entry["photo_message_id"] = p[0]
                        covers += 1
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
        apply_sort_overrides(new_db)   # ручная сортировка из /sort_other не сбрасывается

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
MAX_PENDING_PER_USER = 5
_upload_state = set()  # user_id, которые нажали «Материал жіберу»

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
        await callback.answer("❌ Кітап табылмады!", show_alert=True)
        return
    vote = 1 if direction == "up" else -1
    result = set_vote(callback.from_user.id, book["url"], vote)
    try:
        await callback.message.edit_reply_markup(
            reply_markup=book_card_keyboard(subject_code, lang, idx, book["url"])
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

@dp.message(lambda m: m.document is not None and m.from_user.id in _upload_state)
async def receive_material(message: types.Message):
    uid = message.from_user.id
    doc = message.document
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
        logger.info(f"GROUP пропуск (длина/команда): {text[:30]!r}")
        return

    now = time.time()
    uid = message.sender_chat.id if message.sender_chat else message.from_user.id
    cid = message.chat.id
    if now - _group_user_last.get(uid, 0) < GROUP_USER_COOLDOWN:
        return
    if now - _group_chat_last.get(cid, 0) < GROUP_CHAT_COOLDOWN:
        return

    total, found = await asyncio.to_thread(fuzzy_find_books, text, GROUP_MAX_RESULTS + 1, GROUP_MIN_SCORE)
    logger.info(f"GROUP запрос {text[:40]!r}: найдено {total}")
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
    file_id = message.photo[-1].file_id
    await message.answer(f"file_id:\n`{file_id}`", parse_mode="Markdown")

@dp.message()
async def search(message: types.Message):
    text = message.text or ""
    user_id = message.from_user.id

    # =============================
    # ЗАКЛАДКА — ожидание страницы
    # =============================
    if user_id in _bookmark_state:
        page_text = text.strip()
        if page_text.isdigit():
            state = _bookmark_state.pop(user_id)
            add_bookmark(user_id, state["book_name"], state["book_url"], int(page_text))
            await message.answer(
                f"📌 Закладка сақталды / Закладка сохранена!\n\n"
                f"📖 {state['book_name']}\n"
                f"📄 Бет / Страница: <b>{page_text}</b>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📌 Барлық закладкалар", callback_data="show_bookmarks")],
                    [InlineKeyboardButton(text="🏠 Меню", callback_data="go_main_menu")],
                ])
            )
        else:
            await message.answer("⚠️ Тек сан жазыңыз / Напишите только число!\nМысалы: <code>145</code>", parse_mode="HTML")
        return

    # Игнорируем неизвестные команды (начинаются с /)
    if text.startswith("/"):
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
    text_lower = text.lower()
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
    subject_code = find_subject(text)
    if subject_code:
        log_stat(message.from_user.id, subject_code, text)
        await send_subject_menu(message.chat.id, subject_code)
        return

    # 3. Поиск в books_db.json
    query = text.lower().strip()
    found_books = []
    for sc, langs in BOOKS_DB.items():
        for lang, books in langs.items():
            for idx, bk in enumerate(books):
                fname = bk["file_name"].lower()
                cap = bk.get("caption", "").lower()
                if query in fname or query in cap:
                    found_books.append((sc, lang, idx, bk))

    # 3.1 Точного совпадения нет -> умный поиск (опечатки + латиница)
    is_fuzzy = False
    total_found = len(found_books)
    if not found_books:
        total_found, found_books = await asyncio.to_thread(fuzzy_find_books, text, 5)
        is_fuzzy = bool(found_books)

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
            head = "🔍 Дәл сәйкестік жоқ, мүмкін, мынаны іздедіңіз бе?\nТочного совпадения нет, возможно, вы искали:"
        else:
            head = f"🔍 Табылды: {total_found} кітап (көрсетілген: {len(results)})"
        await message.answer(
            f"{head}\n\n👇 Таңдаңыз:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
        )
        return

    # 4. Ничего не найдено
    await message.answer(
        "❌ Кітап табылмады / Книга не найдена / Book not found\n\n"
        "📚 Осы кітапты табу үшін / Чтобы найти эту книгу:\n\n"
        f"👉 Администраторға жазыңыз: {ADMIN_NAME}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📌 Немесе предметті жазыңыз:\n"
        "• Гиста / Анат / Биохим\n"
        "• Физиол / Патфиз / Патанат\n"
        "• Синельников / Netter / Афанасьев...",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✉️ Администраторға жазу", url=ADMIN_URL)],
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
        BotCommand(command="bookmarks", description="📌 Закладки"),
        BotCommand(command="bookmark",  description="📌 Сохранить закладку"),
        BotCommand(command="popular",   description="🔥 Популярное"),
        BotCommand(command="upload",    description="📤 Материал жіберу"),
    ], scope=BotCommandScopeDefault())

    # Только админ видит эти команды
    await bot.set_my_commands([
        BotCommand(command="start",        description="Начало / Бастау / Start"),
        BotCommand(command="menu",         description="Меню / Мәзір / Menu"),
        BotCommand(command="favorites",    description="⭐ Таңдаулылар"),
        BotCommand(command="chanel",       description="📌 Канал"),
        BotCommand(command="popular",      description="🔥 Популярное"),
        BotCommand(command="upload",       description="📤 Материал жіберу"),
        BotCommand(command="stats",        description="📊 Статистика"),
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
