"""Умный поиск книг: опечатки, латиница/кириллица, точные вхождения (в отдельном потоке)."""

import asyncio
import re
from functools import lru_cache

from books import BOOKS_DB, books_version
from subjects import SUBJECT_COMBOS, SUBJECT_KEYWORDS, _norm_q, find_subject


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
    return (books_version(), tuple(
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
    # Авторы: русское написание «на слух» <-> английское. Добавляйте свои строки сюда.
    ("гайтон", "guyton"),
    ("грей", "грейс", "gray", "gray's"),
    ("роббинс", "робинс", "robbins"),
    ("собота", "соботта", "sobotta"),
    ("харпер", "harper"),
    ("каплан", "kaplan"),
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

_exact_cache = {"sig": None, "items": []}

def _get_exact_index():
    """Плоский список (предмет, язык, номер, книга, имя файла, подпись) — уже в нижнем регистре.
    Пересобирается только когда меняется BOOKS_DB (как и нечёткий индекс)."""
    sig = _books_signature()
    if _exact_cache["sig"] != sig:
        items = []
        for sc, langs in BOOKS_DB.items():
            for book_lang, books in langs.items():
                for idx, bk in enumerate(books):
                    items.append((sc, book_lang, idx, bk,
                                  bk.get("file_name", "").lower(), bk.get("caption", "").lower()))
        _exact_cache["items"] = items
        _exact_cache["sig"] = sig
    return _exact_cache["items"]

def _exact_find_books(variants):
    """Точные вхождения запроса в имя файла или подпись. Работает в отдельном потоке."""
    items = _get_exact_index()
    exact = {}
    for variant in variants:
        q = variant.lower().strip()
        if not q:
            continue
        for sc, book_lang, idx, bk, fname, cap in items:
            if q in fname or q in cap:
                exact[(sc, book_lang, idx)] = (sc, book_lang, idx, bk)
    return exact

async def search_books_multilingual(query, limit=5):
    """Точные вхождения по языковым вариантам + нечёткий (фонетический) поиск ВМЕСТЕ.

    Раньше при любом точном совпадении (например «Неттер» в русских названиях) нечёткий
    поиск не запускался, поэтому книги с английским названием (Frank Netter) не находились.
    Теперь русская запись «на слух» (Неттер, Нетер) находит и русские, и английские книги."""
    variants = expand_search_queries(query)
    exact = await asyncio.to_thread(_exact_find_books, variants)

    # Если точные совпадения уже есть, из нечётких берём только достаточно похожие,
    # чтобы не засорять выдачу случайными книгами.
    min_score = 0.9 if exact else 0.0
    fuzzy = {}
    for variant in variants:
        _total, found = await asyncio.to_thread(fuzzy_find_books, variant, 300, min_score)
        for sc, book_lang, idx, bk in found:
            fuzzy[(sc, book_lang, idx)] = (sc, book_lang, idx, bk)

    merged = dict(exact)
    for key, value in fuzzy.items():
        merged.setdefault(key, value)       # точные совпадения идут первыми
    results = list(merged.values())
    return len(results), results[:limit], (not exact) and bool(results)
