from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageFilter

BASE_DIR = Path(__file__).resolve().parent.parent
COVER_CACHE = BASE_DIR / "covers" / "cache"
FONT_REGULAR = BASE_DIR / "fonts" / "DejaVuSans.ttf"
FONT_BOLD = BASE_DIR / "fonts" / "DejaVuSans-Bold.ttf"
AVATAR_CANDIDATES = (BASE_DIR / "assets" / "adasan_avatar.jpg", BASE_DIR / "adasan.jpg")
AVATAR_PATH = next((p for p in AVATAR_CANDIDATES if p.is_file()), AVATAR_CANDIDATES[0])

# Premium navy palette
BG = (8, 13, 25)
PANEL = (16, 27, 48)
CARD = (34, 53, 81)
CARD_EDGE = (54, 76, 108)
WHITE = (245, 248, 255)
MUTED = (157, 177, 207)
GOLD = (255, 194, 67)
TEAL = (30, 190, 171)


def _font(size: int, bold: bool = False):
    path = FONT_BOLD if bold else FONT_REGULAR
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default()


def _rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius, fill=255)
    return mask


def _cover_for(entry: dict[str, Any]) -> Path | None:
    # Explicit local path takes priority; Telegram cache is populated by main.py.
    local = entry.get("cover_path")
    candidates = [Path(local)] if local else []
    cover_id = entry.get("cover_message_id")
    if cover_id:
        candidates.append(COVER_CACHE / f"{cover_id}.jpg")
        candidates.append(COVER_CACHE / f"{cover_id}.png")
    for path in candidates:
        if path.is_file():
            return path
    return None


def _draw_cover(canvas: Image.Image, entry: dict[str, Any], box: tuple[int, int, int, int]):
    x, y, w, h = box
    cover_path = _cover_for(entry)
    if cover_path:
        try:
            with Image.open(cover_path) as source:
                source = source.convert("RGB")
                # Cover image is cropped to a portrait frame without distortion.
                target_ratio = w / h
                source_ratio = source.width / source.height
                if source_ratio > target_ratio:
                    new_w = int(source.height * target_ratio)
                    left = (source.width - new_w) // 2
                    source = source.crop((left, 0, left + new_w, source.height))
                else:
                    new_h = int(source.width / target_ratio)
                    top = max(0, (source.height - new_h) // 2)
                    source = source.crop((0, top, source.width, top + new_h))
                source = source.resize((w, h), Image.Resampling.LANCZOS)
                canvas.paste(source, (x, y), _rounded_mask((w, h), 22))
                return
        except Exception:
            pass

    # Neutral fallback: deliberately not presented as a real book cover.
    placeholder = Image.new("RGB", (w, h), (24, 42, 67))
    pd = ImageDraw.Draw(placeholder)
    pd.rounded_rectangle((14, 14, w - 14, h - 14), 18, outline=(76, 105, 143), width=2)
    pd.text((w // 2, h // 2 - 16), "NO COVER", font=_font(23, True), fill=MUTED, anchor="mm")
    pd.text((w // 2, h // 2 + 22), "Adasan Library", font=_font(15), fill=(117, 145, 180), anchor="mm")
    canvas.paste(placeholder, (x, y), _rounded_mask((w, h), 22))


def _fit_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
    text = str(text or "Без названия").strip()
    if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
        return text
    while text and draw.textbbox((0, 0), text + "…", font=font)[2] > max_width:
        text = text[:-1]
    return text.rstrip() + "…"


def _gradient(width: int, height: int) -> Image.Image:
    """Тёмно-синий градиент: рисуем полоску 1 px и растягиваем (быстро)."""
    strip = Image.new("RGB", (1, height))
    for yy in range(height):
        t = yy / max(1, height - 1)
        strip.putpixel((0, yy), (int(9 + 5 * t), int(15 + 8 * t), int(29 + 15 * t)))
    return strip.resize((width, height))


def _wrap2(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    """Название в 1–2 строки; вторая строка обрезается с «…»."""
    text = " ".join(str(text or "Без названия").split())
    if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
        return [text]
    words, first = text.split(" "), ""
    for i, word in enumerate(words):
        trial = (first + " " + word).strip()
        if draw.textbbox((0, 0), trial, font=font)[2] > max_width:
            break
        first = trial
    else:
        return [first]
    if not first:                       # одно очень длинное слово
        first = _fit_text(draw, text, font, max_width).rstrip("…")
        rest = text[len(first):]
    else:
        rest = " ".join(words[len(first.split(" ")):])
    return [first, _fit_text(draw, rest, font, max_width)]


def render_top_image(entries: list[dict[str, Any]], total_opens: int) -> bytes:
    """Create a premium 3+2 book leaderboard PNG. All figures come from SQLite."""
    entries = entries[:5]
    width = 1500
    height = 800 if len(entries) <= 3 else 1250     # одна строка карточек или две
    img = _gradient(width, height)
    draw = ImageDraw.Draw(img)

    # Main panel with a soft shadow.
    shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((62, 42, width - 62, height - 38), 38, fill=(0, 0, 0, 145))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    img = Image.alpha_composite(img.convert("RGBA"), shadow)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((55, 30, width - 55, height - 52), 34, fill=PANEL)

    # Header: use the user's Adasan wolf emblem instead of generic stacked squares.
    avatar_size = 76
    avatar_box = (94, 61, 94 + avatar_size, 61 + avatar_size)
    try:
        with Image.open(AVATAR_PATH) as avatar_source:
            avatar_source = avatar_source.convert("RGB")
            side = min(avatar_source.width, avatar_source.height)
            left = (avatar_source.width - side) // 2
            top = (avatar_source.height - side) // 2
            avatar_source = avatar_source.crop((left, top, left + side, top + side))
            avatar_source = avatar_source.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)
            avatar_mask = Image.new("L", (avatar_size, avatar_size), 0)
            ImageDraw.Draw(avatar_mask).ellipse((0, 0, avatar_size - 1, avatar_size - 1), fill=255)
            draw.ellipse((avatar_box[0] - 3, avatar_box[1] - 3, avatar_box[2] + 3, avatar_box[3] + 3),
                         fill=(39, 126, 220), outline=(103, 192, 255), width=3)
            img.paste(avatar_source, (avatar_box[0], avatar_box[1]), avatar_mask)
            draw = ImageDraw.Draw(img)
    except Exception:
        draw.ellipse((94, 61, 170, 137), fill=(23, 87, 157), outline=(103, 192, 255), width=3)
        draw.text((132, 99), "A", font=_font(38, True), fill=WHITE, anchor="mm")
    draw.text((190, 72), "Adasan Library", font=_font(49, True), fill=WHITE)
    draw.text((98, 155), "TOP-5 ПОПУЛЯРНЫХ КНИГ", font=_font(23, True), fill=MUTED)
    draw.rounded_rectangle((1280, 78, 1395, 121), 20, fill=(13, 75, 57))
    draw.text((1337, 100), "● LIVE", font=_font(19, True), fill=(71, 226, 157), anchor="mm")

    # Up to 3 cards are centered on one row; 4-5 use a 3+2 layout.
    card_w, card_h = 405, 420
    gap_x, gap_y = 18, 24
    top_y = 205
    positions = []
    if len(entries) <= 3:
        row_width = len(entries) * card_w + max(0, len(entries) - 1) * gap_x
        first_x = (width - row_width) // 2
        positions = [(first_x + i * (card_w + gap_x), top_y) for i in range(len(entries))]
    else:
        first_x = (width - (3 * card_w + 2 * gap_x)) // 2
        positions = [(first_x + i * (card_w + gap_x), top_y) for i in range(3)]
        second_count = len(entries) - 3
        second_width = second_count * card_w + max(0, second_count - 1) * gap_x
        second_x = (width - second_width) // 2
        second_y = top_y + card_h + gap_y
        positions += [(second_x + i * (card_w + gap_x), second_y) for i in range(second_count)]

    for idx, entry in enumerate(entries):
        x, y = positions[idx]
        accent = GOLD if idx == 0 else (TEAL if idx < 3 else (117, 159, 210))
        draw.rounded_rectangle((x, y, x + card_w, y + card_h), 24, fill=CARD,
                               outline=CARD_EDGE, width=2)
        draw.text((x + card_w // 2, y + 35), f"{idx + 1}", font=_font(37, True),
                  fill=accent, anchor="mm")

        cover_w, cover_h = 270, 235
        cover_x = x + (card_w - cover_w) // 2
        cover_y = y + 70
        _draw_cover(img, entry, (cover_x, cover_y, cover_w, cover_h))
        draw = ImageDraw.Draw(img)

        t_font = _font(21, True)
        lines = _wrap2(draw, entry.get("title", "Без названия"), t_font, card_w - 42)
        if len(lines) == 1:
            draw.text((x + card_w // 2, y + 336), lines[0], font=t_font, fill=WHITE, anchor="mm")
        else:
            draw.text((x + card_w // 2, y + 322), lines[0], font=t_font, fill=WHITE, anchor="mm")
            draw.text((x + card_w // 2, y + 348), lines[1], font=t_font, fill=WHITE, anchor="mm")
        count = f'{int(entry.get("opens", 0)):,}'.replace(',', ' ')
        draw.text((x + card_w // 2, y + 380), count, font=_font(32, True), fill=accent, anchor="mm")
        # «открытий  ♥ 12» — подпись и число лайков в одной строке по центру
        lab_font, likes = _font(16), int(entry.get("likes", 0) or 0)
        lab = "открытий"
        heart = f"♥ {likes}"
        w_lab = draw.textlength(lab, font=lab_font)
        w_heart = draw.textlength(heart, font=lab_font)
        start = x + card_w // 2 - (w_lab + 22 + w_heart) / 2
        draw.text((start, y + 406), lab, font=lab_font, fill=MUTED, anchor="lm")
        draw.text((start + w_lab + 22, y + 406), heart, font=lab_font, fill=(255, 107, 129), anchor="lm")

    # Footer summary (всё внутри панели: она заканчивается на height - 52)
    footer_y = height - 90
    draw.line((95, footer_y - 45, width - 95, footer_y - 45), fill=(53, 72, 101), width=2)
    draw.text((98, footer_y - 12), "Всего открытий книг", font=_font(20), fill=MUTED, anchor="lm")
    total = f"{int(total_opens):,}".replace(',', ' ')
    draw.text((width - 100, footer_y - 12), total, font=_font(30, True), fill=WHITE, anchor="rm")
    draw.text((width // 2, footer_y + 22), "@LIBRARY_ADASAN", font=_font(17), fill=(125, 151, 185), anchor="mm")

    output = io.BytesIO()
    img.convert("RGB").save(output, format="PNG", optimize=True)
    return output.getvalue()

def render_favorites_image(entries: list[dict[str, Any]]) -> bytes:
    """Premium personal favorites card. It intentionally contains no book-cover photos."""
    entries = entries[:30]
    width = 1500
    row_h = 82
    height = max(560, 360 + row_h * max(1, len(entries)))
    img = _gradient(width, height)

    img = img.convert("RGBA")
    shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle((62, 42, width - 62, height - 38), 38, fill=(0, 0, 0, 145))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    img = Image.alpha_composite(img, shadow)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((55, 30, width - 55, height - 52), 34, fill=PANEL)

    # Adasan wolf avatar, cropped as a circular emblem.
    avatar_size = 76
    try:
        with Image.open(AVATAR_PATH) as source:
            source = source.convert("RGB")
            side = min(source.width, source.height)
            left = (source.width - side) // 2
            top = (source.height - side) // 2
            source = source.crop((left, top, left + side, top + side))
            source = source.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)
            mask = Image.new("L", (avatar_size, avatar_size), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, avatar_size - 1, avatar_size - 1), fill=255)
            draw.ellipse((91, 58, 173, 140), fill=(39, 126, 220), outline=(103, 192, 255), width=3)
            img.paste(source, (97, 64), mask)
            draw = ImageDraw.Draw(img)
    except Exception:
        draw.ellipse((94, 61, 170, 137), fill=(23, 87, 157), outline=(103, 192, 255), width=3)
        draw.text((132, 99), "A", font=_font(38, True), fill=WHITE, anchor="mm")

    draw.text((190, 72), "Adasan Library", font=_font(49, True), fill=WHITE)
    draw.text((96, 170), "Мои любимые книги", font=_font(54, True), fill=GOLD)
    draw.text((98, 244), "Личная подборка пользователя", font=_font(29), fill=MUTED)

    count = len(entries)
    badge = (width - 310, 176, width - 100, 238)
    draw.rounded_rectangle(badge, 26, fill=(6, 78, 59))
    draw.text(((badge[0] + badge[2]) // 2, (badge[1] + badge[3]) // 2),
              f"{count} КНИГ", font=_font(25, True), fill=(110, 231, 183), anchor="mm")

    y0 = 320
    if not entries:
        draw.rounded_rectangle((96, y0, width - 96, y0 + 90), 20, fill=CARD)
        draw.text((130, y0 + 45), "Пока нет любимых книг — добавьте их из карточек библиотеки.",
                  font=_font(24), fill=WHITE, anchor="lm")
    else:
        for index, entry in enumerate(entries):
            y = y0 + index * row_h
            draw.rounded_rectangle((96, y, width - 96, y + 66), 16, fill=CARD, outline=CARD_EDGE, width=1)
            draw.text((128, y + 33), f"{index + 1:02d}", font=_font(27, True), fill=GOLD, anchor="lm")
            title = _fit_text(draw, str(entry.get("title", "Без названия")), _font(27, True), width - 300)
            draw.text((205, y + 33), title, font=_font(27, True), fill=WHITE, anchor="lm")

    footer_y = height - 92
    draw.line((96, footer_y - 18, width - 96, footer_y - 18), fill=CARD_EDGE, width=2)
    draw.text((width // 2, footer_y + 20), "@LIBRARY_ADASAN", font=_font(25), fill=MUTED, anchor="mm")
    output = io.BytesIO()
    img.convert("RGB").save(output, "PNG")
    return output.getvalue()

