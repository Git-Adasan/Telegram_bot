# -*- coding: utf-8 -*-
"""
merge_patch.py — объединяет исправления с твоим main.py.

Как запустить (файл положи В ТУ ЖЕ ПАПКУ, где main.py):
    python merge_patch.py            # правит main.py
    python merge_patch.py другой.py  # или любой другой файл

Скрипт ничего не ломает: сначала делает копию main_before_merge.py,
правит только если все места найдены, и проверяет, что код компилируется.
Если что-то не так — твой файл остаётся как был.
"""
import sys, os, py_compile, shutil, tempfile

path = sys.argv[1] if len(sys.argv) > 1 else "main.py"
raw = open(path, encoding="utf-8", newline="").read()
crlf = "\r\n" in raw
src = raw.replace("\r\n", "\n")

OLD_FIND_SUBJECT = 'def find_subject(query):\n    q = query.lower().strip()\n    for code, keywords in SUBJECT_KEYWORDS.items():\n        for kw in keywords:\n            if kw in q:\n                return code\n    return None\n'
NEW_FIND_SUBJECT = '# Составные названия: ВСЕ основы должны встретиться в запросе (в любом порядке и падеже).\n# Ловят «патологическая физиология», «патологический физиология», «патологиялық анатомия» и т.п.\nSUBJECT_COMBOS = {\n    "patfiz":  [("патолог", "физиол"), ("пат", "физ")],\n    "patanat": [("патолог", "анатом"), ("пат", "анат")],\n    "toanat":  [("топограф", "анатом"), ("топ", "анат")],\n}\n\ndef _norm_q(s):\n    s = s.lower().replace("ё", "е")\n    return re.sub(r"[^\\w\\s]", " ", s).strip()\n\ndef find_subject(query):\n    """Выбирает самое ТОЧНОЕ совпадение, а не первое.\n    Раньше «анат» (анатомия) находилось внутри «патанат» и «топанат»,\n    а «физ» (физиология) — внутри «патфиз», поэтому бот путал предметы."""\n    q = _norm_q(query)\n    if not q:\n        return None\n    best_code, best_score = None, 0\n\n    # 1. Прямые ключевые слова: чем длиннее совпадение, тем оно точнее\n    for code, keywords in SUBJECT_KEYWORDS.items():\n        for kw in keywords:\n            kw = _norm_q(kw)\n            if kw and kw in q and len(kw) > best_score:\n                best_code, best_score = code, len(kw)\n\n    # 2. Составные названия — приоритетнее обычных ключевых слов\n    for code, combos in SUBJECT_COMBOS.items():\n        for stems in combos:\n            if all(re.search(r"(?<!\\w)" + re.escape(st), q) for st in stems):\n                score = 100 + sum(len(st) for st in stems)\n                if score > best_score:\n                    best_code, best_score = code, score\n\n    return best_code\n'
OLD_DETECT = '        def detect_subj(text):\n            tl = text.lower()\n            for tag, code in HASHTAG_MAP.items():\n                if tag in tl:\n                    return code\n            for subj, kws in SUBJECT_KW.items():\n                for kw in kws:\n                    if kw.lower() in tl:\n                        return subj\n            return "other"\n'
NEW_DETECT = '        def detect_subj(text):\n            tl = text.lower().replace("ё", "е")\n            # хэштеги: самый длинный — самый точный (#патанат раньше #анат)\n            tag_hits = [(len(tag), code) for tag, code in HASHTAG_MAP.items() if tag in tl]\n            if tag_hits:\n                return max(tag_hits)[1]\n            # составные названия\n            if "патолог" in tl and "физиол" in tl:\n                return "patfiz"\n            if "патолог" in tl and "анатом" in tl:\n                return "patanat"\n            if "топограф" in tl and "анатом" in tl:\n                return "toanat"\n            # обычные ключевые слова: самое длинное совпадение\n            best, best_len = None, 0\n            for subj, kws in SUBJECT_KW.items():\n                for kw in kws:\n                    kw = kw.lower()\n                    if kw in tl and len(kw) > best_len:\n                        best, best_len = subj, len(kw)\n            return best or "other"\n'
SORT_BLOCK = '# =========================\n# РАЗБОР РАЗДЕЛА "other" (/sort_other, только админ)\n# =========================\n# --- sort_other: logic ---\n_sort_overrides_path = os.path.join(BASE_DIR, "sort_overrides.json")\n_sort_skipped = set()   # message_id, пропущенные до перезапуска бота\n\ndef _load_sort_overrides():\n    try:\n        with open(_sort_overrides_path, encoding="utf-8") as f:\n            return _json.load(f)\n    except Exception:\n        return {}\n\ndef _save_sort_overrides(ov):\n    tmp = _sort_overrides_path + ".tmp"\n    with open(tmp, "w", encoding="utf-8") as f:\n        _json.dump(ov, f, ensure_ascii=False, indent=2)\n    os.replace(tmp, _sort_overrides_path)\n\ndef _pop_book(db, mid):\n    """Достаёт книгу из базы, где бы она ни лежала. Возвращает (язык, книга) или None."""\n    for sc, langs in db.items():\n        for lg, lst in langs.items():\n            for i, b in enumerate(lst):\n                if b.get("message_id") == mid:\n                    return lg, lst.pop(i)\n    return None\n\ndef _put_book(db, code, lg, book):\n    tgt = db.setdefault(code, {}).setdefault(lg, [])\n    tgt.append(book)\n    tgt.sort(key=lambda x: x["message_id"], reverse=True)   # как и во всей базе: новые сверху\n\ndef apply_sort_overrides(db):\n    """Применяет ручные решения админа к свежесобранной базе (вызывается из /update_books),\n    чтобы ручная сортировка не сбрасывалась при каждом обновлении."""\n    for mid, code in _load_sort_overrides().items():\n        if code == "other":\n            continue\n        found = _pop_book(db, int(mid))\n        if found:\n            _put_book(db, code, found[0], found[1])\n    return db\n\ndef _sort_queue():\n    ov = _load_sort_overrides()\n    out = []\n    for lg in ("rus", "kaz", "eng"):\n        for b in BOOKS_DB.get("other", {}).get(lg, []):\n            mid = b["message_id"]\n            if str(mid) in ov or mid in _sort_skipped:\n                continue\n            out.append((lg, b))\n    return out\n\ndef _sort_move(mid, code):\n    """Переносит книгу из other в предмет и запоминает решение."""\n    other = BOOKS_DB.get("other", {})\n    for lg, lst in other.items():\n        for i, b in enumerate(lst):\n            if b.get("message_id") == mid:\n                lst.pop(i)\n                _put_book(BOOKS_DB, code, lg, b)\n                save_books_db()\n                ov = _load_sort_overrides()\n                ov[str(mid)] = code\n                _save_sort_overrides(ov)\n                return True\n    return False\n# --- sort_other: handlers ---\n\nasync def _sort_send_files():\n    """Хостинг при перезапуске откатывает файлы — присылаем админу свежие копии."""\n    for fn, cap in (\n        ("books_db.json", "💾 books_db.json — замени этим файлом старый в проекте"),\n        ("sort_overrides.json", "💾 sort_overrides.json — положи в проект рядом с books_db.json "\n                                "(иначе /update_books забудет ручную сортировку)"),\n    ):\n        path = os.path.join(BASE_DIR, fn)\n        if os.path.exists(path):\n            try:\n                await bot.send_document(ADMIN_ID, FSInputFile(path), caption=cap)\n            except Exception as e:\n                logger.warning(f"sort_other: не отправился {fn}: {e}")\n\ndef _sort_card():\n    queue = _sort_queue()\n    if not queue:\n        return "✅ Разбор закончен — в other больше нет книг без решения.", None\n    lg, b = queue[0]\n    mid = b["message_id"]\n    caption = (b.get("caption") or "").strip().replace("\\n", " ")[:200]\n    text = (\n        f"📦 <b>other</b> — осталось: {len(queue)}\\n\\n"\n        f"📄 <b>{_html.escape(b.get(\'file_name\', \'?\'))}</b>\\n"\n        f"🌐 {LANG_LABELS.get(lg, lg)}\\n"\n        + (f"📝 {_html.escape(caption)}\\n" if caption else "")\n        + f"🔗 {b.get(\'url\', \'\')}\\n\\n"\n        "Куда отнести?"\n    )\n    rows, row = [], []\n    for label, code in SUBJECTS.items():\n        row.append(InlineKeyboardButton(text=label, callback_data=f"srt_{code}_{mid}"))\n        if len(row) == 2:\n            rows.append(row); row = []\n    if row:\n        rows.append(row)\n    rows.append([\n        InlineKeyboardButton(text="⏭ Пропустить", callback_data=f"srt_skip_{mid}"),\n        InlineKeyboardButton(text="📦 Оставить в other", callback_data=f"srt_keep_{mid}"),\n    ])\n    rows.append([InlineKeyboardButton(text="💾 Прислать файлы", callback_data="srt_files_0")])\n    return text, InlineKeyboardMarkup(inline_keyboard=rows)\n\n@dp.message(Command("sort_other"))\nasync def sort_other_command(message: types.Message):\n    if message.from_user.id != ADMIN_ID:\n        await message.answer("❌ Рұқсат жоқ!")\n        return\n    text, kb = _sort_card()\n    await message.answer(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)\n\n@dp.callback_query(lambda c: c.data and c.data.startswith("srt_"))\nasync def sort_other_callback(callback: types.CallbackQuery):\n    if callback.from_user.id != ADMIN_ID:\n        await callback.answer("❌ Рұқсат жоқ!", show_alert=True)\n        return\n    try:\n        _, code, mid_s = callback.data.split("_", 2)\n        mid = int(mid_s)\n    except ValueError:\n        await callback.answer("Қате / Ошибка данных")\n        return\n\n    if code == "files":\n        await callback.answer("💾 Отправляю файлы")\n        await _sort_send_files()\n        return\n    if code == "skip":\n        _sort_skipped.add(mid)\n        note = "⏭ Пропущено"\n    elif code == "keep":\n        ov = _load_sort_overrides()\n        ov[str(mid)] = "other"\n        _save_sort_overrides(ov)\n        note = "📦 Остаётся в other"\n    elif code in SUBJECTS.values():\n        note = f"✅ → {code}" if _sort_move(mid, code) else "⚠️ Книга уже перенесена"\n    else:\n        await callback.answer("Неизвестный предмет")\n        return\n\n    await callback.answer(note)\n    text, kb = _sort_card()\n    try:\n        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb,\n                                         disable_web_page_preview=True)\n    except Exception:\n        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb,\n                                      disable_web_page_preview=True)\n    if kb is None:               # разбор закончен — сразу присылаем файлы\n        await _sort_send_files()\n\n'

PATCHES = [
    ("1. find_subject: самое точное совпадение, а не первое",
     OLD_FIND_SUBJECT, NEW_FIND_SUBJECT),
    ("2. detect_subj в /update_books: то же исправление",
     OLD_DETECT, NEW_DETECT),
    ("3. спам-счётчик: .seconds -> .total_seconds()",
     "(now - t).seconds < 10", "(now - t).total_seconds() < 10"),
    ("4. админа не банить за мат в личке",
     "    mat = find_profanity(text)\n    if mat:\n        ban_user(message.from_user.id",
     "    mat = find_profanity(text) if user_id != ADMIN_ID else None\n    if mat:\n        ban_user(message.from_user.id"),
    ("5. антифлуд не мешает админу (нужно для /sort_other)",
     "        # Флуд\n        if hasattr(event, 'data'):  # callback",
     "        if user_id == ADMIN_ID:\n            return await handler(event, data)\n"
     "        # Флуд\n        if hasattr(event, 'data'):  # callback"),
    ("6. /update_books применяет ручную сортировку",
     '        new_db = result["new_db"]\n        total  = result["total"]\n',
     '        new_db = result["new_db"]\n        total  = result["total"]\n'
     '        apply_sort_overrides(new_db)   # ручная сортировка из /sort_other не сбрасывается\n'),
    ("7. команда /sort_other в меню админа",
     '        BotCommand(command="update_books", description="🔄 Кітаптарды жаңарту"),\n',
     '        BotCommand(command="update_books", description="🔄 Кітаптарды жаңарту"),\n'
     '        BotCommand(command="sort_other",   description="📦 Разобрать other"),\n'),
    ("8. разбор раздела other (/sort_other)",
     "# ---------- Популярное ----------", SORT_BLOCK + "# ---------- Популярное ----------"),
]

if "def sort_other_command" in src:
    sys.exit("Похоже, исправления уже применены (найден sort_other_command). Ничего не меняю.")

# --- Шаг 0: старая версия с автобаном «слово внутри текста» (MAT_WORDS) -> безопасный фильтр по целым словам.
# В новой версии (с find_profanity) этот шаг пропускается.
OLD_MAT_LOOP = "    for mat in MAT_WORDS:\n        if mat in text_lower:\n"
MAT_HELPER = '# Мат ищем по целым словам: короткие слова — только точное совпадение,\n# длинные корни — по началу слова. Раньше проверялось «слово внутри текста»,\n# и «ит» банило за «цитология», «лейкоцит», «Литвицкий», а «бля» — за «бляшка».\n_MAT_EXACT = {\n    "бля", "блять", "блядь", "сука", "суки", "ит", "тварь", "мразь", "гнида", "нокта",\n    "шайтан", "еба", "залупа", "шлюха", "мудак", "ублюдок", "гондон", "пидор", "пидар",\n    "выблядок",\n}\n_MAT_PREFIX = (\n    "пизд", "ебан", "хуй", "хуе", "хуи", "нахуй", "ахуе", "охуе", "выеб",\n    "мудил", "ублюд", "шлюх", "бляд", "пидор", "пидар",\n)\n\ndef find_profanity(text):\n    t = text.lower().replace("ё", "е")\n    words = re.findall(r"\\w+", t)\n    for w in words:\n        if w in _MAT_EXACT or w.startswith(_MAT_PREFIX):\n            return w\n    if "сорай кет" in t:\n        return "сорай кет"\n    return None\n\n'
MAT_ANCHOR = "# Закладки — ожидание страницы от юзера"
if "def find_profanity" not in src and OLD_MAT_LOOP in src and src.count(MAT_ANCHOR) == 1:
    lines = src.split("\n")
    st = next(i for i, l in enumerate(lines) if l == "    for mat in MAT_WORDS:")
    en = next(i for i in range(st, len(lines)) if lines[i].strip() == "# =============================")
    block = [l[4:] if l.startswith("    ") else l for l in lines[st + 2:en]]
    lines[st:en] = ["    mat = find_profanity(text)", "    if mat:"] + block
    src = "\n".join(lines).replace(MAT_ANCHOR, MAT_HELPER + MAT_ANCHOR, 1)
    print("  ✓ 0. автобан за мат: теперь по целым словам («цитология», «бляшка» больше не баним)")

problems = []
for title, old, new in PATCHES:
    n = src.count(old)
    if n != 1:
        problems.append(f"  ✗ {title}: нашлось мест: {n} (нужно 1)")
if problems:
    print("Файл НЕ изменён. Не нашёл нужные места в коде:")
    print("\n".join(problems))
    print("Пришли main.py файлом — я посмотрю, что отличается.")
    sys.exit(1)

for title, old, new in PATCHES:
    src = src.replace(old, new, 1)
    print("  ✓", title)

out = src.replace("\n", "\r\n") if crlf else src
tmp = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8", newline="")
tmp.write(out); tmp.close()
try:
    py_compile.compile(tmp.name, doraise=True)
except py_compile.PyCompileError as e:
    os.unlink(tmp.name)
    sys.exit(f"Ошибка компиляции после объединения, файл НЕ изменён:\n{e}")

backup = os.path.splitext(path)[0] + "_before_merge.py"
shutil.copyfile(path, backup)
with open(path, "w", encoding="utf-8", newline="") as f:
    f.write(out)
os.unlink(tmp.name)
print(f"\nГотово. Копия старого файла: {backup}")
print("Перезапусти бота и отправь ему /sort_other")
