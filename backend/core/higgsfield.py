"""
Higgsfield — генерация изображений (Soul) и видео (DoP) по официальному API.

Раньше этот модуль стучался в выдуманные адреса `/v1/text2video` и `/v1/jobs/{id}`
с заголовком `Bearer <ключ>`. Таких эндпоинтов у Higgsfield нет, поэтому REST-путь
не мог сработать ни при каких ключах — «не генерируется» было следствием именно
этого, а не настроек.

Как устроен настоящий API (сверено с официальным SDK @higgsfield/client):

  База      https://platform.higgsfield.ai
  Доступ    заголовки hf-api-key / hf-secret (v1), плюс Authorization: Key k:s (v2)
  Картинка  POST /v1/text2image/soul     {"params": {prompt, width_and_height, ...}}
  Видео     POST /v1/image2video/dop     {"params": {model, prompt, input_images}}
  Ожидание  GET  /v1/job-sets/{id}       jobs[].status → results.raw.url

Важное свойство платформы: DoP — это image2video, ему нужен исходный кадр. Поэтому
видео «из текста» делается в два шага: Soul рисует кадр, DoP его оживляет. Это не
обход, а штатный путь Higgsfield.

Ключ и секрет берутся из HIGGSFIELD_API_KEY + HIGGSFIELD_SECRET либо из принятых
в SDK имён HF_API_KEY + HF_SECRET / HF_KEY="ключ:секрет".
"""
import os
import asyncio
import httpx

DEFAULT_BASE = "https://platform.higgsfield.ai"

# Пути официального API. Вынесены в константы, чтобы их нельзя было «подправить»
# наугад: каждый проверен по SDK.
PATH_IMAGE = "/v1/text2image/soul"
PATH_VIDEO = "/v1/image2video/dop"
PATH_JOBSET = "/v1/job-sets/{id}"

# Размеры кадра Soul: платформа принимает только этот список значений, поэтому
# соотношение сторон переводим в разрешение, а не шлём «9:16».
SIZES = {
    "9:16": "1152x2048",
    "16:9": "2048x1152",
    "1:1": "1536x1536",
    "4:5": "1152x1536",
    "3:4": "1152x1536",
}

DOP_MODELS = ("dop-lite", "dop-turbo", "dop-standard")


def _base() -> str:
    return os.getenv("HIGGSFIELD_API_BASE", DEFAULT_BASE).rstrip("/")


def _pair() -> tuple[str, str]:
    """Ключ и секрет по отдельности. Пустой ключ — доступ не настроен."""
    raw = os.getenv("HF_KEY", "").strip()
    if raw and ":" in raw:
        key, _, secret = raw.partition(":")
        return key.strip(), secret.strip()
    key = (os.getenv("HIGGSFIELD_API_KEY") or os.getenv("HF_API_KEY") or "").strip()
    secret = (os.getenv("HIGGSFIELD_SECRET") or os.getenv("HF_API_SECRET")
              or os.getenv("HF_SECRET") or "").strip()
    if ":" in key:                      # ключ вставили уже парой
        key, _, tail = key.partition(":")
        secret = secret or tail.strip()
    return key.strip(), secret


def credentials() -> str:
    """Пара «ключ:секрет» или пустая строка.

    Один ключ без секрета — заведомо отклонённый запрос, поэтому доступом его не
    считаем: лучше сразу сказать, чего не хватает, чем ловить 401 на генерации.
    """
    key, secret = _pair()
    if not key or not secret:
        return ""
    return f"{key}:{secret}"


def _headers() -> dict:
    """Оба варианта авторизации сразу: v1 читает hf-*, v2 — Authorization.

    Лишний заголовок безвреден, а угадывать версию по адресу — источник тех же
    молчаливых отказов, из-за которых генерация не работала.
    """
    key, secret = _pair()
    return {"hf-api-key": key, "hf-secret": secret,
            "Authorization": f"Key {key}:{secret}",
            "Content-Type": "application/json"}


NO_KEY = ("Нужны HIGGSFIELD_API_KEY и HIGGSFIELD_SECRET "
          "(ключ и секрет из cloud.higgsfield.ai)")


def size_for(ratio: str) -> str:
    return SIZES.get((ratio or "").strip(), SIZES["9:16"])


def _error_text(status: int, data) -> str:
    """Понятная причина вместо дампа JSON.

    401/403/422 у Higgsfield означают три разные и очень конкретные вещи, и
    человеку надо сказать именно их, иначе он идёт менять не то.
    """
    detail = data.get("detail") if isinstance(data, dict) else None
    if isinstance(detail, list) and detail:
        detail = "; ".join(str(d.get("msg") or d) for d in detail[:3])
    detail = str(detail or data)[:300]
    if status == 401:
        return f"Higgsfield не принял ключ (401). Проверьте ключ и секрет. {detail}"
    if status == 403:
        return f"Higgsfield: не хватает кредитов или доступа (403). {detail}"
    if status == 404:
        return f"Higgsfield: адрес {detail} не найден (404) — проверьте HIGGSFIELD_API_BASE"
    if status == 422:
        return f"Higgsfield отверг параметры (422): {detail}"
    return f"Higgsfield вернул {status}: {detail}"


async def _post(path: str, params: dict) -> dict:
    """Запускает задачу. Возвращает {'ok': True, 'job_id': ...} либо причину."""
    if not credentials():
        return {"ok": False, "error": NO_KEY}
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(f"{_base()}{path}", headers=_headers(),
                             json={"params": params})
            try:
                data = r.json()
            except Exception:
                data = r.text[:300]
            if r.status_code >= 400:
                return {"ok": False, "error": _error_text(r.status_code, data)}
    except Exception as e:
        return {"ok": False, "error": f"Higgsfield недоступен: {type(e).__name__}: {str(e)[:200]}"}

    job_id = (data or {}).get("id") if isinstance(data, dict) else None
    if not job_id:
        return {"ok": False, "error": f"Higgsfield не вернул id задачи: {str(data)[:200]}"}
    return {"ok": True, "job_id": job_id}


def _job_url(job: dict) -> str:
    res = job.get("results") or {}
    for key in ("raw", "min"):
        url = (res.get(key) or {}).get("url") if isinstance(res.get(key), dict) else None
        if url:
            return url
    return ""


async def poll_job(job_id: str, attempts: int = 60, delay: float = 5) -> dict:
    """Ждёт готовности набора задач. Возвращает {'ok': True, 'url': ...}."""
    if not credentials() or not job_id:
        return {"ok": False, "error": "нет доступа Higgsfield или id задачи"}
    path = PATH_JOBSET.format(id=job_id)
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            for _ in range(attempts):
                r = await c.get(f"{_base()}{path}", headers=_headers())
                if r.status_code >= 500:
                    await asyncio.sleep(delay)      # временная ошибка платформы
                    continue
                data = r.json() if r.status_code < 400 else {}
                if r.status_code >= 400:
                    return {"ok": False, "error": _error_text(r.status_code, r.text[:200])}
                jobs = data.get("jobs") or []
                statuses = [(j.get("status") or "").lower() for j in jobs]
                if any(s == "completed" for s in statuses):
                    for j in jobs:
                        url = _job_url(j)
                        if url:
                            return {"ok": True, "url": url}
                    return {"ok": False, "error": "Higgsfield: задача готова, но без ссылки"}
                if any(s == "nsfw" for s in statuses):
                    return {"ok": False, "error": "Higgsfield отклонил запрос как небезопасный (nsfw)"}
                if statuses and all(s in ("failed", "canceled") for s in statuses):
                    return {"ok": False, "error": "Higgsfield: генерация не удалась"}
                await asyncio.sleep(delay)
        return {"ok": False, "error": "Higgsfield не ответил вовремя"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}


# Совместимость со старым именем (его зовёт core/hixiit.py).
poll_video = poll_job


async def create_image(prompt: str, ratio: str = "9:16", quality: str = "1080p") -> dict:
    """Запускает генерацию картинки моделью Soul."""
    return await _post(PATH_IMAGE, {
        "prompt": (prompt or "")[:1000],
        "width_and_height": size_for(ratio),
        "quality": quality if quality in ("720p", "1080p") else "1080p",
        "batch_size": 1,
        "enhance_prompt": True,
    })


async def create_video(prompt: str, image_url: str = None, motion: str = "general",
                       ratio: str = "9:16", model: str = None) -> dict:
    """Запускает генерацию видео моделью DoP по исходному кадру.

    `motion` и `ratio` оставлены в сигнатуре ради совместимости с вызывающими
    модулями: DoP берёт соотношение сторон из самого кадра.
    """
    if not credentials():
        return {"ok": False, "error": NO_KEY}
    model = model or os.getenv("HIGGSFIELD_MODEL", "dop-turbo")
    if model not in DOP_MODELS:
        model = "dop-turbo"
    if not image_url:
        return {"ok": False, "error": "DoP оживляет готовый кадр — нужен image_url",
                "needs_image": True}
    return await _post(PATH_VIDEO, {
        "model": model,
        "prompt": (prompt or "")[:1000],
        "input_images": [{"type": "image_url", "image_url": image_url}],
    })


async def generate_image(prompt: str, ratio: str = "9:16") -> dict:
    """Картинка «под ключ»: запуск + ожидание."""
    started = await create_image(prompt, ratio)
    if not started.get("ok"):
        return started
    return await poll_job(started["job_id"])


async def generate_video(prompt: str, image_url: str = "", ratio: str = "9:16",
                         model: str = None) -> dict:
    """Видео «под ключ». Без исходного кадра сначала рисуем его моделью Soul —
    это штатный путь Higgsfield для «видео из текста»."""
    if not image_url:
        shot = await generate_image(prompt, ratio)
        if not shot.get("ok"):
            return {"ok": False, "error": f"кадр для видео не создан: {shot.get('error')}"}
        image_url = shot["url"]
    started = await create_video(prompt, image_url=image_url, ratio=ratio, model=model)
    if not started.get("ok"):
        return started
    done = await poll_job(started["job_id"])
    if done.get("ok"):
        done["preview_image"] = image_url
    return done


async def check() -> dict:
    """Живая проверка доступа: один настоящий запрос, а не «ключ есть».

    Спрашиваем список стилей Soul — это дешёвый GET, который проходит только с
    верной парой ключ+секрет.
    """
    if not credentials():
        return {"ok": False, "error": NO_KEY}
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(f"{_base()}/v1/text2image/soul-styles", headers=_headers())
        if r.status_code < 400:
            return {"ok": True, "detail": "ключ принят"}
        return {"ok": False, "error": _error_text(r.status_code, r.text[:200])}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}


# Модели, которые реально существуют у Higgsfield по этому API.
MODELS = list(DOP_MODELS) + ["soul"]
