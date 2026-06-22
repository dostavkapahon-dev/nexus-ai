"""
VIDEO ASSEMBLY — сборка готового вертикального ролика (Pillow + ffmpeg).
=======================================================================
Текст-оверлеи рисуются через Pillow (надёжно, без зависимости от ffmpeg
drawtext/libfreetype), кадры приводятся к 1080x1920, ffmpeg только склеивает
кадры в mp4 и добавляет CTA-экран.

ffmpeg берётся из imageio-ffmpeg (бандл) или системный. Недоступен/ошибка —
возвращаем {ok: False, error} и не валим конвейер.
"""
import os
import shutil
import asyncio
import base64
import tempfile
import subprocess
from io import BytesIO
from datetime import date

import httpx
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def _ffmpeg() -> str | None:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _font(size: int) -> ImageFont.FreeTypeFont:
    for f in FONT_CANDIDATES:
        if os.path.exists(f):
            try:
                return ImageFont.truetype(f, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _dur(t: str) -> int:
    try:
        a, b = t.split("-")
        return max(2, min(int(float(b) - float(a)), 8))
    except Exception:
        return 3


async def _load_image(src: str) -> Image.Image | None:
    """Грузит картинку из data-URI или http(s)."""
    try:
        if src.startswith("data:"):
            raw = base64.b64decode(src.split(",", 1)[1])
            return Image.open(BytesIO(raw)).convert("RGB")
        async with httpx.AsyncClient(timeout=40, follow_redirects=True) as c:
            r = await c.get(src)
            if r.status_code == 200:
                return Image.open(BytesIO(r.content)).convert("RGB")
    except Exception:
        pass
    return None


def _cover_crop(img: Image.Image) -> Image.Image:
    """Масштаб с заполнением и кроп до 1080x1920."""
    src_ratio = img.width / img.height
    dst_ratio = W / H
    if src_ratio > dst_ratio:
        nh = H
        nw = int(H * src_ratio)
    else:
        nw = W
        nh = int(W / src_ratio)
    img = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - W) // 2
    top = (nh - H) // 2
    return img.crop((left, top, left + W, top + H))


def _wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _draw_overlay(img: Image.Image, text: str, size: int = 72, bottom: bool = False) -> Image.Image:
    """Рисует крупный текст в полупрозрачной плашке по центру (или снизу)."""
    if not text:
        return img
    draw = ImageDraw.Draw(img, "RGBA")
    font = _font(size)
    lines = _wrap(draw, text.upper(), font, W - 160)
    lh = size + 18
    block_h = lh * len(lines)
    y0 = (H - block_h) // 2 if not bottom else int(H * 0.74)
    pad = 28
    draw.rectangle([60, y0 - pad, W - 60, y0 + block_h + pad], fill=(10, 10, 10, 150))
    for i, ln in enumerate(lines):
        tw = draw.textlength(ln, font=font)
        x = (W - tw) / 2
        y = y0 + i * lh
        # обводка
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
            draw.text((x + dx, y + dy), ln, font=font, fill=(0, 0, 0, 255))
        draw.text((x, y), ln, font=font, fill=(255, 255, 255, 255))
    return img


def _run(args: list) -> bool:
    try:
        return subprocess.run(args, capture_output=True, timeout=180).returncode == 0
    except Exception:
        return False


async def assemble_slideshow(frames: list, cta_text: str = "Pakhon Studio",
                             out_dir: str = None) -> dict:
    """frames: [{'image': url|datauri, 'overlay': str, 't': '0-3'}] → {ok, path}."""
    ff = _ffmpeg()
    if not ff:
        return {"ok": False, "error": "ffmpeg недоступен"}
    if not frames:
        return {"ok": False, "error": "нет кадров"}

    base = os.path.dirname(os.path.dirname(__file__))
    out_dir = out_dir or os.path.join(base, "output", date.today().isoformat())
    os.makedirs(out_dir, exist_ok=True)
    work = tempfile.mkdtemp(prefix="nx_montage_")
    clips = []

    # 1. Кадры с запечённым текстом → клипы
    for i, fr in enumerate(frames[:6]):
        img = await _load_image(fr.get("image", ""))
        if img is None:
            continue
        img = _cover_crop(img)
        img = _draw_overlay(img, fr.get("overlay", ""), 72)
        png = os.path.join(work, f"f{i}.png")
        img.save(png)
        clip = os.path.join(work, f"c{i}.mp4")
        if await asyncio.to_thread(_run, [
            ff, "-y", "-loop", "1", "-t", str(_dur(fr.get("t", "0-3"))), "-i", png,
            "-r", "30", "-pix_fmt", "yuv420p", "-vf", "scale=1080:1920", clip,
        ]):
            clips.append(clip)

    if not clips:
        return {"ok": False, "error": "не удалось подготовить кадры (скачивание картинок?)"}

    # 2. CTA-экран (тёмный фон + призыв) через Pillow
    cta_img = Image.new("RGB", (W, H), (10, 10, 10))
    _draw_overlay(cta_img, cta_text, 80)
    cta_png = os.path.join(work, "cta.png")
    cta_img.save(cta_png)
    cta_clip = os.path.join(work, "cta.mp4")
    if await asyncio.to_thread(_run, [
        ff, "-y", "-loop", "1", "-t", "3", "-i", cta_png,
        "-r", "30", "-pix_fmt", "yuv420p", "-vf", "scale=1080:1920", cta_clip,
    ]):
        clips.append(cta_clip)

    # 3. Склейка
    listfile = os.path.join(work, "list.txt")
    with open(listfile, "w") as f:
        for c in clips:
            f.write(f"file '{c}'\n")
    out = os.path.join(out_dir, f"reel_{date.today().isoformat()}_{os.getpid()}.mp4")
    if not await asyncio.to_thread(_run, [
        ff, "-y", "-f", "concat", "-safe", "0", "-i", listfile, "-c", "copy", out,
    ]) or not os.path.exists(out):
        return {"ok": False, "error": "склейка не удалась"}
    return {"ok": True, "path": out, "provider": "ffmpeg_montage", "clips": len(clips)}
