"""Предметы: названия, фото, ключевые слова и поиск предмета по тексту."""

import re

from books import _DYN_NAMES


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

# Предметы БЕЗ препаратов
NO_PREPARATY = {"biohimiya", "fiziologiya", "ishki", "farmakologiya",
                "mikrobiologiya", "genetika", "biofizika", "tarih"}

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
