"""База книг (BOOKS_DB): загрузка, замена на месте, сохранение, поиск по ссылке/ID,
файл ручной сортировки."""

import json as _json
import os

from core import BASE_DIR


_books_db_path = os.path.join(BASE_DIR, "books_db.json")

if os.path.exists(_books_db_path):
    with open(_books_db_path, "r", encoding="utf-8") as _f:
        BOOKS_DB = _json.load(_f)
else:
    BOOKS_DB = {}

BOOKS_VERSION = 0       # растёт при каждой замене базы: по нему кэши поиска понимают, что пора пересобраться

def books_version():
    return BOOKS_VERSION

def replace_books_db(new_db):
    """Заменить содержимое BOOKS_DB НА МЕСТЕ — все модули держат ссылку на один и тот же объект."""
    global BOOKS_VERSION
    BOOKS_DB.clear()
    BOOKS_DB.update(new_db)
    BOOKS_VERSION += 1

# =========================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =========================
def find_book(query):
    # Поиск теперь через books_db.json
    return None

def _find_by_message_id(mid):
    for sc, langs in BOOKS_DB.items():
        for lg, books in langs.items():
            for i, bk in enumerate(books):
                if bk.get("message_id") == mid:
                    return sc, lg, i
    return None

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

_DYN_NAMES = {}            # code -> «📖 Название» для разделов, созданных из хэштегов
