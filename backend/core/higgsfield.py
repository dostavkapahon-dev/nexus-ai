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
# Запасной адрес: в документации и SDK встречаются оба хоста. Ошибиться хостом —
# это молчаливое «не работает», поэтому пробуем второй, а рабочий запоминаем.
FALLBACK_BASE = "https://api.higgsfield.ai"
_working_base: str = ""

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
    forced = os.getenv("HIGGSFIELD_API_BASE", "").strip()
    if forced:
        return forced.rstrip("/")
    return (_working_base or DEFAULT_BASE).rstrip("/")


def _bases() -> list[str]:
    """Адреса в порядке проверки. Явно заданный в окружении — единственный."""
    forced = os.getenv("HIGGSFIELD_API_BASE", "").strip()
    if forced:
        return [forced.rstrip("/")]
    if _working_base:
        return [_working_base] + [b for b in (DEFAULT_BASE, FALLBACK_BASE)
                                  if b != _working_base]
    return [DEFAULT_BASE, FALLBACK_BASE]


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

# Платформа принимает ключ и секрет только в виде UUID и отвечает на чужой
# формат 422 с текстом про uuid_parsing. Сырой JSON этой ошибки человеку ничего
# не говорит: он видит «отверг параметры» и идёт искать поломку в коде, хотя
# дело в значении переменной. Проверяем форму до запроса и называем причину.
_UUID_LEN = 36


def _looks_like_uuid(value: str) -> bool:
    v = (value or "").strip()
    if len(v) != _UUID_LEN or v.count("-") != 4:
        return False
    return all(c in "0123456789abcdefABCDEF-" for c in v)


def _what_is_it(value: str) -> str:
    """Подсказка, чем похоже вставленное значение. Пусто — узнать нечем.

    «Не тот формат» мало что даёт: человек уже вставил то, что нашёл в кабинете,
    и не понимает, что именно нашёл не то. Длинная hex-строка — это токен
    (у Higgsfield такой вид у MCP-токена), а не ключ платформы, и сказать об
    этом полезнее, чем повторить требование к формату.
    """
    v = (value or "").strip()
    if len(v) == 64 and all(c in "0123456789abcdefABCDEF" for c in v):
        # Подтверждено по кабинету: на странице api-keys выдаются две строки —
        # key (UUID) и secret (длинная hex-строка). Значит 64 hex в поле ключа
        # почти всегда означает, что половины переставлены, а не что вставлен
        # посторонний токен.
        return ("Похоже, это СЕКРЕТ: в кабинете Higgsfield секрет выглядит "
                "длинной строкой без дефисов, а ключ — как UUID. Проверьте, не "
                "переставлены ли значения местами.")
    if v.startswith(("sk-", "hf_", "Bearer ")):
        return "Похоже, это ключ другого сервиса."
    return ""


def key_problem() -> str:
    """Человеческое объяснение, почему пара ключей не подойдёт. Пусто — форма ок.

    Это проверка ФОРМЫ, а не годности: правильный по виду ключ всё ещё может
    быть просрочен или от другого аккаунта — это покажет живой запрос.
    """
    key, secret = _pair()
    if not key or not secret:
        return NO_KEY

    if key == secret:
        # Оба поля UUID и по форме безупречны, но это одно и то же значение —
        # платформа ответит «Invalid credentials», и человек будет искать
        # причину в самом ключе. Ключ и секрет выдаются парой и всегда разные.
        return ("HIGGSFIELD_API_KEY и HIGGSFIELD_SECRET содержат ОДНО И ТО ЖЕ "
                "значение. Это разные половины пары: в кабинете Higgsfield при "
                "создании ключа показываются два разных значения — key и secret.")

    key_ok, secret_ok = _looks_like_uuid(key), _looks_like_uuid(secret)
    if key_ok and secret_ok:
        return ""
    if secret_ok and not key_ok:
        return ("HIGGSFIELD_API_KEY не похож на ключ платформы, а "
                "HIGGSFIELD_SECRET похож — возможно, значения перепутаны местами. "
                "Ключ должен быть UUID из 36 символов вида "
                "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx, "
                f"а сейчас в нём {len(key)}.")
    if not key_ok:
        return ("HIGGSFIELD_API_KEY неверного формата: платформа ждёт UUID из "
                f"36 символов, а в переменной {len(key)}. " + _what_is_it(key)
                + " Ключ платформы берётся в личном кабинете Higgsfield, "
                "раздел API keys — там он показан как "
                "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx.")
    return ("HIGGSFIELD_SECRET неверного формата: ожидается UUID из 36 символов, "
            f"а в переменной {len(secret)}.")


def size_for(ratio: str) -> str:
    return SIZES.get((ratio or "").strip(), SIZES["9:16"])


def _error_text(status: int, data) -> str:
    """Понятная причина вместо дампа JSON.

    401/403/422 у Higgsfield означают три разные и очень конкретные вещи, и
    человеку надо сказать именно их, иначе он идёт менять не то.
    """
    detail = data.get("detail") if isinstance(data, dict) else None

    # Отдельный случай: платформа жалуется не на параметры генерации, а на сам
    # ключ в заголовке. Человеку это приходило как «отверг параметры (422)» с
    # куском JSON — и он шёл искать поломку в промпте, хотя дело в переменной.
    if isinstance(detail, list):
        for d in detail:
            if not isinstance(d, dict):
                continue
            loc = [str(x) for x in (d.get("loc") or [])]
            if "hf-api-key" in loc or "hf-secret" in loc:
                which = "HIGGSFIELD_API_KEY" if "hf-api-key" in loc else "HIGGSFIELD_SECRET"
                return (f"Higgsfield не принял {which}: платформа ждёт UUID из "
                        "36 символов вида xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx. "
                        "Возьмите значение в личном кабинете Higgsfield, "
                        "раздел API keys.")

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
    """Запускает задачу. Возвращает {'ok': True, 'job_id': ...} либо причину.

    Если первый адрес отвечает 404 или недоступен, пробуем второй: ошибиться
    хостом — это то же самое «не генерируется», только без объяснения.
    """
    global _working_base
    problem = key_problem()
    if problem:
        # Не тратим запрос и не показываем человеку сырой 422: причина известна.
        return {"ok": False, "error": problem}

    last = {"ok": False, "error": "Higgsfield не ответил"}
    for base in _bases():
        try:
            async with httpx.AsyncClient(timeout=60) as c:
                r = await c.post(f"{base}{path}", headers=_headers(),
                                 json={"params": params})
                try:
                    data = r.json()
                except Exception:
                    data = r.text[:300]
        except Exception as e:
            last = {"ok": False,
                    "error": f"Higgsfield недоступен ({base}): "
                             f"{type(e).__name__}: {str(e)[:150]}"}
            continue

        if r.status_code == 404:
            last = {"ok": False, "error": _error_text(404, f"{base}{path}")}
            continue                      # адрес не тот — пробуем следующий
        if r.status_code >= 400:
            return {"ok": False, "error": _error_text(r.status_code, data)}

        job_id = data.get("id") if isinstance(data, dict) else None
        if not job_id:
            return {"ok": False,
                    "error": f"Higgsfield не вернул id задачи: {str(data)[:200]}"}
        _working_base = base              # адрес рабочий — дальше идём сразу сюда
        return {"ok": True, "job_id": job_id, "base": base}

    return last


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
    верной парой ключ+секрет. Заодно определяем рабочий адрес API.
    """
    global _working_base
    problem = key_problem()
    if problem:
        return {"ok": False, "error": problem}
    last = {"ok": False, "error": "Higgsfield не ответил"}
    for base in _bases():
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.get(f"{base}/v1/text2image/soul-styles",
                                headers=_headers())
        except Exception as e:
            last = {"ok": False, "error": f"{type(e).__name__}: {str(e)[:150]}"}
            continue
        if r.status_code < 400:
            _working_base = base
            return {"ok": True, "detail": f"ключ принят ({base})", "base": base}
        if r.status_code == 404:
            last = {"ok": False, "error": _error_text(404, base)}
            continue
        return {"ok": False, "error": _error_text(r.status_code, r.text[:200])}
    return last


# Модели, которые реально существуют у Higgsfield по этому API.
MODELS = list(DOP_MODELS) + ["soul"]

# Каталог для выбора в интерфейсе. Раньше модели можно было выбрать только через
# MCP: без него меню отвечало «нет ни одной модели», хотя ключ работал.
# Каталог для выбора в интерфейсе. Здесь только модели REST-пути (`/v1/...`):
# это отдельная, более старая поверхность API, и её имена не совпадают с
# каталогом аккаунта, который отдаёт MCP. Поэтому список помечен явно — чтобы
# нельзя было спутать его с настоящим каталогом подписки.
CATALOG = {
    "image": [{"value": "soul", "label": "Soul (REST) — text2image"}],
    "video": [
        {"value": "dop-turbo", "label": "DoP Turbo (REST) — быстро"},
        {"value": "dop-standard", "label": "DoP Standard (REST) — качество"},
        {"value": "dop-lite", "label": "DoP Lite (REST) — дёшево"},
    ],
}


def catalog(kind: str = "image") -> list[dict]:
    """Модели REST-пути. `connected` = есть ключ и секрет, то есть выбор сработает."""
    ok = bool(credentials())
    return [{**m, "group": "Higgsfield REST", "connected": ok}
            for m in CATALOG.get(kind, [])]
