"""
HiggsField AI — генерация коротких кинематографичных видео из текста/изображения.
Сильна в динамичных «вирусных» роликах для Reels/TikTok/Shorts.

Доступ: пара «ключ + секрет» из Higgsfield Cloud (https://cloud.higgsfield.ai).
Авторизация — заголовок `Authorization: Key <ключ>:<секрет>`. Раньше здесь стоял
`Bearer <ключ>` и отдельный заголовок `hf-secret`; такой запрос Higgsfield не
принимает, поэтому REST-путь не мог заработать ни при каких настройках.

Имена переменных: HIGGSFIELD_API_KEY + HIGGSFIELD_SECRET (как в остальном
проекте) либо HF_API_KEY + HF_API_SECRET / HF_KEY="ключ:секрет" — как в
официальном SDK. Эндпоинты вынесены в env, чтобы менять их без правки кода.
"""
import os
import asyncio
import httpx

DEFAULT_BASE = "https://platform.higgsfield.ai/v1"


def _base() -> str:
    return os.getenv("HIGGSFIELD_API_BASE", DEFAULT_BASE).rstrip("/")


def credentials() -> str:
    """Пара «ключ:секрет» для заголовка Authorization, либо пустая строка.

    Принимаем оба набора имён: свои (HIGGSFIELD_*) и принятые в SDK (HF_*),
    чтобы ключ, скопированный из документации Higgsfield, работал сразу.
    """
    pair = os.getenv("HF_KEY", "").strip()
    if pair:
        return pair
    key = (os.getenv("HIGGSFIELD_API_KEY") or os.getenv("HF_API_KEY") or "").strip()
    secret = (os.getenv("HIGGSFIELD_SECRET") or os.getenv("HF_API_SECRET") or "").strip()
    if not key:
        return ""
    # Ключ мог быть вставлен уже в виде «ключ:секрет» — второй раз не склеиваем.
    return key if ":" in key else (f"{key}:{secret}" if secret else "")


def _headers() -> dict:
    return {"Authorization": f"Key {credentials()}",
            "Content-Type": "application/json"}


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
    if not credentials():
        return {"ok": False, "error": "Нужны HIGGSFIELD_API_KEY и HIGGSFIELD_SECRET "
                                      "(ключ и секрет из cloud.higgsfield.ai)"}
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
    if not credentials() or not job_id:
        return {"ok": False, "error": "нет ключа Higgsfield или job_id"}
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
