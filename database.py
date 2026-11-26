"""База данных SQLite: пользователи, избранное, статистика, баны, помощники админа,
кэши языка / бана / подписки на канал."""

import os
import re
import sqlite3
import time
from datetime import datetime, timedelta

from core import ADMIN_ID, DB_PATH, logger


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
    c.execute("""CREATE TABLE IF NOT EXISTS admins (
        user_id INTEGER PRIMARY KEY,
        added_at TEXT,
        added_by INTEGER
    )""")
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
    # Подписчики канала: заполняется событиями chat_member (вступил / вышел)
    c.execute("""CREATE TABLE IF NOT EXISTS channel_subs (
        user_id INTEGER PRIMARY KEY,
        is_member INTEGER NOT NULL,
        updated_at INTEGER NOT NULL
    )""")
    c.execute(_BLOCKED_DDL)
    c.execute(_ARCHIVE_DDL)
    c.execute(_MISS_DDL)
    c.execute(_WISH_DDL)
    _ensure_indexes(c)
    conn.commit()
    conn.close()

# Индексы: без них каждый поиск по user_id / дате читает всю таблицу целиком.
# Создаются при запуске и после /restore (init_db вызывается и там).
_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_stats_user ON stats(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_stats_created ON stats(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_fav_user_url ON favorites(user_id, book_url)",
    "CREATE INDEX IF NOT EXISTS idx_hist_user_url ON book_history(user_id, book_url)",
    "CREATE INDEX IF NOT EXISTS idx_ratings_url ON book_ratings(book_url)",
    "CREATE INDEX IF NOT EXISTS idx_archive_user ON stats_archive(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_wishes_miss ON book_wishes(miss_id)",
]

def _ensure_indexes(c):
    for sql in _INDEXES:
        try:
            c.execute(sql)
        except sqlite3.OperationalError as e:          # таблицы/колонки может не быть в очень старой базе
            logger.warning(f"Индекс не создан ({sql.split(' ON ')[0]}): {e}")

# Кто заблокировал бота: таким рассылка больше не отправляется (вернётся после /start).
_BLOCKED_DDL = """CREATE TABLE IF NOT EXISTS bot_blocked (
    user_id INTEGER PRIMARY KEY,
    blocked_at TEXT
)"""

def mark_bot_blocked(user_id):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(_BLOCKED_DDL)
        conn.execute("INSERT OR REPLACE INTO bot_blocked (user_id, blocked_at) VALUES (?, ?)",
                     (user_id, datetime.now().isoformat()))
        conn.commit()
    finally:
        conn.close()

def clear_bot_blocked(user_id):
    """Человек разблокировал бота — снова включаем в рассылку."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(_BLOCKED_DDL)
        conn.execute("DELETE FROM bot_blocked WHERE user_id=?", (user_id,))
        conn.commit()
    finally:
        conn.close()

def count_bot_blocked():
    """Сколько из пользователей заблокировали бота."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(_BLOCKED_DDL)
        return conn.execute(
            "SELECT COUNT(*) FROM users WHERE user_id IN (SELECT user_id FROM bot_blocked)").fetchone()[0]
    finally:
        conn.close()

# Архив статистики: старые поиски (по одной строке на каждый запрос, с текстом запроса)
# сворачиваются в «месяц × пользователь × предмет → сколько раз». Все счётчики остаются прежними
# (всего поисков, топ предметов, по месяцам, у каждого пользователя), а таблица stats перестаёт расти вечно.
_ARCHIVE_DDL = """CREATE TABLE IF NOT EXISTS stats_archive (
    month TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    subject TEXT NOT NULL,
    n INTEGER NOT NULL,
    PRIMARY KEY (month, user_id, subject)
)"""

STATS_KEEP_MONTHS = 2     # текущий месяц + столько полных предыдущих остаются «как есть» (нужны графику за 7 дней)

def _stats_cutoff(keep_months=STATS_KEEP_MONTHS, today=None):
    """Первое число месяца, раньше которого строки уходят в архив: ровно по границе месяца,
    чтобы месяц никогда не лежал одновременно и в stats, и в архиве."""
    today = today or datetime.now()
    idx = today.year * 12 + (today.month - 1) - keep_months
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}-01"

def compact_stats(keep_months=STATS_KEEP_MONTHS, today=None):
    """Свернуть старые строки stats в stats_archive. Возвращает, сколько строк свёрнуто.
    Всё в одной транзакции: либо строки перенесены и удалены, либо ничего не изменилось."""
    cutoff = _stats_cutoff(keep_months, today)
    conn = sqlite3.connect(DB_PATH, isolation_level=None)      # транзакцией управляем сами
    try:
        conn.execute(_ARCHIVE_DDL)
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                """INSERT INTO stats_archive (month, user_id, subject, n)
                   SELECT SUBSTR(created_at,1,7), COALESCE(user_id,0), COALESCE(subject,''), COUNT(*)
                   FROM stats WHERE created_at < ?
                   GROUP BY 1,2,3
                   ON CONFLICT(month, user_id, subject) DO UPDATE SET n = n + excluded.n""",
                (cutoff,))
            moved = conn.execute("DELETE FROM stats WHERE created_at < ?", (cutoff,)).rowcount
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        return moved
    finally:
        conn.close()

def vacuum_db():
    """Вернуть место на диске после удаления строк (блокирует базу на время работы)."""
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    try:
        conn.execute("VACUUM")
    finally:
        conn.close()

# Запросы, по которым книга не нашлась: видно, чего не хватает в библиотеке.
# book_wishes: кто это искал (wished=0) и кто нажал «сообщить, когда появится» (wished=1).
_MISS_DDL = """CREATE TABLE IF NOT EXISTS missed_queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    qnorm TEXT NOT NULL UNIQUE,
    sample TEXT NOT NULL,
    n INTEGER NOT NULL DEFAULT 1,
    first_at TEXT,
    last_at TEXT,
    resolved_at TEXT
)"""

_WISH_DDL = """CREATE TABLE IF NOT EXISTS book_wishes (
    user_id INTEGER NOT NULL,
    miss_id INTEGER NOT NULL,
    wished INTEGER NOT NULL DEFAULT 0,
    created_at TEXT,
    PRIMARY KEY (user_id, miss_id)
)"""

MAX_WISHES_PER_USER = 20      # столько ожидаемых книг на человека: защита от лавины уведомлений

def miss_key(text):
    """Нормализация запроса: «Книга  Х!» и «книга х» — один и тот же запрос."""
    t = re.sub(r"[^\w\s]", " ", (text or "").lower().replace("ё", "е"))
    return re.sub(r"\s+", " ", t).strip()[:100]

def record_miss(user_id, query):
    """Запомнить ненайденный запрос. Возвращает id запроса или None, если запрос слишком короткий."""
    key = miss_key(query)
    if len(key) < 3:
        return None
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(_MISS_DDL)
        conn.execute(_WISH_DDL)
        conn.execute(
            """INSERT INTO missed_queries (qnorm, sample, n, first_at, last_at) VALUES (?,?,1,?,?)
               ON CONFLICT(qnorm) DO UPDATE SET n = n + 1, last_at = excluded.last_at, resolved_at = NULL""",
            (key, (query or "").strip()[:100], now, now))
        miss_id = conn.execute("SELECT id FROM missed_queries WHERE qnorm=?", (key,)).fetchone()[0]
        conn.execute("INSERT OR IGNORE INTO book_wishes (user_id, miss_id, wished, created_at) VALUES (?,?,0,?)",
                     (user_id, miss_id, now))
        conn.commit()
        return miss_id
    finally:
        conn.close()

def set_wish(user_id, miss_id):
    """Человек просит сообщить, когда книга появится. Возвращает "ok", "gone" (запрос уже закрыт/не существует)
    или "limit" (слишком много ожидаемых книг)."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(_MISS_DDL)
        conn.execute(_WISH_DDL)
        row = conn.execute("SELECT resolved_at FROM missed_queries WHERE id=?", (miss_id,)).fetchone()
        if row is None or row[0] is not None:
            return "gone"
        already = conn.execute("SELECT wished FROM book_wishes WHERE user_id=? AND miss_id=?",
                               (user_id, miss_id)).fetchone()
        if not (already and already[0]):
            n = conn.execute("""SELECT COUNT(*) FROM book_wishes w JOIN missed_queries m ON m.id = w.miss_id
                                WHERE w.user_id=? AND w.wished=1 AND m.resolved_at IS NULL""", (user_id,)).fetchone()[0]
            if n >= MAX_WISHES_PER_USER:
                return "limit"
        conn.execute(
            """INSERT INTO book_wishes (user_id, miss_id, wished, created_at) VALUES (?,?,1,?)
               ON CONFLICT(user_id, miss_id) DO UPDATE SET wished=1""",
            (user_id, miss_id, datetime.now().isoformat()))
        conn.commit()
        return "ok"
    finally:
        conn.close()

def top_misses(limit=20):
    """Чего чаще всего ищут и не находят: (id, запрос, раз, человек, ждут_уведомления)."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(_MISS_DDL)
        conn.execute(_WISH_DDL)
        return conn.execute(
            """SELECT m.id, m.sample, m.n,
                      (SELECT COUNT(*) FROM book_wishes w WHERE w.miss_id = m.id),
                      (SELECT COALESCE(SUM(w.wished),0) FROM book_wishes w WHERE w.miss_id = m.id)
               FROM missed_queries m WHERE m.resolved_at IS NULL
               ORDER BY 4 DESC, m.n DESC, m.last_at DESC LIMIT ?""", (limit,)).fetchall()
    finally:
        conn.close()

def pending_wishes():
    """[(id запроса, текст запроса, [user_id, ...])] — только те, кого просили уведомить."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(_MISS_DDL)
        conn.execute(_WISH_DDL)
        out = {}
        for mid, sample, uid in conn.execute(
                """SELECT m.id, m.sample, w.user_id FROM missed_queries m
                   JOIN book_wishes w ON w.miss_id = m.id
                   WHERE m.resolved_at IS NULL AND w.wished = 1 ORDER BY m.id"""):
            out.setdefault((mid, sample), []).append(uid)
        return [(mid, sample, uids) for (mid, sample), uids in out.items()]
    finally:
        conn.close()

def resolve_miss(miss_id):
    """Книга появилась и все ожидающие уведомлены: закрываем запрос."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("UPDATE missed_queries SET resolved_at=? WHERE id=?", (datetime.now().isoformat(), miss_id))
        conn.execute("DELETE FROM book_wishes WHERE miss_id=?", (miss_id,))
        conn.commit()
    finally:
        conn.close()

def prune_misses(resolved_days=30, stale_days=90):
    """Раз в сутки: убираем закрытые запросы и одиночные запросы без желающих, которым больше stale_days."""
    now = datetime.now()
    r_cut = (now - timedelta(days=resolved_days)).isoformat()
    s_cut = (now - timedelta(days=stale_days)).isoformat()
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(_MISS_DDL)
        conn.execute(_WISH_DDL)
        a = conn.execute("DELETE FROM missed_queries WHERE resolved_at IS NOT NULL AND resolved_at < ?", (r_cut,)).rowcount
        b = conn.execute(
            """DELETE FROM missed_queries WHERE resolved_at IS NULL AND n <= 1 AND last_at < ?
               AND id NOT IN (SELECT miss_id FROM book_wishes WHERE wished = 1)""", (s_cut,)).rowcount
        conn.execute("DELETE FROM book_wishes WHERE miss_id NOT IN (SELECT id FROM missed_queries)")
        conn.commit()
        return a + b
    finally:
        conn.close()

def get_broadcast_user_ids():
    """(кому слать, сколько пропущено как заблокировавших бота)."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(_BLOCKED_DDL)
        rows = [r[0] for r in conn.execute(
            "SELECT user_id FROM users WHERE user_id NOT IN (SELECT user_id FROM bot_blocked)")]
        total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    finally:
        conn.close()
    return rows, total - len(rows)

def add_user(user_id, username, first_name):
    """Добавляет пользователя. Возвращает True, если это НОВЫЙ пользователь (его ещё не было в базе).
    Для старых обновляет username / имя — раньше они навсегда оставались такими, как при первом /start."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO users (user_id, username, first_name, lang, joined_at) VALUES (?,?,?,?,?)",
        (user_id, username, first_name, "ru", datetime.now().isoformat())
    )
    is_new = c.rowcount > 0
    if not is_new:
        c.execute("UPDATE users SET username=?, first_name=? WHERE user_id=?", (username, first_name, user_id))
    c.execute(_BLOCKED_DDL)
    c.execute("DELETE FROM bot_blocked WHERE user_id=?", (user_id,))   # написал /start — значит снова доступен
    conn.commit()
    conn.close()
    return is_new


def clear_book_history(user_id):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("DELETE FROM book_history WHERE user_id=?", (user_id,))
        conn.commit()
    finally:
        conn.close()


def get_user_profile(user_id):
    """Личная статистика для /profile."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(_ARCHIVE_DDL)
        conn.execute(_MISS_DDL)
        conn.execute(_WISH_DDL)
        one = lambda sql: conn.execute(sql, (user_id,)).fetchone()[0] or 0          # noqa: E731
        row = conn.execute("SELECT joined_at FROM users WHERE user_id=?", (user_id,)).fetchone()
        return {
            "joined_at": row[0] if row else None,
            "opened": one("SELECT COUNT(*) FROM book_history WHERE user_id=?"),
            "favs": one("SELECT COUNT(*) FROM favorites WHERE user_id=?"),
            "votes": one("SELECT COUNT(*) FROM book_ratings WHERE user_id=?"),
            "searches": one("SELECT COUNT(*) FROM stats WHERE user_id=?")
                        + one("SELECT COALESCE(SUM(n),0) FROM stats_archive WHERE user_id=?"),
            "wishes": one("""SELECT COUNT(*) FROM book_wishes w JOIN missed_queries m ON m.id = w.miss_id
                             WHERE w.user_id=? AND w.wished=1 AND m.resolved_at IS NULL"""),
        }
    finally:
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

def _mid_from_url(url):
    """message_id поста из ссылки https://t.me/library_adasan/123 (стабилен, в отличие от индекса)."""
    m = re.search(r"/(\d+)$", url or "")
    return m.group(1) if m else "0"

def get_favorites(user_id):
    """Возвращает только личные избранные книги конкретного пользователя."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT id,subject_code,lang,book_idx,book_name,book_url "
        "FROM favorites WHERE user_id=? ORDER BY added_at DESC LIMIT 30",
        (user_id,)
    )
    rows = c.fetchall()
    conn.close()
    return rows

def remove_favorite_by_id(user_id, favorite_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM favorites WHERE user_id=? AND id=?", (user_id, favorite_id))
    conn.commit()
    conn.close()

# Кэш в памяти: язык и бан читаются на КАЖДОЕ сообщение, а меняются редко.
# Пишет в базу по-прежнему только save_lang / ban_user / unban_user — они же сбрасывают кэш.
_lang_cache = {}         # user_id -> "ru" | "kz" | "en"

_banned_ids = None       # множество user_id; None — ещё не загружено

_CACHE_MAX = 100_000     # страховка от бесконечного роста

def save_lang(user_id, lang):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET lang=? WHERE user_id=?", (lang, user_id))
    conn.commit()
    conn.close()
    _lang_cache.pop(user_id, None)       # следующее чтение возьмёт свежее значение из базы

def get_lang(user_id):
    lang = _lang_cache.get(user_id)
    if lang is not None:
        return lang
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT lang FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    lang = row[0] if row and row[0] else "ru"
    if len(_lang_cache) >= _CACHE_MAX:
        _lang_cache.clear()
    _lang_cache[user_id] = lang
    return lang

def _load_banned():
    global _banned_ids
    conn = sqlite3.connect(DB_PATH)
    try:
        _banned_ids = {r[0] for r in conn.execute("SELECT user_id FROM banned_users")}
    finally:
        conn.close()

def reset_user_caches():
    """Сбросить кэши (после /restore: база подменена целиком)."""
    _lang_cache.clear()
    _sub_cache.clear()
    _load_banned()

def _total_searches(c):
    """Все поиски за всё время: свежие строки + то, что уже свёрнуто в архив."""
    return c.execute("SELECT (SELECT COUNT(*) FROM stats) + (SELECT COALESCE(SUM(n),0) FROM stats_archive)").fetchone()[0]

def _top_subjects(c, limit=5):
    return c.execute(
        """SELECT subject, SUM(n) AS cnt FROM (
               SELECT subject, COUNT(*) AS n FROM stats GROUP BY subject
               UNION ALL
               SELECT subject, SUM(n) FROM stats_archive GROUP BY subject
           ) GROUP BY subject ORDER BY cnt DESC LIMIT ?""", (limit,)).fetchall()

def get_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(DISTINCT user_id) FROM users")
    total_users = c.fetchone()[0]
    top_subjects = _top_subjects(c)
    total_searches = _total_searches(c)
    conn.close()
    return total_users, total_searches, top_subjects

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
    if _banned_ids is None:
        _load_banned()
    return user_id in _banned_ids

def ban_user(user_id, reason=""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO banned_users (user_id, banned_at, reason) VALUES (?,?,?)",
              (user_id, datetime.now().isoformat(), reason))
    conn.commit()
    conn.close()
    if _banned_ids is None:
        _load_banned()
    else:
        _banned_ids.add(user_id)

def unban_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM banned_users WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    if _banned_ids is None:
        _load_banned()
    else:
        _banned_ids.discard(user_id)

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
    total_searches = _total_searches(c)
    top_subjects = _top_subjects(c)
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
    c.execute("""SELECT m, SUM(n), COUNT(DISTINCT user_id) FROM (
                     SELECT SUBSTR(created_at,1,7) AS m, user_id, 1 AS n FROM stats WHERE created_at IS NOT NULL
                     UNION ALL
                     SELECT month, user_id, n FROM stats_archive
                 ) GROUP BY m ORDER BY m""")
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
                        (SELECT COUNT(*) FROM stats s WHERE s.user_id = u.user_id)
                        + (SELECT COALESCE(SUM(a.n),0) FROM stats_archive a WHERE a.user_id = u.user_id) AS n
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

    _ensure_indexes(c)
    conn.commit()
    conn.close()

init_db()

migrate_db()

# =========================
# ПОМОЩНИКИ АДМИНА («правая рука»)
# Владелец (ADMIN_ID) всегда выше. Помощники хранятся в БД (/addadmin) и/или в
# переменной окружения EXTRA_ADMIN_IDS=111,222 (она не стирается при перезапуске).
# =========================
def _parse_ids(raw):
    out = set()
    for part in re.split(r"[,\s;]+", raw or ""):
        if part.strip().isdigit():
            out.add(int(part))
    return out

_ENV_HELPERS = _parse_ids(os.getenv("EXTRA_ADMIN_IDS", ""))

_DB_HELPERS = set()

def reload_helpers():
    global _DB_HELPERS
    conn = sqlite3.connect(DB_PATH)
    _DB_HELPERS = {r[0] for r in conn.execute("SELECT user_id FROM admins")}
    conn.close()

def helper_ids():
    return (_DB_HELPERS | _ENV_HELPERS) - {ADMIN_ID}

def is_owner(user_id) -> bool:
    return user_id == ADMIN_ID

def is_staff(user_id) -> bool:
    """Владелец или помощник."""
    return user_id == ADMIN_ID or user_id in _DB_HELPERS or user_id in _ENV_HELPERS

def add_helper(user_id, added_by):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO admins (user_id, added_at, added_by) VALUES (?,?,?)",
                 (user_id, datetime.now().isoformat(), added_by))
    conn.commit()
    conn.close()
    reload_helpers()

def remove_helper(user_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM admins WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    reload_helpers()

def resolve_user(token):
    """'@username' или число → (user_id, отображаемое имя) либо (None, None)."""
    token = (token or "").strip()
    conn = sqlite3.connect(DB_PATH)
    try:
        if token.startswith("@"):
            row = conn.execute("SELECT user_id, first_name FROM users WHERE username=?",
                               (token.lstrip("@"),)).fetchone()
            return (row[0], f"{row[1]} ({token})") if row else (None, None)
        if token.isdigit():
            uid = int(token)
            row = conn.execute("SELECT first_name, username FROM users WHERE user_id=?", (uid,)).fetchone()
            if row:
                uname = f" (@{row[1]})" if row[1] else ""
                return uid, f"{row[0] or uid}{uname}"
            return uid, str(uid)
        return None, None
    finally:
        conn.close()

reload_helpers()

_SUBS_DDL = """CREATE TABLE IF NOT EXISTS channel_subs (
    user_id INTEGER PRIMARY KEY,
    is_member INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
)"""

_sub_cache = {}          # user_id -> (is_member, updated_at); зеркало таблицы channel_subs

def _sub_db_get(user_id):
    """(is_member, updated_at) или None, если записи нет."""
    rec = _sub_cache.get(user_id)
    if rec is not None:
        return rec
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(_SUBS_DDL)   # на случай, если базу подменили копией без этой таблицы (/restore)
        row = conn.execute(
            "SELECT is_member, updated_at FROM channel_subs WHERE user_id=?", (user_id,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    rec = (bool(row[0]), row[1])
    if len(_sub_cache) >= _CACHE_MAX:
        _sub_cache.clear()
    _sub_cache[user_id] = rec
    return rec

def _sub_db_set(user_id, is_member):
    now = int(time.time())
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(_SUBS_DDL)
        conn.execute(
            "INSERT INTO channel_subs (user_id, is_member, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET is_member=excluded.is_member, updated_at=excluded.updated_at",
            (user_id, 1 if is_member else 0, now),
        )
        conn.commit()
    finally:
        conn.close()
    _sub_cache[user_id] = (bool(is_member), now)
