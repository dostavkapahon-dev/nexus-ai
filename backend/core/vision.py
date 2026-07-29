"""
Зрение агента — анализ картинок и роликов vision-моделью.

Картинку отдаём модели по URL; ролик — вырезаем несколько кадров через ffmpeg
и отдаём их как последовательность изображений (базовый разбор видео).

Провайдеры (по наличию ключа):
  • OpenAI GPT-4o (vision) — основной, принимает image_url;
  • Anthropic Claude (vision) — запасной, через base64.

Возвращаем текстовый разбор: хук, что в кадре, монтаж, что улучшить.
"""
import os
import base64
import asyncio
import tempfile

import httpx

DEFAULT_Q = (
    "Ты эксперт по вирусным Reels/TikTok. Разбери это как креатив: "
    "1) сильный ли визуальный хук в первом кадре; 2) что в кадре, стиль, качество; "
    "3) удержание/динамика; 4) 3 конкретных улучшения. Коротко, по пунктам, по-русски."
)


def _openai_key():
    return os.getenv("OPENAI_API_KEY", "")


def _anthropic_key():
    return os.getenv("ANTHROPIC_API_KEY", "")


def _gemini_key():
    return os.getenv("GEMINI_API_KEY", "")


async def _gemini_vision(image_paths: list, question: str) -> str:
    """Зрение через Gemini — бесплатный вариант, не требует OpenAI."""
    import google.generativeai as genai
    genai.configure(api_key=_gemini_key())
    model = genai.GenerativeModel(os.getenv("NEXUS_VISION_GEMINI_MODEL", "gemini-2.0-flash"))
    parts = [question]
    for p in image_paths:
        with open(p, "rb") as f:
            parts.append({"mime_type": "image/png", "data": f.read()})
    resp = await asyncio.to_thread(model.generate_content, parts)
    return resp.text


async def _download(url: str) -> str | None:
    if not url or not url.startswith("http"):
        return url if (url and os.path.exists(url)) else None
    try:
        async with httpx.AsyncClient(timeout=90, follow_redirects=True) as c:
            r = await c.get(url)
            r.raise_for_status()
        p = os.path.join(tempfile.mkdtemp(prefix="nx_vis_"), "media")
        with open(p, "wb") as f:
            f.write(r.content)
        return p
    except Exception:
        return None


def _extract_frames(video_path: str, n: int = 3) -> list[str]:
    """Вырезает n кадров из видео через ffmpeg → список путей к png."""
    from core.video_assembly import _ffmpeg, _run
    ff = _ffmpeg()
    if not ff or not video_path or not os.path.exists(video_path):
        return []
    work = tempfile.mkdtemp(prefix="nx_frames_")
    # Равномерно по времени: fps низкий + берём первые n.
    out_pat = os.path.join(work, "fr_%02d.png")
    _run([ff, "-y", "-i", video_path, "-vf", "fps=1/2,scale=512:-1", "-frames:v", str(n), out_pat])
    frames = []
    for i in range(1, n + 1):
        p = os.path.join(work, f"fr_{i:02d}.png")
        if os.path.exists(p):
            frames.append(p)
    return frames


def _b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


async def _openai_vision(image_refs: list, question: str) -> str:
    """image_refs: список либо http-url, либо локальных путей к png."""
    import openai
    client = openai.AsyncOpenAI(api_key=_openai_key())
    content = [{"type": "text", "text": question}]
    for ref in image_refs:
        if isinstance(ref, str) and ref.startswith("http"):
            content.append({"type": "image_url", "image_url": {"url": ref}})
        else:
            content.append({"type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{_b64(ref)}"}})
    resp = await client.chat.completions.create(
        model="gpt-4o", max_tokens=700,
        messages=[{"role": "user", "content": content}],
    )
    return resp.choices[0].message.content


async def _anthropic_vision(image_paths: list, question: str) -> str:
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=_anthropic_key())
    blocks = [{"type": "text", "text": question}]
    for p in image_paths:
        blocks.append({"type": "image", "source": {
            "type": "base64", "media_type": "image/png", "data": _b64(p)}})
    msg = await client.messages.create(
        model="claude-sonnet-4-20250514", max_tokens=700,
        messages=[{"role": "user", "content": blocks}],
    )
    return msg.content[0].text


async def analyze_image(url: str, question: str = None) -> dict:
    """Разбор одной картинки. Провайдеры по наличию ключа: OpenAI → Gemini → Anthropic."""
    q = question or DEFAULT_Q
    err = "не задан ни один ключ (GEMINI_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY)"

    if _openai_key():
        try:
            return {"ok": True, "analysis": await _openai_vision([url], q)}
        except Exception as e:
            err = f"OpenAI: {str(e)[:120]}"

    # Gemini и Anthropic работают с локальным файлом.
    local = await _download(url) if (_gemini_key() or _anthropic_key()) else None
    if local and _gemini_key():
        try:
            return {"ok": True, "analysis": await _gemini_vision([local], q)}
        except Exception as e:
            err = f"Gemini: {str(e)[:120]}"
    if local and _anthropic_key():
        try:
            return {"ok": True, "analysis": await _anthropic_vision([local], q)}
        except Exception as e:
            err = f"Anthropic: {str(e)[:120]}"
    return {"ok": False, "error": f"Vision недоступен: {err}"}


async def analyze_video(url: str, question: str = None, frames: int = 3) -> dict:
    """Базовый разбор ролика: вырезаем кадры и анализируем их как раскадровку."""
    q = (question or DEFAULT_Q) + f"\n(Это {frames} кадра из ролика по порядку.)"
    local = await _download(url)
    if not local:
        return {"ok": False, "error": "не удалось скачать видео"}
    imgs = await asyncio.to_thread(_extract_frames, local, frames)
    if not imgs:
        return {"ok": False, "error": "не удалось вырезать кадры (ffmpeg?)"}
    err = "не задан ни один ключ (GEMINI_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY)"
    if _openai_key():
        try:
            return {"ok": True, "analysis": await _openai_vision(imgs, q), "frames": len(imgs)}
        except Exception as e:
            err = f"OpenAI: {str(e)[:120]}"
    if _gemini_key():
        try:
            return {"ok": True, "analysis": await _gemini_vision(imgs, q), "frames": len(imgs)}
        except Exception as e:
            err = f"Gemini: {str(e)[:120]}"
    if _anthropic_key():
        try:
            return {"ok": True, "analysis": await _anthropic_vision(imgs, q), "frames": len(imgs)}
        except Exception as e:
            err = f"Anthropic: {str(e)[:120]}"
    return {"ok": False, "error": err}


async def analyze_media(url: str, question: str = None) -> dict:
    """Авто-выбор: видео → кадры, иначе картинка."""
    if url and str(url).lower().split("?")[0].endswith((".mp4", ".mov", ".webm")):
        return await analyze_video(url, question)
    return await analyze_image(url, question)
