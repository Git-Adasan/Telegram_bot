"""Тома одной книги объединяются в серию; обложки серий; нормализация каталога."""

import re

from books import BOOKS_DB, _load_sort_overrides, books_version
from core import logger
from subjects import SUBJECTS, find_subject


# =========================
# ТОМА ОДНОЙ КНИГИ — общее определение серии (используют поиск, списки и карточка)
# =========================
# --- series: logic ---
# ---------------------------------------------------------------------------
# ТОМА ОДНОЙ КНИГИ: единое определение «серии» для всех книг каталога.
# Серия = книга из нескольких файлов (том 1, 2, 3 ... / часть / бөлім / «Название 1», «Название 2»).
# Не зависит ни от языка, ни от предмета, которые бот присвоил файлу: в каталоге том 1 может лежать
# как rus, а том 2 как kaz, или в разных предметах. Книги в BOOKS_DB НЕ переносятся: серия — это
# «виртуальная» группа поверх базы, поэтому индексы в избранном/истории не ломаются.
# ---------------------------------------------------------------------------
_SX_LAT2CYR = str.maketrans({"a": "а", "e": "е", "o": "о", "p": "р", "c": "с", "x": "х",
                             "y": "у", "k": "к", "m": "м", "t": "т", "b": "в", "h": "н"})

_SX_TOKEN_RE = re.compile(r"[^\W\d_]+|\d+")

_SX_NOISE_RE = re.compile(
    r"[0-9a-f]{8}[-_ ][0-9a-f]{4}[-_ ][0-9a-f]{4}[-_ ][0-9a-f]{4}[-_ ][0-9a-f]{12}"   # UUID в имени файла
    r"|(?:tg[-_ ]?)?@\w+"                                                          # tg-@канал, @канал
    r"|\(\s*\d{1,4}\s*\)",                                                         # «(1)» — копия файла, «(2020)» — год
    re.I)

_SX_VOL_WORDS = {
    "том", "тома", "томе", "томов", "tom", "toma", "tomi", "т", "t",
    "часть", "части", "chast", "chasti", "ч", "ch",
    "бөлім", "бөлiм", "бөлим", "белим", "bolim", "belim", "бөлімі",
    "vol", "vols", "volume", "volumes", "part", "parts", "pt",
    "книга", "кн", "book", "bk", "выпуск", "вып",
}

_SX_SUFFIX = {"й", "я", "ый", "ая", "ой", "ий", "е", "ое", "th", "st", "nd", "rd", "ші", "шы"}

_SX_TOTAL_PREFIX = {"в", "из", "in", "of", "на"}        # «в 2 томах», «in 2 vols» — число томов, не номер

_SX_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10}

_SX_NOT_A_VOLUME = {   # слова, рядом с которыми число в конце — не том (издания, лекции, классы…)
    "издание", "изд", "ed", "edition", "лекция", "дәріс", "lecture", "глава", "chapter", "тема",
    "тест", "билет", "вопрос", "урок", "sem", "курс", "класс", "сынып", "кл",
}

_SX_WEAK_MAX = 20

# Ручное объединение, если бот не смог склеить сам (названия томов совсем разные).
# Добавляй сюда свои серии: {"ids": [номера постов-файлов в канале], "title": "Название серии"}
SERIES_FORCE = [
    {"ids": [1168, 1169, 1170, 1171, 1172, 1173, 1174, 1175, 1176, 1177, 1178], "title": "ITI Treatment Guide"},
]

def _sx_fix_token(tok):
    """Слово из кириллицы и латиницы вперемешку («тoм» с латинской o) -> целиком кириллицей."""
    if re.search(r"[а-яёәіңғүұқөһ]", tok) and re.search(r"[a-z]", tok):
        return tok.translate(_SX_LAT2CYR)
    return tok

def _sx_num(tok):
    if tok.isdigit():
        return int(tok)
    return _SX_ROMAN.get(tok.replace("і", "i").replace("х", "x"))

def sx_parse(file_name):
    """Разбор имени файла.
    -> {"key": слова названия БЕЗ номера тома/года/мусора (tuple),
        "vol": номер тома или None,
        "explicit": номер найден по слову «том/часть/бөлім/vol…»,
        "weak": номер — просто число в конце имени («Название 2»),
        "title": название для показа (без номера тома)}"""
    raw = re.sub(r"\.(pdf|djvu|epub|zip|rar)$", "", file_name or "", flags=re.I).replace("_", " ")
    low = raw.lower().replace("ё", "е")
    noise = [(m.start(), m.end()) for m in _SX_NOISE_RE.finditer(low)]
    for a, b in noise:                                  # пробелами той же длины: позиции не сдвигаются
        low = low[:a] + " " * (b - a) + low[b:]
    toks = [(m.group(), m.start(), m.end()) for m in _SX_TOKEN_RE.finditer(low)]
    words = [_sx_fix_token(t[0]) for t in toks]
    n = len(words)
    marker, total = set(), set()
    vol = None
    for i, w in enumerate(words):
        if w not in _SX_VOL_WORDS:
            continue
        if i + 1 < n and _sx_num(words[i + 1]) is not None and (i + 1) not in marker:   # «том 1», «т.1»
            if vol is None:
                vol = _sx_num(words[i + 1])
            marker.update((i, i + 1))
            continue
        j = i - 1                                                                         # «1 том», «1-й том», «2bolim»
        if j >= 0 and words[j] in _SX_SUFFIX:
            j -= 1
        if j >= 0 and _sx_num(words[j]) is not None and j not in marker:
            if j - 1 >= 0 and words[j - 1] in _SX_TOTAL_PREFIX:
                total.update(range(j - 1, i + 1))
                continue
            if vol is None:
                vol = _sx_num(words[j])
            marker.update(range(j, i + 1))
    explicit = bool(marker)
    drop = set(marker) | total
    weak = False
    if not explicit:                                    # число в конце: «Адайбаев Анатомия 2»
        k = n - 1
        while k >= 0 and words[k].isdigit() and len(words[k]) == 4 and 1900 <= int(words[k]) <= 2099:
            k -= 1                                      # год в конце не трогаем, смотрим левее
        end = k
        while k >= 0 and words[k].isdigit() and len(words[k]) <= 2:
            k -= 1
        if k < end and k >= 0 and len(words[k]) >= 3 and words[k] not in _SX_NOT_A_VOLUME:
            first = int(words[k + 1])
            if 1 <= first <= _SX_WEAK_MAX:
                vol, weak = first, True
                drop.update(range(k + 1, end + 1))
    keep = [q for q, w in enumerate(words)
            if q not in drop and not (w.isdigit() and len(w) == 4 and 1900 <= int(w) <= 2099)]
    key = tuple(words[q] for q in keep)
    key_orig = tuple(raw[toks[q][1]:toks[q][2]] for q in keep)
    cut = sorted([(toks[q][1], toks[q][2]) for q in drop] + noise)
    out, pos = [], 0
    for a, b in cut:
        if a >= pos:
            out.append(raw[pos:a])
            pos = b
    out.append(raw[pos:])
    title = re.sub(r"\s+", " ", "".join(out)).strip(" .,-–—;:()")
    title = re.sub(r"\s+([,.;:])", r"\1", title)
    return {"key": key, "key_orig": key_orig, "vol": vol, "explicit": explicit, "weak": weak,
            "title": title if key else ""}

def sx_caption_title(caption):
    """Первая строка подписи поста («✏️Название») без эмодзи и хэштегов. Пусто, если в ней номер тома."""
    for line in (caption or "").splitlines():
        t = re.sub(r"#\w+|\[[^\]]*\]\([^)]*\)|https?://\S+", " ", line)
        t = re.sub(r"^[^\w]+", "", t).strip()
        if not t or re.match(r"^[👤📚🔗📌]", line.strip()):
            continue
        p = sx_parse(t)
        return "" if p["explicit"] else re.sub(r"\s+", " ", t).strip(" .,-–—;:")
    return ""

def _sx_prefix_len(a, b):
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n

def sx_build(books):
    """books: [{"mid", "name", "caption", "photo"}]  ->  {"of": {mid: sid}, "series": {sid: {...}}}.
    В серии только 2+ файла. Правила от сильных к слабым; склейка отклоняется, если у серии
    получились бы два файла с одним номером тома (значит это разные книги/издания)."""
    from difflib import SequenceMatcher
    info = {}
    for b in books:
        p = sx_parse(b["name"])
        p["cap"] = ""
        if not p["key"]:                                 # имя «том 1.pdf» — название берём из подписи
            ct = sx_caption_title(b.get("caption", ""))
            if ct:
                p["cap"] = ct
                p["key"] = sx_parse(ct)["key"]
                p["title"] = ct
        info[b["mid"]] = {**p, "mid": b["mid"], "photo": b.get("photo"), "book": b}
    order = sorted(info)
    parent = {m: m for m in order}
    vols = {m: ({info[m]["vol"]} if info[m]["vol"] is not None else set()) for m in order}
    why = {}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b, rule, force=False):
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        if not force and vols[ra] & vols[rb]:
            return
        parent[rb] = ra
        vols[ra] |= vols[rb]
        why[a] = why[b] = rule

    # 1. одна обложка (один пост-обложка у нескольких файлов)
    by_photo = {}
    for m in order:
        if info[m]["photo"]:
            by_photo.setdefault(info[m]["photo"], []).append(m)
    for members in by_photo.values():
        for m in members[1:]:
            union(members[0], m, "обложка", force=True)

    forced_title = {}
    for grp in SERIES_FORCE:                              # ручные серии: сильнее всех правил
        ids = [m for m in grp["ids"] if m in info]
        for m in ids[1:]:
            union(ids[0], m, "вручную", force=True)
        if len(ids) >= 2:
            forced_title[min(ids)] = grp.get("title", "")
    expl = [m for m in order if info[m]["explicit"]]
    # 2. одинаковое название без номера тома
    by_key = {}
    for m in expl:
        if info[m]["key"]:
            by_key.setdefault(info[m]["key"], []).append(m)
    for key, members in by_key.items():
        for a, b in zip(members, members[1:]):
            if len(key) >= 2 or b - a <= 3:              # короткое/общее слово («анатомия») — только соседние посты
                union(a, b, "название")
        if len(key) >= 2:                                 # длинное название: можно и не подряд
            for m in members[1:]:
                union(members[0], m, "название")
    # 3. общее начало названия у подряд идущих постов (подзаголовки у томов разные)
    for a, b in zip(expl, expl[1:]):
        ka, kb = info[a]["key"], info[b]["key"]
        if b - a <= 1 and ka and kb:
            pl = _sx_prefix_len(ka, kb)
            if pl >= 3 or (pl >= 2 and pl >= 0.6 * min(len(ka), len(kb))):
                union(a, b, "начало названия")
    # 4. «том 1», «том 2» без названия: подряд идущие посты
    for a, b in zip(expl, expl[1:]):
        if b - a <= 1 and not info[a]["key"] and not info[b]["key"]:
            union(a, b, "тома подряд")
    # 5. число в конце имени («Анатомия 1», «Анатомия 2»): только соседи, без конфликта обложек
    weak_ids = [m for m in order if info[m]["weak"] or (not info[m]["explicit"] and info[m]["vol"] is None)]
    for i, a in enumerate(weak_ids):
        for b in weak_ids[i + 1:i + 4]:
            if b - a > 2:
                break
            ia, ib = info[a], info[b]
            if not (ia["weak"] or ib["weak"]):
                continue
            if not ia["key"] or not ib["key"] or max(len(w) for w in ia["key"] + ib["key"]) < 4:
                continue
            if set(ia["key"]) & _SX_NOT_A_VOLUME or set(ib["key"]) & _SX_NOT_A_VOLUME:
                continue
            if ia["photo"] and ib["photo"] and ia["photo"] != ib["photo"]:
                continue                                  # у каждого своя обложка — разные издания
            if SequenceMatcher(None, " ".join(ia["key"]), " ".join(ib["key"])).ratio() < 0.9:
                continue
            union(a, b, "номер в конце имени")

    comps = {}
    for m in order:
        comps.setdefault(find(m), []).append(m)
    series, of = {}, {}
    for members in comps.values():
        if len(members) < 2:
            continue
        sid = f"s{min(members)}"
        recs = [info[m] for m in members]
        # файл без номера рядом с «-2», «-3» — это том 1
        numbered = {r["vol"] for r in recs if r["vol"] is not None}
        blank = [r for r in recs if r["vol"] is None]
        assumed = None
        if numbered and len(blank) == 1 and 1 not in numbered and any(r["weak"] for r in recs):
            assumed = blank[0]["mid"]
        def vnum(r):
            return 1 if r["mid"] == assumed else r["vol"]
        recs.sort(key=lambda r: (vnum(r) is None, vnum(r) if vnum(r) is not None else 0, r["mid"]))
        # название серии: если у всех томов одинаковое — оно; иначе общее начало названий
        titles = [r["title"] for r in recs]
        if len(set(titles)) == 1:
            title = titles[0]
        else:
            ks = [r["key"] for r in recs]
            n_common = min(_sx_prefix_len(ks[0], k) for k in ks[1:])
            title = " ".join(recs[0]["key_orig"][:n_common]) if n_common >= 2 else titles[0]
        title = title.strip(" .,-–—;:(")
        for fm, ft in forced_title.items():
            if fm in members and ft:
                title = ft
        series[sid] = {
            "id": sid, "title": title, "rule": why.get(members[0], why.get(members[-1], "")),
            "members": [{"mid": r["mid"], "vol": vnum(r), "title": r["title"]} for r in recs],
        }
        for m in members:
            of[m] = sid
    return {"of": of, "series": series}

# --- series: runtime ---
def _sx_books_from(db):
    out = []
    for langs in db.values():
        for lst in langs.values():
            for b in lst:
                out.append({"mid": b["message_id"], "name": b.get("file_name", ""),
                            "caption": b.get("caption", ""), "photo": b.get("photo_message_id")})
    return out

_sx_cache = {"sig": None, "data": {"of": {}, "series": {}}}

def series_index():
    """Серии по текущей BOOKS_DB. Пересчитывается только после изменения базы (/update_books, обложки)."""
    books = _sx_books_from(BOOKS_DB)
    sig = (books_version(), len(books), sum(b["mid"] for b in books), sum(1 for b in books if b["photo"]))
    if _sx_cache["sig"] != sig:
        try:
            _sx_cache["data"] = sx_build(books)
        except Exception as e:                      # ошибка разбора не должна ронять поиск
            logger.warning(f"Серии томов не построились: {e}")
            _sx_cache["data"] = {"of": {}, "series": {}}
        _sx_cache["sig"] = sig
    return _sx_cache["data"]

def _sx_series_lang(members):
    """Язык серии: преобладающий. При равенстве — казахский, если в названии/подписи есть казахские буквы."""
    from collections import Counter
    top = Counter(m["lang"] for m in members).most_common()
    if len(top) == 1 or top[0][1] > top[1][1]:
        return top[0][0]
    kz = re.compile(r"[әіңғүұқөһ]", re.I)
    if any(l == "kaz" for l, _ in top) and any(
            kz.search(m["book"].get("file_name", "") + " " + m["book"].get("caption", "")) for m in members):
        return "kaz"
    return members[0]["lang"]

def _sx_series_subject(members):
    """Предмет серии: чаще всего встречающийся среди томов (раздел other — только если больше ничего нет)."""
    from collections import Counter
    codes = [m["sc"] for m in members if m["sc"] != "other"] or [m["sc"] for m in members]
    return Counter(codes).most_common(1)[0][0]

def series_info(mid):
    """Вся серия, в которую входит книга message_id=mid (все предметы и языки), или None, если книга одна."""
    data = series_index()
    sid = data["of"].get(mid)
    if not sid:
        return None
    loc = {}
    for sc, langs in BOOKS_DB.items():
        for lg, lst in langs.items():
            for idx, b in enumerate(lst):
                loc[b["message_id"]] = (sc, lg, idx, b)
    members = []
    for m in data["series"][sid]["members"]:
        place = loc.get(m["mid"])
        if place:
            members.append({"vol": m["vol"], "title": m["title"], "sc": place[0], "lang": place[1],
                            "idx": place[2], "book": place[3]})
    if len(members) < 2:
        return None
    return {
        "id": sid, "title": data["series"][sid]["title"], "members": members,
        "lang": _sx_series_lang(members), "subject": _sx_series_subject(members),
        "cover": next((m["book"].get("photo_message_id") for m in members
                       if m["book"].get("photo_message_id")), None),
    }

def propagate_series_covers(db):
    """У всех томов серии одна обложка: тому без своей обложки даём обложку серии. Возвращает число книг."""
    try:
        res = sx_build(_sx_books_from(db))
    except Exception as e:
        logger.warning(f"Обложки серий не подставились: {e}")
        return 0
    by_mid = {b["message_id"]: b for langs in db.values() for lst in langs.values() for b in lst}
    n = 0
    for s in res["series"].values():
        books = [by_mid[m["mid"]] for m in s["members"] if m["mid"] in by_mid]
        cover = next((b.get("photo_message_id") for b in books if b.get("photo_message_id")), None)
        if not cover:
            continue
        for b in books:
            if not b.get("photo_message_id"):
                b["photo_message_id"] = cover
                n += 1
    return n

# --- series: end ---

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

def _plain_name(fname):
    return re.sub(r"\.(pdf|djvu|epub)$", "", fname or "", flags=re.I).replace("_", " ").strip()
