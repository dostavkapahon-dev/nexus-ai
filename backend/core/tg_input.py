"""
Приём голосовых сообщений и медиа из Telegram (Stage 2A мастер-ТЗ).

• Голос  → скачиваем .ogg → распознаём (Gemini audio, бесплатно) → текст
           дальше обрабатывается как обычное сообщение/команда.
• Фото/видео → сохраняем как референс + сразу разбираем зрением.
• Аудио/шрифты → кладём в библиотеку (музыка) или в ассеты бренда.

Всё бесплатно: распознавание через тот же ключ Gemini, что уже используется.
"""
import os
import tempfile

import httpx

ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "assets")


def _token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "")


async def download_file(file_id: str, suffix: str = "") -> str | None:
    """Скачивает файл Telegram по file_id во временный путь."""
    token = _token()
    if not token or not file_id:
        return None
    try:
        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.get(f"https://api.telegram.org/bot{token}/getFile",
                            params={"file_id": file_id})
            d = r.json()
            if not d.get("ok"):
                return None
            path = d["result"]["file_path"]
            fr = await c.get(f"https://api.telegram.org/file/bot{token}/{path}")
            fr.raise_for_status()
        dst = os.path.join(tempfile.mkdtemp(prefix="nx_tg_"),
                           f"file{suffix or os.path.splitext(path)[1] or '.bin'}")
        with open(dst, "wb") as f:
            f.write(fr.content)
        return dst
    except Exception:
        return None


async def transcribe(audio_path: str) -> str:
    """Распознаёт речь. Gemini (бесплатно) → OpenAI Whisper, если есть ключ."""
    if not audio_path or not os.path.exists(audio_path):
        return ""

    if os.getenv("GEMINI_API_KEY"):
        try:
            import asyncio
            import google.generativeai as genai
            from core.ai_router import resolve_gemini_model
            genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
            model_name = resolve_gemini_model() or "gemini-2.0-flash"
            model = genai.GenerativeModel(model_name)
            with open(audio_path, "rb") as f:
                data = f.read()
            resp = await asyncio.to_thread(
                model.generate_content,
                ["Расшифруй речь из аудио дословно. Верни ТОЛЬКО текст, без пояснений.",
                 {"mime_type": "audio/ogg", "data": data}],
            )
            txt = (resp.text or "").strip()
            if txt:
                return txt
        except Exception:
            pass

    if os.getenv("OPENAI_API_KEY"):
        try:
            import openai
            client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            with open(audio_path, "rb") as f:
                tr = await client.audio.transcriptions.create(model="whisper-1", file=f)
            return (tr.text or "").strip()
        except Exception:
            pass
    return ""


def save_asset(src: str, kind: str = "reference") -> str | None:
    """Кладёт файл в постоянную папку ассетов бренда."""
    if not src or not os.path.exists(src):
        return None
    folder = os.path.join(ASSETS_DIR, kind)
    os.makedirs(folder, exist_ok=True)
    dst = os.path.join(folder, os.path.basename(src))
    try:
        with open(src, "rb") as a, open(dst, "wb") as b:
            b.write(a.read())
        return dst
    except Exception:
        return None


async def handle_media(msg: dict) -> dict:
    """Разбирает входящее медиа. Возвращает {kind, text, path, analysis}."""
    # Голос / аудио-сообщение
    voice = msg.get("voice") or msg.get("audio")
    if voice:
        p = await download_file(voice.get("file_id"), ".ogg")
        text = await transcribe(p) if p else ""
        # Музыкальный трек (не голосовое) — в библиотеку
        if msg.get("audio") and not msg.get("voice"):
            saved = save_asset(p, "music") if p else None
            return {"kind": "audio", "path": saved, "text": text}
        return {"kind": "voice", "text": text, "path": p}

    # Фото
    photos = msg.get("photo")
    if photos:
        best = photos[-1]  # самое большое
        p = await download_file(best.get("file_id"), ".jpg")
        saved = save_asset(p, "reference") if p else None
        return {"kind": "photo", "path": saved or p}

    # Видео / документ (шрифт, клип, что угодно)
    doc = msg.get("video") or msg.get("document")
    if doc:
        name = doc.get("file_name", "")
        suffix = os.path.splitext(name)[1] or (".mp4" if msg.get("video") else "")
        p = await download_file(doc.get("file_id"), suffix)
        kind = "font" if suffix.lower() in (".ttf", ".otf") else \
               ("video" if msg.get("video") or suffix.lower() in (".mp4", ".mov") else "document")
        saved = save_asset(p, "fonts" if kind == "font" else "reference") if p else None
        return {"kind": kind, "path": saved or p, "name": name}

    return {}
