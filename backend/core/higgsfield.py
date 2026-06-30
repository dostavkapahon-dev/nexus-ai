"""
HiggsField AI — генерация коротких кинематографичных видео из текста/изображения.
Сильна в динамичных «вирусных» роликах для Reels/TikTok/Shorts.
Требует HIGGSFIELD_API_KEY (и опц. HIGGSFIELD_SECRET).

Примечание: публичный API HiggsField развивается; эндпоинты вынесены в env,
чтобы можно было обновить без правки кода.
"""
import os
import asyncio
import httpx

DEFAULT_BASE = "https://platform.higgsfield.ai/v1"


def _base() -> str:
    return os.getenv("HIGGSFIELD_API_BASE", DEFAULT_BASE).rstrip("/")


def _headers() -> dict:
    api_key = os.getenv("HIGGSFIELD_API_KEY", "")
    h = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    secret = os.getenv("HIGGSFIELD_SECRET", "")
    if secret:
        h["hf-secret"] = secret
    return h


# Популярные модели HiggsField (значения можно переопределить через UI/env).
MODELS = [
    "higgsfield-dop",      # кинематографичная камера (DoP)
    "higgsfield-soul",     # реалистичные персонажи
    "higgsfield-turbo",    # быстрая генерация
    "kling-2.1",           # Kling
    "minimax-hailuo",      # MiniMax / Hailuo
    "seedance",            # Seedance
    "wan-2.2",             # Wan
    "veo-3",               # Google Veo (через HiggsField)
]


async def create_video(prompt: str, image_url: str = None, motion: str = "general",
                       ratio: str = "9:16", model: str = None) -> dict:
    """Запускает генерацию видео. Возвращает {'ok': True, 'job_id': ...}.

    model — конкретная AI-модель HiggsField (см. MODELS). По умолчанию берётся
    HIGGSFIELD_MODEL из настроек, иначе 'higgsfield-dop'.
    """
    if not os.getenv("HIGGSFIELD_API_KEY"):
        return {"ok": False, "error": "HIGGSFIELD_API_KEY not set"}
    model = model or os.getenv("HIGGSFIELD_MODEL", "higgsfield-dop")
    payload = {"prompt": prompt[:1000], "aspect_ratio": ratio, "motion": motion, "model": model}
    if image_url:
        payload["image_url"] = image_url
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{_base()}/text2video", headers=_headers(), json=payload)
            data = r.json()
            if r.status_code >= 400:
                return {"ok": False, "error": str(data)}
            return {"ok": True, "job_id": data.get("id") or data.get("job_id")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def poll_video(job_id: str, attempts: int = 30, delay: float = 10) -> dict:
    """Опрашивает статус задачи. Возвращает {'ok': True, 'url': ...} когда готово."""
    if not os.getenv("HIGGSFIELD_API_KEY") or not job_id:
        return {"ok": False, "error": "no api key or job_id"}
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            for _ in range(attempts):
                r = await c.get(f"{_base()}/jobs/{job_id}", headers=_headers())
                d = r.json()
                status = (d.get("status") or "").lower()
                if status in ("completed", "succeeded", "success"):
                    url = d.get("video_url") or (d.get("output") or {}).get("url")
                    return {"ok": True, "url": url}
                if status in ("failed", "error"):
                    return {"ok": False, "error": d.get("error", "generation failed")}
                await asyncio.sleep(delay)
        return {"ok": False, "error": "timeout waiting for HiggsField video"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# Модель HiggsField для генерации фото (Soul — реалистичные кадры).
IMAGE_MODEL_DEFAULT = "higgsfield-soul"


async def create_image(prompt: str, ratio: str = "1:1", model: str = None) -> dict:
    """Запускает генерацию фото (HiggsField Soul). Возвращает {'ok': True, 'job_id': ...}."""
    if not os.getenv("HIGGSFIELD_API_KEY"):
        return {"ok": False, "error": "HIGGSFIELD_API_KEY not set"}
    model = model or os.getenv("HIGGSFIELD_IMAGE_MODEL", IMAGE_MODEL_DEFAULT)
    path = os.getenv("HIGGSFIELD_IMAGE_PATH", "text2image")
    payload = {"prompt": prompt[:1000], "aspect_ratio": ratio, "model": model}
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{_base()}/{path}", headers=_headers(), json=payload)
            data = r.json()
            if r.status_code >= 400:
                return {"ok": False, "error": str(data)}
            return {"ok": True, "job_id": data.get("id") or data.get("job_id")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def poll_image(job_id: str, attempts: int = 30, delay: float = 5) -> dict:
    """Опрашивает статус фото-задачи. Возвращает {'ok': True, 'url': ...} когда готово."""
    if not os.getenv("HIGGSFIELD_API_KEY") or not job_id:
        return {"ok": False, "error": "no api key or job_id"}
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            for _ in range(attempts):
                r = await c.get(f"{_base()}/jobs/{job_id}", headers=_headers())
                d = r.json()
                status = (d.get("status") or "").lower()
                if status in ("completed", "succeeded", "success"):
                    out = d.get("output") or {}
                    url = (d.get("image_url") or out.get("url")
                           or (out.get("images") or [None])[0])
                    return {"ok": True, "url": url}
                if status in ("failed", "error"):
                    return {"ok": False, "error": d.get("error", "generation failed")}
                await asyncio.sleep(delay)
        return {"ok": False, "error": "timeout waiting for HiggsField image"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
