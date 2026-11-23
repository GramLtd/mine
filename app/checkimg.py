"""Картинка чека с суммой (как у кошельков в Telegram)."""
import io
import math
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ASSETS = Path(__file__).resolve().parent / "assets"
W, H = 1280, 720


def _font(name, size):
    return ImageFont.truetype(str(ASSETS / name), size)


def _ton_logo(d: ImageDraw.ImageDraw, cx, cy, r, fill, line):
    """Круг с ромбом-стрелкой (значок монеты)."""
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill)
    w, top, bot = r * 0.62, cy - r * 0.38, cy + r * 0.52
    pts = [(cx - w, top), (cx + w, top), (cx, bot)]
    d.line(pts + [pts[0]], fill=line, width=max(2, int(r * 0.13)), joint="curve")
    d.line([(cx, top), (cx, bot)], fill=line, width=max(2, int(r * 0.13)))


@lru_cache(maxsize=256)
def render(amount: str, coin: str, rub: str = "", n: int = 1) -> bytes:
    # фон: диагональный градиент
    img = Image.new("RGB", (W, H))
    c1, c2 = (0, 152, 234), (88, 70, 226)
    px = img.load()
    for y in range(H):
        for x in range(0, W, 4):
            t = (x / W * 0.65 + y / H * 0.35)
            col = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
            for k in range(4):
                px[x + k, y] = col
    # узор из полупрозрачных значков
    pat = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(pat)
    step = 150
    for row, y in enumerate(range(-40, H + step, step)):
        for x in range(-40 + (row % 2) * step // 2, W + step, step):
            _ton_logo(pd, x, y, 34, (255, 255, 255, 18), (255, 255, 255, 34))
    img = Image.alpha_composite(img.convert("RGBA"), pat)
    # мягкое свечение под суммой
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((W * .2, H * .18, W * .8, H * .82), fill=(255, 255, 255, 40))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(90)))
    d = ImageDraw.Draw(img)
    # сумма: подбираем размер, чтобы влезла
    size = 260
    while size > 90:
        f = _font("InterDisplay-ExtraBold.otf", size)
        if d.textlength(amount, font=f) <= W * 0.82:
            break
        size -= 10
    tw = d.textlength(amount, font=f)
    # тень
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).text(((W - tw) / 2, H * .44 + 8), amount, font=f, fill=(0, 0, 0, 70), anchor="lm")
    img = Image.alpha_composite(img, sh.filter(ImageFilter.GaussianBlur(12)))
    d = ImageDraw.Draw(img)
    d.text(((W - tw) / 2, H * .44), amount, font=f, fill=(255, 255, 255), anchor="lm")
    # подпись: значок + «1 TON» (+ ≈ ₽)
    sub = f"{amount} {coin}" + (f"  ×  {n}" if n > 1 else "") + (f"  ·  ≈ {rub} ₽" if rub and n == 1 else "")
    f2 = _font("Inter-SemiBold.otf", 58)
    sw = d.textlength(sub, font=f2)
    r = 30
    x0 = (W - (sw + r * 2 + 22)) / 2
    y = H * .44 + size * 0.62 + 40
    _ton_logo(d, x0 + r, y, r, (255, 255, 255, 235), (0, 136, 214))
    d.text((x0 + r * 2 + 22, y), sub, font=f2, fill=(255, 255, 255, 230), anchor="lm")
    out = io.BytesIO()
    img.convert("RGB").save(out, "JPEG", quality=88, optimize=True)
    return out.getvalue()


@lru_cache(maxsize=256)
def thumb(amount: str, coin: str) -> bytes:
    im = Image.open(io.BytesIO(render(amount, coin))).resize((320, 180))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=80)
    return out.getvalue()
