"""
HiggsField AI — генерация изображений и коротких кинематографичных видео.
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

# ─────────────────────────── изображения ───────────────────────────

# Модели под изображения. Машинные имена — из каталога HiggsField; подбор под
# задачу нужен потому, что одна модель не хороша во всём: та, что чётко рисует
# текст на макете, дороже и медленнее там, где нужен просто черновик кадра.
IMAGE_MODELS = {
    "nano_banana_2":        "4K, текст в кадре, инфографика — максимальное качество",
    "nano_banana_flash":    "черновик и проверка композиции — дёшево и быстро",
    "marketing_studio_image": "товар и реклама, когда есть бренд-кит",
    "cinematic_studio_2_5": "киношный лук",
    "soul_2":               "узнаваемый персонаж (нужен обученный soul_id)",
    "seedream_v5_lite":     "лёгкая альтернатива для черновика",
}

DEFAULT_IMAGE_MODEL = "nano_banana_2"

# Признаки задачи → модель. Порядок важен: правила проверяются сверху вниз,
# первое совпавшее побеждает.
_TEXT_IN_FRAME = ("текст", "надпись", "заголовок", "инфограф", "макет", "титр",
                  "text", "caption", "headline", "infographic", "poster")
_PRODUCT = ("товар", "продукт", "реклама", "упаковк", "product", "packshot",
            "ad ", "advert")
_CINEMA = ("кинематограф", "киношн", "cinematic", "film still", "movie")


def pick_image_model(prompt: str, draft: bool = False,
                     soul_id: str | None = None) -> str:
    """Модель под конкретный кадр.

    Черновик намеренно идёт на дешёвую модель: смысл первой генерации —
    проверить композицию, а не получить финал. Платить полную цену за кадр,
    который увидит только автор, незачем.
    """
    if soul_id:
        return "soul_2"
    if draft:
        return "nano_banana_flash"
    low = (prompt or "").lower()
    if any(w in low for w in _TEXT_IN_FRAME):
        return "nano_banana_2"
    if any(w in low for w in _PRODUCT):
        return "marketing_studio_image"
    if any(w in low for w in _CINEMA):
        return "cinematic_studio_2_5"
    return os.getenv("HIGGSFIELD_IMAGE_MODEL", DEFAULT_IMAGE_MODEL)


async def create_image(prompt: str, ratio: str = "9:16", model: str | None = None,
                       draft: bool = False, soul_id: str | None = None,
                       reference_url: str | None = None) -> dict:
    """Генерация изображения. Возвращает {'ok', 'job_id', 'model'}.

    `reference_url` включает image-to-image: та же сцена правится, а не рисуется
    заново с нуля — иначе замечание «поменяй фон» приносит другого человека
    в другой одежде.
    """
    if not os.getenv("HIGGSFIELD_API_KEY"):
        return {"ok": False, "error": "HIGGSFIELD_API_KEY not set"}
    model = model or pick_image_model(prompt, draft=draft, soul_id=soul_id)
    payload = {"prompt": prompt[:2000], "aspect_ratio": ratio, "model": model}
    if soul_id:
        payload["soul_id"] = soul_id
    endpoint = "text2image"
    if reference_url:
        payload["image_url"] = reference_url
        endpoint = "image2image"
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{_base()}/{endpoint}", headers=_headers(), json=payload)
            data = r.json()
        if r.status_code >= 400:
            return {"ok": False, "error": str(data)[:300], "model": model}
        return {"ok": True, "job_id": data.get("id") or data.get("job_id"),
                "model": model}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}",
                "model": model}


async def poll_image(job_id: str, attempts: int = 20, delay: float = 5) -> dict:
    """Ждёт готовую картинку. Возвращает {'ok': True, 'url': ...}."""
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
                           or (out.get("images") or [{}])[0].get("url"))
                    if not url:
                        return {"ok": False, "error": "готово, но ссылки на картинку нет"}
                    return {"ok": True, "url": url}
                if status in ("failed", "error"):
                    return {"ok": False, "error": str(d.get("error", "generation failed"))[:200]}
                await asyncio.sleep(delay)
        return {"ok": False, "error": "HiggsField не отдал картинку за отведённое время"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}


async def image(prompt: str, ratio: str = "9:16", model: str | None = None,
                draft: bool = False, soul_id: str | None = None,
                reference_url: str | None = None) -> dict:
    """Запуск + ожидание одним вызовом: {'ok', 'url', 'model'} либо ошибка."""
    started = await create_image(prompt, ratio=ratio, model=model, draft=draft,
                                 soul_id=soul_id, reference_url=reference_url)
    if not started.get("ok"):
        return started
    done = await poll_image(started["job_id"])
    done["model"] = started.get("model")
    return done
