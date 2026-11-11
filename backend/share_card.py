"""Renders the shareable "what was here" card as a PNG: street name, one fact, the NVM mark.

Drawn server-side with Pillow so the result is identical on iOS, Android and the web preview, and so the
card can use the app's own fonts and the warm white / brown palette from design_guidelines.json.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = Path(__file__).parent / "fonts"
W, H = 1080, 1350  # Instagram portrait; also fine for WhatsApp
PAD = 88

# Same palette as frontend/src/theme.ts (light): surface, onSurface, brandPrimary, brand, muted, divider.
SURFACE = "#FDFBF7"
INK = "#2A241F"
BRAND_DARK = "#5A4634"
BRAND = "#8E735B"
MUTED = "#8C8177"
DIVIDER = "#E6DACB"
PANEL = "#F2EAE0"


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / name), size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        words, cur = para.split(), ""
        for w in words:
            trial = f"{cur} {w}".strip()
            if draw.textlength(trial, font=font) <= width or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
    return lines


def _fit(draw: ImageDraw.ImageDraw, text: str, font_name: str, max_size: int, min_size: int, width: int, max_lines: int) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """Shrink the type until the text fits in max_lines; clip with an ellipsis if even the smallest won't."""
    for size in range(max_size, min_size - 1, -4):
        font = _font(font_name, size)
        lines = _wrap(draw, text, font, width)
        if len(lines) <= max_lines:
            return font, lines
    font = _font(font_name, min_size)
    lines = _wrap(draw, text, font, width)[:max_lines]
    last = lines[-1]
    while draw.textlength(last + "…", font=font) > width and len(last) > 1:
        last = last[:-1].rstrip()
    lines[-1] = last + "…"
    return font, lines


def _text_block(draw: ImageDraw.ImageDraw, x: int, y: int, lines: list[str], font: ImageFont.FreeTypeFont, fill: str, leading: float = 1.22) -> int:
    step = int(font.size * leading)
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += step
    return y


def render_card(title: str, subtitle: str, era_label: str, fact: str, source_note: str) -> bytes:
    img = Image.new("RGB", (W, H), SURFACE)
    d = ImageDraw.Draw(img)
    content_w = W - 2 * PAD

    # Top: wordmark and kicker
    d.rectangle([0, 0, W, 14], fill=BRAND_DARK)
    d.text((PAD, 72), "N V M", font=_font("PlayfairDisplay-Bold.ttf", 40), fill=BRAND_DARK)
    kicker_font = _font("DMSans-Bold.ttf", 24)
    kicker = "W H A T   W A S   H E R E"
    d.text((W - PAD - d.textlength(kicker, font=kicker_font), 82), kicker, font=kicker_font, fill=BRAND)

    # Street name
    y = 180
    title_font, title_lines = _fit(d, title, "PlayfairDisplay-Bold.ttf", 96, 56, content_w, 3)
    y = _text_block(d, PAD, y, title_lines, title_font, INK, 1.1)
    if subtitle:
        sub_font, sub_lines = _fit(d, subtitle, "DMSans-Regular.ttf", 32, 26, content_w, 2)
        y = _text_block(d, PAD, y + 12, sub_lines, sub_font, MUTED)

    # Fact panel, sized to its text (bigger type for short facts, smaller for long ones)
    panel_top = y + 56
    inner_x = PAD + 56
    inner_w = content_w - 56 - 48
    footer_top = H - 250
    max_panel_h = footer_top - 40 - panel_top
    label_h = 56 if era_label else 0
    avail_h = max_panel_h - 96 - label_h
    quoted = f"“{fact}”"
    fact_font, fact_lines = _fit(d, quoted, "PlayfairDisplay-Medium.ttf", 64, 34, inner_w, 12)
    while len(fact_lines) * int(fact_font.size * 1.3) > avail_h and fact_font.size > 34:
        fact_font = _font("PlayfairDisplay-Medium.ttf", fact_font.size - 4)
        fact_lines = _wrap(d, quoted, fact_font, inner_w)
    text_h = len(fact_lines) * int(fact_font.size * 1.3)
    panel_bottom = min(footer_top - 40, panel_top + 96 + label_h + text_h)
    d.rounded_rectangle([PAD, panel_top, W - PAD, panel_bottom], radius=28, fill=PANEL)
    d.rectangle([PAD, panel_top + 28, PAD + 8, panel_bottom - 28], fill=BRAND)
    fy = panel_top + 48
    if era_label:
        d.text((inner_x, fy), era_label.upper(), font=_font("DMSans-Bold.ttf", 24), fill=BRAND)
        fy += label_h
    _text_block(d, inner_x, fy, fact_lines, fact_font, INK, 1.3)

    # Footer
    d.line([PAD, footer_top, W - PAD, footer_top], fill=DIVIDER, width=3)
    d.text((PAD, footer_top + 36), source_note, font=_font("DMSans-Regular.ttf", 26), fill=MUTED)
    mark_font = _font("PlayfairDisplay-Bold.ttf", 34)
    mark = "NVM · Nevermind"
    d.text((W - PAD - d.textlength(mark, font=mark_font), footer_top + 28), mark, font=mark_font, fill=BRAND_DARK)
    d.text((PAD, footer_top + 100), "Point your camera at any street in India", font=_font("DMSans-Medium.ttf", 30), fill=INK)
    d.text((PAD, footer_top + 146), "and see what stood there through the centuries.", font=_font("DMSans-Regular.ttf", 30), fill=MUTED)

    import io

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
