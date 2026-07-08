#!/usr/bin/env python3
"""Локальный рендер Reels без внешних сервисов и API-ключей.

Claude (мозг) пишет сториборд-JSON: хук, кадры, подписи. Этот скрипт только
рендерит: Pillow рисует вертикальные кадры 1080x1920 (градиент + типографика),
ffmpeg склеивает их в mp4 c плавным зумом (Ken Burns).

Использование:
    python tools/make_reel.py storyboard.json out.mp4

Формат storyboard.json:
{
  "frames": [
    {"title": "Крупный текст-хук", "sub": "подзаголовок", "dur": 3,
     "colors": ["#0f0c29", "#302b63"], "accent": "#ff2d78"}
  ],
  "cta": "Подпишись → @pakhon.studio",
  "brand": "PAKHON STUDIO"
}
"""
import json
import math
import os
import random
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920
FONT_DIRS = ["/usr/share/fonts", os.path.expanduser("~/.fonts")]


def _find_font(bold=True):
    names = (["DejaVuSans-Bold.ttf", "NotoSans-Bold.ttf", "LiberationSans-Bold.ttf"]
             if bold else ["DejaVuSans.ttf", "NotoSans-Regular.ttf", "LiberationSans-Regular.ttf"])
    for d in FONT_DIRS:
        for root, _, files in os.walk(d):
            for n in names:
                if n in files:
                    return os.path.join(root, n)
    return None


def font(size, bold=True):
    p = _find_font(bold)
    return ImageFont.truetype(p, size) if p else ImageFont.load_default()


def hex2rgb(s):
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def gradient(c1, c2, angle_seed=0):
    img = Image.new("RGB", (W, H))
    px = img.load()
    a, b = hex2rgb(c1), hex2rgb(c2)
    for y in range(H):
        t = y / H
        # лёгкая диагональная волна, чтобы фон не выглядел плоским
        for x in range(0, W, 4):
            tt = min(1, max(0, t + 0.08 * math.sin((x / W + angle_seed) * math.pi * 2)))
            col = tuple(int(a[i] + (b[i] - a[i]) * tt) for i in range(3))
            for dx in range(4):
                if x + dx < W:
                    px[x + dx, y] = col
    return img


def add_glow_shapes(img, accent, seed):
    rnd = random.Random(seed)
    layer = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(layer)
    ac = hex2rgb(accent)
    for _ in range(3):
        r = rnd.randint(180, 420)
        x, y = rnd.randint(-100, W), rnd.randint(-100, H)
        d.ellipse([x - r, y - r, x + r, y + r],
                  fill=tuple(int(c * 0.55) for c in ac))
    layer = layer.filter(ImageFilter.GaussianBlur(160))
    return Image.blend(img, Image.composite(layer, img, layer.convert("L")), 0.9)


def wrap(draw, text, fnt, max_w):
    words, lines, cur = text.split(), [], ""
    for w_ in words:
        t = (cur + " " + w_).strip()
        if draw.textlength(t, font=fnt) <= max_w:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w_
    if cur:
        lines.append(cur)
    return lines


def draw_text_block(img, title, sub, accent, brand):
    d = ImageDraw.Draw(img)
    pad = 90
    f_title = font(96)
    lines = wrap(d, title, f_title, W - 2 * pad)
    while len(lines) > 5 and f_title.size > 60:
        f_title = font(f_title.size - 8)
        lines = wrap(d, title, f_title, W - 2 * pad)
    lh = int(f_title.size * 1.18)
    total = len(lines) * lh
    y = (H - total) // 2 - 80

    # тень
    for i, ln in enumerate(lines):
        x = pad
        d.text((x + 5, y + i * lh + 5), ln, font=f_title, fill=(0, 0, 0))
        d.text((x, y + i * lh), ln, font=f_title, fill=(255, 255, 255))

    if sub:
        f_sub = font(52, bold=False)
        sl = wrap(d, sub, f_sub, W - 2 * pad)
        sy = y + total + 50
        for i, ln in enumerate(sl[:3]):
            d.text((pad + 3, sy + i * 66 + 3), ln, font=f_sub, fill=(0, 0, 0))
            d.text((pad, sy + i * 66), ln, font=f_sub, fill=hex2rgb(accent))

    # брендинг сверху и прогресс-полоска снизу
    fb = font(40)
    d.text((pad, 120), brand, font=fb, fill=(255, 255, 255, 200))
    d.rectangle([pad, 130 + 56, pad + 120, 130 + 62], fill=hex2rgb(accent))
    return img


def ffmpeg_exe():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def main():
    sb = json.load(open(sys.argv[1], encoding="utf-8"))
    out = sys.argv[2]
    ff = ffmpeg_exe()
    work = tempfile.mkdtemp(prefix="reel_")
    clips = []
    brand = sb.get("brand", "PAKHON STUDIO")

    frames = list(sb["frames"])
    if sb.get("cta"):
        frames.append({"title": sb["cta"], "sub": "", "dur": 3,
                       "colors": ["#000000", "#1a1a2e"],
                       "accent": frames[0].get("accent", "#ff2d78")})

    for i, fr in enumerate(frames):
        c1, c2 = fr.get("colors", ["#0f0c29", "#302b63"])
        accent = fr.get("accent", "#ff2d78")
        img = gradient(c1, c2, i * 0.37)
        img = add_glow_shapes(img, accent, i)
        img = draw_text_block(img, fr.get("title", ""), fr.get("sub", ""), accent, brand)
        png = os.path.join(work, f"f{i}.png")
        img.save(png)
        dur = int(fr.get("dur", 3))
        clip = os.path.join(work, f"c{i}.mp4")
        # Ken Burns: медленный зум 1.0 -> 1.07
        zf = f"zoompan=z='1+0.07*on/{dur * 30}':d={dur * 30}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps=30"
        r = subprocess.run([ff, "-y", "-loop", "1", "-t", str(dur), "-i", png,
                            "-vf", zf, "-pix_fmt", "yuv420p", clip],
                           capture_output=True, timeout=300)
        if r.returncode == 0:
            clips.append(clip)

    lst = os.path.join(work, "list.txt")
    with open(lst, "w") as f:
        for c in clips:
            f.write(f"file '{c}'\n")
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    r = subprocess.run([ff, "-y", "-f", "concat", "-safe", "0", "-i", lst,
                        "-c", "copy", out], capture_output=True, timeout=300)
    if r.returncode != 0 or not os.path.exists(out):
        sys.exit("ffmpeg concat failed: " + r.stderr.decode()[-400:])
    print("OK", out, os.path.getsize(out), "bytes")


if __name__ == "__main__":
    main()
