"""
HIXIIT — единый генеративный слой (Higgsfield).
==============================================
Одна точка входа для Cloud Opus: «вот задача — верни готовый медиа-результат».

HIXIIT сам:
  • понимает тип генерации (изображение или видео),
  • выбирает подходящую модель из РЕАЛЬНО доступных в аккаунте,
  • подбирает формат кадра,
  • возвращает ссылку на результат либо ВНЯТНУЮ причину отказа.

Пути доступа (сверху вниз, первый доступный побеждает):
  1. MCP    — рабочее подключение аккаунта (HIGGSFIELD_MCP_URL + HIGGSFIELD_MCP_TOKEN)
  2. REST   — прямой API по ключу HIGGSFIELD_API_KEY (core/higgsfield.py)
  3. Браузер — агент на ПК в залогиненном аккаунте (core/skills.py)
  4. Free   — бесплатная картинка Pollinations (только для изображений)

Молчаливых отказов быть не должно: каждый уровень объясняет, почему не сработал,
а `generate()` возвращает список попыток в поле 'tried'.
"""
import os
import json
import asyncio
import time

# Кэш каталога моделей: {(type, input): (timestamp, [models])}
_models_cache: dict = {}
_MODELS_TTL = 3600.0


# ── Определение типа задачи ───────────────────────────────────────────────────

_VIDEO_HINTS = (
    "видео", "ролик", "reels", "reel", "shorts", "tiktok", "клип", "анимац",
    "движен", "video", "animate", "motion", "сторис", "stories",
)


def detect_kind(task: str, explicit: str = "auto") -> str:
    """Тип генерации: 'video' или 'image'. explicit имеет приоритет."""
    if explicit in ("image", "video"):
        return explicit
    low = (task or "").lower()
    return "video" if any(h in low for h in _VIDEO_HINTS) else "image"


def detect_ratio(task: str, default: str = "9:16") -> str:
    """Формат кадра по формулировке задачи."""
    low = (task or "").lower()
    if any(h in low for h in ("16:9", "горизонт", "youtube", "landscape", "обложка канала")):
        return "16:9"
    if any(h in low for h in ("1:1", "квадрат", "square", "аватар")):
        return "1:1"
    return default


def _reraise_control_flow(e: BaseException) -> None:
    """Пропускает наружу отмену и остановку процесса, глушит всё остальное.

    Сломанные нативные зависимости (mcp → cryptography → pyo3) бросают
    PanicException, которая НЕ наследуется от Exception и проходит сквозь
    обычные except, унося с собой всю задачу. Ловить её приходится явно.
    """
    import asyncio as _a
    if isinstance(e, (_a.CancelledError, KeyboardInterrupt, SystemExit)):
        raise e


# ── MCP-путь ──────────────────────────────────────────────────────────────────

def mcp_configured() -> bool:
    return bool(os.getenv("HIGGSFIELD_MCP_URL"))


def _http_client_factory():
    """Клиент streamable HTTP из пакета mcp, как бы он ни назывался.

    Пакет переименовал функцию между версиями: `streamablehttp_client` →
    `streamable_http_client`. Код импортировал только старое имя, поэтому на
    сервере с более новым mcp путь падал с ImportError, и MCP молча выключался
    — а вместе с ним каталог моделей и безлимит. Версию пакета мы не выбираем
    (requirements допускает диапазон), поэтому принимаем оба имени.
    """
    import importlib
    mod = importlib.import_module("mcp.client.streamable_http")
    for name in ("streamablehttp_client", "streamable_http_client"):
        fn = getattr(mod, name, None)
        if fn is not None:
            return fn
    have = [n for n in dir(mod) if n.endswith("client")]
    raise ImportError(
        "в mcp.client.streamable_http нет ни streamablehttp_client, ни "
        f"streamable_http_client; есть: {', '.join(have) or '—'}")


async def _mcp_call(tool: str, args: dict, timeout: float = 600.0):
    """Один вызов инструмента на MCP-сервере Higgsfield.

    Возвращает распарсенный результат (dict/list/str) либо бросает исключение.
    Сессия создаётся на вызов — так проще и безопаснее в долгоживущем процессе.
    """
    url = os.getenv("HIGGSFIELD_MCP_URL", "")
    if not url:
        raise RuntimeError("HIGGSFIELD_MCP_URL не задан")

    # Импорт ленивый и защищённый: сломанная сборка mcp/cryptography роняет
    # интерпретатор через pyo3 PanicException, а она НЕ наследуется от Exception
    # и проходит сквозь обычные except — задача падала бы целиком.
    try:
        from mcp import ClientSession
        streamablehttp_client = _http_client_factory()
    except BaseException as e:
        raise RuntimeError(
            f"клиент mcp недоступен ({type(e).__name__}: {str(e)[:100]}); "
            "проверь установку пакета mcp") from None

    headers = {}
    token = os.getenv("HIGGSFIELD_MCP_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async def _run():
        # У новой версии пакета сменилась не только фамилия функции, но и то, как
        # ей передают заголовки: вместо `headers=` она принимает готовый
        # http-клиент. И отдаёт пару потоков вместо тройки. Поддерживаем оба
        # варианта, иначе MCP отваливается на каждом обновлении пакета.
        import inspect
        from contextlib import AsyncExitStack

        takes_headers = "headers" in inspect.signature(streamablehttp_client).parameters
        async with AsyncExitStack() as stack:
            if takes_headers:
                streams = await stack.enter_async_context(
                    streamablehttp_client(url, headers=headers or None))
            else:
                from mcp.client.streamable_http import create_mcp_http_client
                client = await stack.enter_async_context(
                    create_mcp_http_client(headers=headers or None))
                streams = await stack.enter_async_context(
                    streamablehttp_client(url, http_client=client))
            # Старая версия отдавала (read, write, get_session_id), новая — пару.
            read, write = streams[0], streams[1]
            async with ClientSession(read, write) as session:
                await session.initialize()
                res = await session.call_tool(tool, args)
                return _unwrap(res)

    return await asyncio.wait_for(_run(), timeout=timeout)


def _unwrap(res):
    """Достаёт полезную нагрузку из ответа MCP-инструмента."""
    if getattr(res, "isError", False):
        raise RuntimeError(_text_of(res) or "MCP tool error")
    data = getattr(res, "structuredContent", None)
    if data:
        return data
    text = _text_of(res)
    try:
        return json.loads(text)
    except Exception:
        return text


def _text_of(res) -> str:
    parts = []
    for block in getattr(res, "content", None) or []:
        t = getattr(block, "text", None)
        if t:
            parts.append(t)
    return "\n".join(parts)


async def pick_model(task: str, kind: str, has_reference: bool = False) -> dict:
    """Модель для генерации: ручной выбор пользователя → авто-подбор по каталогу.

    Раньше выбор был только автоматическим. Если человек указал модель явно,
    подбирать другую нельзя — он ждёт именно её.
    """
    manual = await preferred_model(kind)
    if manual:
        return {"id": manual, "name": manual}

    key = (kind, "image" if has_reference else "text")
    now = time.time()
    cached = _models_cache.get(key)
    if cached and now - cached[0] < _MODELS_TTL:
        models = cached[1]
    else:
        try:
            res = await _mcp_call("models_explore", {
                "action": "recommend",
                "query": (task or "")[:300],
                "type": kind,
                "input": "image" if has_reference else "text",
                "limit": 5,
            }, timeout=60)
        except BaseException as e:
            _reraise_control_flow(e)
            return {}
        models = _as_model_list(res, has_reference)
        if models:
            _models_cache[key] = (now, models)

    if not models:
        return {}
    preferred = os.getenv("HIGGSFIELD_MODEL", "")
    if preferred:
        for m in models:
            if preferred in (m.get("id", ""), m.get("name", "")):
                return m
    return models[0]


# Входы, которые HIXIIT умеет дать сам. Модель, требующая чего-то ещё
# (например YouTube-ссылку для Personal Clipper), для нашей задачи не годится.
_SUPPLIABLE = {"prompt", "text", "aspect_ratio", "ratio", "image_url", "image",
               "input_image", "duration", "model", "quality", "seed"}


def _model_is_usable(m: dict, has_reference: bool) -> bool:
    for prm in m.get("parameters") or []:
        if str(prm.get("required", "")).lower() != "required":
            continue
        name = prm.get("name", "")
        if name not in _SUPPLIABLE:
            return False
        if name in ("image_url", "image", "input_image") and not has_reference:
            return False
    return True


def _as_model_list(res, has_reference: bool = False) -> list:
    """Приводит ответ models_explore к списку пригодных моделей.

    Ответ приходит как {"items": [...]}; отбрасываем модели, которым нужен
    вход, которого у нас нет.
    """
    if isinstance(res, dict):
        for field in ("models", "items", "results", "data", "recommendations"):
            val = res.get(field)
            if isinstance(val, list):
                res = val
                break
        else:
            res = []
    if not isinstance(res, list):
        return []
    out = []
    for m in res:
        if not isinstance(m, dict):
            continue
        mid = m.get("id") or m.get("model_id") or m.get("model")
        if mid and _model_is_usable(m, has_reference):
            out.append({"id": mid, "name": m.get("name") or mid})
    return out


# ─────────────────────── экспертиза по моделям Higgsfield ───────────────────────
#
# Каталог сверен живым вызовом models_explore: у аккаунта существуют именно эти
# id. Раньше здесь стояли `soul` и `dop-*` из README старого SDK — таких моделей
# в каталоге нет, и выбор такой модели закончился бы отказом.
#
# Каждая строка — не «список ради списка», а правило «задача → модель»: дорогая
# модель на черновик тратит кредиты впустую, а дешёвая на финал портит результат.

IMAGE_MODELS = [
    {"value": "z_image", "label": "Z Image — быстрый черновик (дёшево)",
     "role": "draft"},
    {"value": "soul_2", "label": "Soul 2.0 — портреты, UGC, персонажи",
     "role": "person"},
    {"value": "gpt_image_2", "label": "GPT Image 2 — текст в кадре, 4K",
     "role": "text"},
    {"value": "cinematic_studio_2_5", "label": "Cinema Studio 2.5 — киношный кадр",
     "role": "cinematic"},
    {"value": "marketing_studio_image", "label": "Marketing Studio — товар, реклама",
     "role": "product"},
    {"value": "image_auto", "label": "Auto — платформа выбирает сама",
     "role": "auto"},
]

VIDEO_MODELS = [
    {"value": "minimax_hailuo", "label": "Minimax Hailuo — живая мимика, физика",
     "role": "person"},
    {"value": "cinematic_studio_3_0", "label": "Cinema Studio 3.0 — лучшее качество",
     "role": "cinematic"},
    {"value": "flux_3_video", "label": "FLUX 3 — видео из текста, со звуком",
     "role": "text2video"},
    {"value": "marketing_studio_video", "label": "Marketing Studio — реклама товара",
     "role": "product"},
    {"value": "wan2_6", "label": "Wan 2.6 — стилизованное, экспериментальное",
     "role": "stylized"},
]

# Слова задачи → нужная роль модели. Порядок важен: товар перевешивает «человека»,
# потому что реклама с человеком — всё равно реклама.
_ROLE_HINTS = (
    ("product", ("товар", "продукт", "реклам", "распродаж", "акци", "доставк",
                 "меню", "product", "ads")),
    ("text", ("текст", "надпись", "заголов", "инфограф", "цитат", "обложк с текст")),
    ("person", ("человек", "персонаж", "лицо", "портрет", "модель", "девушк",
                "парен", "ugc", "блогер")),
    ("cinematic", ("кино", "атмосфер", "драматич", "эпич", "cinematic")),
)


def role_for_task(task: str, kind: str, has_reference: bool = False) -> str:
    """Какая роль модели нужна этой задаче: товар, текст, человек, кино, черновик."""
    low = (task or "").lower()
    for role, words in _ROLE_HINTS:
        if any(w in low for w in words):
            return role
    if kind == "video":
        return "person" if has_reference else "text2video"
    return "person" if has_reference else "draft"


# Замены под безлимит. Безлимит выдаётся не на все модели, а на конкретные —
# и почти все наши штатные фото-модели (z_image, cinematic_studio_2_5,
# marketing_studio_image) в него НЕ входят. Без этой карты система с активным
# безлимитом всё равно списывала бы кредиты: роль подобрана верно, а модель
# оплачиваемая.
#
# Кандидаты и их назначение взяты из живого каталога аккаунта, а не придуманы:
#   nano_banana      — «realistic images, budget-friendly» → черновик
#   nano_banana_pro  — «ultimate quality, text and diagrams» → товар, реклама
#   soul_2           — «realistic UGC, character generation» → человек
#   gpt_image_2      — «text-rendering, typography, 4k» → текст в кадре
#   flux_2           — «precise prompt adherence» → сложный кинокадр
#   seedream_v4_5    — «4K output, precise control» → запасной вариант
_UNLIM_BY_ROLE = {
    "draft": ("nano_banana", "nano_banana_2", "seedream_v5_lite"),
    "person": ("soul_2", "soul_v2", "nano_banana_pro"),
    "text": ("gpt_image_2", "nano_banana_pro"),
    "cinematic": ("flux_2", "seedream_v4_5", "kling_omni_image"),
    "product": ("nano_banana_pro", "seedream_v4_5", "nano_banana_2"),
}


def unlim_swap(model_id: str, role: str, covered: list) -> str:
    """Модель, покрытая безлимитом, под ту же роль. Пусто — замены нет.

    Роль важнее модели: человеку нужен кадр нужного типа, а не конкретный id.
    Но подменять вслепую нельзя — берём только то, что безлимит реально
    покрывает, иначе платформа откажет вместо генерации.
    """
    if not covered or model_id in covered:
        return ""
    for candidate in _UNLIM_BY_ROLE.get(role, ()):
        if candidate in covered:
            return candidate
    return ""


def pick_by_task(task: str, kind: str, has_reference: bool = False) -> str:
    """Модель под задачу по правилам, когда каталог MCP недоступен.

    Это не «любая модель из списка»: неверный выбор либо жжёт кредиты, либо даёт
    негодный кадр. Правила взяты из рабочего пайплайна, а не придуманы.
    """
    low = (task or "").lower()
    models = VIDEO_MODELS if kind == "video" else IMAGE_MODELS
    by_role = {m["role"]: m["value"] for m in models}

    for role, words in _ROLE_HINTS:
        if any(w in low for w in words) and role in by_role:
            return by_role[role]

    if kind == "video":
        # Без исходного кадра нужна модель, умеющая text-to-video.
        return by_role["text2video"] if not has_reference else by_role["person"]
    return by_role["person"] if has_reference else by_role["draft"]


# Каждая модель понимает свой язык промпта. Один универсальный текст всем — это
# худший результат у всех сразу.
_PROMPT_STYLE = {
    "soul_2": "Focus on scene, wardrobe, action, lighting and composition; "
              "do not re-describe the face.",
    "gpt_image_2": "Spell out any on-image text exactly, name the font style, "
                   "state the layout.",
    "z_image": "Keep it short and concrete: subject, setting, light.",
    "cinematic_studio_2_5": "Describe it as a film still: lens, light direction, "
                            "colour grade, mood.",
    "cinematic_studio_3_0": "Write as a director: camera move, shot length, "
                            "colour grade, pacing.",
    "minimax_hailuo": "Describe motion and emotion — gestures, tempo; the "
                      "background comes from the source frame.",
    "flux_3_video": "Describe the scene, the camera move and the sound source.",
    "marketing_studio_image": "Think in brand terms: hook, setting, product.",
    "marketing_studio_video": "Think in brand terms: hook, setting, product, CTA.",
}


def prompt_for(model: str, prompt: str) -> str:
    """Промпт, адаптированный под конкретную модель.

    Модели лучше понимают английский, поэтому русский текст переводится слоем
    обогащения (`media_generator.enrich_image_prompt`) до этого места; здесь
    добавляется только то, что важно именно этой модели.
    """
    hint = _PROMPT_STYLE.get(model or "")
    text = (prompt or "").strip()
    return f"{text}\n\n{hint}" if hint else text


async def unlim_status() -> dict:
    """Есть ли безлимитные генерации и на какие модели.

    Безлимит — не то же самое, что подписка: он выдаётся отдельно и покрывает
    только часть моделей. Тратить его молча нельзя, но и не использовать, когда
    он есть, — значит зря списывать кредиты.
    """
    if not mcp_configured():
        return {"available": False, "reason": "MCP не настроен"}
    try:
        res = await _mcp_call("models_explore",
                              {"action": "list", "unlim": True, "limit": 50},
                              timeout=60)
    except BaseException as e:
        _reraise_control_flow(e)
        return {"available": False, "reason": f"{type(e).__name__}: {str(e)[:120]}"}
    block = (res or {}).get("unlim") or {}
    models = [m.get("id") for m in _as_model_list(res) if m.get("id")]
    out = {"available": bool(block.get("available")),
           "remaining": block.get("remaining"),
           "expires_at": block.get("expires_at"),
           "models": models}
    if not out["available"]:
        # Причина нужна всегда. Без неё «безлимита нет» выглядит одинаково с
        # «мы не проверяли», и человек считает, что генерации бесплатные, пока
        # они молча съедают кредиты. Модели могут заявлять supports_unlim, но
        # решает право аккаунта, а оно выдаётся отдельно и часто только на сайте.
        out["reason"] = ("платформа не выдала безлимит этому аккаунту — "
                         "генерации спишут кредиты")
    return out


async def _import_media(image_url: str) -> str | None:
    """Ссылка на картинку → media_id. MCP принимает только id, не URL."""
    try:
        res = await _mcp_call("media_import_url", {"url": image_url}, timeout=120)
    except BaseException as e:
        _reraise_control_flow(e)
        return None
    if isinstance(res, dict):
        for key in ("media_id", "id"):
            if res.get(key):
                return res[key]
        items = res.get("results") or res.get("medias") or []
        if items and isinstance(items[0], dict):
            return items[0].get("media_id") or items[0].get("id")
    return None


async def _wait_job(job_id: str, attempts: int = 40) -> str:
    """Ждёт готовности задачи. Генерация асинхронная: ответ на запрос — это
    заявка со статусом pending, а не готовое медиа."""
    for _ in range(attempts):
        res = await _mcp_call("jobs_wait",
                              {"jobs": [{"index": 0, "job_id": job_id}],
                               "timeout_seconds": 15}, timeout=60)
        jobs = (res or {}).get("jobs") or []
        job = jobs[0] if jobs else {}
        status = (job.get("status") or "").lower()
        if status == "completed":
            url = job.get("result_url") or _find_media_url(job)
            if url:
                return url
            raise RuntimeError("задача готова, но без ссылки на результат")
        if status in ("failed", "canceled", "nsfw"):
            raise RuntimeError(f"Higgsfield: задача завершилась статусом {status}")
        if (res or {}).get("all_terminal"):
            break
    raise RuntimeError("Higgsfield не отдал результат вовремя")


async def _generate_via_mcp(task: str, kind: str, ratio: str,
                            image_url: str = None) -> dict:
    """Генерация через MCP по фактическому протоколу платформы.

    Три вещи, без которых путь не работал: аргументы идут вложенными в `params`,
    результат приходит заявкой со статусом (её надо дождаться), а картинка-вход
    передаётся как media_id, а не ссылкой.
    """
    model = await pick_model(task, kind, has_reference=bool(image_url))
    model_id = model.get("id") or pick_by_task(task, kind, bool(image_url))
    tool = "generate_video" if kind == "video" else "generate_image"

    params = {"model": model_id, "prompt": prompt_for(model_id, task)[:1500],
              "aspect_ratio": ratio, "count": 1}

    # Безлимит тратим, только когда он есть и покрывает выбранную модель:
    # иначе платформа вернёт отказ вместо генерации.
    unlim = await unlim_status()
    swapped_from = ""
    if unlim.get("available"):
        covered = unlim.get("models") or []
        # Если безлимит не покрывает выбранную модель, пробуем равноценную по
        # роли из покрытых: иначе безлимит лежит без дела, а кредиты тратятся.
        alt = unlim_swap(model_id, role_for_task(task, kind, bool(image_url)), covered)
        if alt:
            swapped_from, model_id = model_id, alt
            params["model"] = model_id
            params["prompt"] = prompt_for(model_id, task)[:1500]
        params["use_unlim"] = bool(not covered or model_id in covered)
    else:
        params["use_unlim"] = False

    if image_url:
        media_id = await _import_media(image_url)
        if media_id:
            role = "start_image" if kind == "video" else "image"
            params["medias"] = [{"value": media_id, "role": role}]

    res = await _mcp_call(tool, {"params": params})

    # Готовая ссылка приходит редко (некоторые инструменты отвечают сразу) —
    # но обычно это заявка, и её надо дождаться.
    url = _find_media_url(res)
    if not url:
        results = (res or {}).get("results") or []
        job_id = results[0].get("id") if results and isinstance(results[0], dict) else None
        if not job_id:
            raise RuntimeError(f"MCP не вернул задачу: {str(res)[:300]}")
        url = await _wait_job(job_id)

    out = {"ok": True, "url": url, "provider": "higgsfield_mcp",
           "kind": kind, "model": model_id,
           "unlim": bool(params.get("use_unlim"))}
    if swapped_from:
        # Подмену модели не прячем: человек должен видеть, что кадр сделан
        # другой моделью — и почему.
        out["swapped_from"] = swapped_from
    return out


_URL_KEYS = ("video_url", "image_url", "url", "output_url", "result_url", "media_url", "download_url")


def _find_media_url(data, depth: int = 0):
    """Рекурсивно ищет первую ссылку на медиа в ответе любой формы."""
    if depth > 6:
        return None
    if isinstance(data, str):
        return data if data.startswith("http") and _looks_like_media(data) else None
    if isinstance(data, dict):
        for k in _URL_KEYS:
            v = data.get(k)
            if isinstance(v, str) and v.startswith("http"):
                return v
        for v in data.values():
            found = _find_media_url(v, depth + 1)
            if found:
                return found
        return None
    if isinstance(data, list):
        for v in data:
            found = _find_media_url(v, depth + 1)
            if found:
                return found
    return None


def _looks_like_media(url: str) -> bool:
    low = url.split("?")[0].lower()
    return low.endswith((".mp4", ".mov", ".webm", ".png", ".jpg", ".jpeg", ".webp", ".gif"))


# ── Главная точка входа ───────────────────────────────────────────────────────

# ─────────────────────── проверка до и после генерации ───────────────────────
#
# Генерация — самый дорогой шаг конвейера, и до сих пор он шёл вслепую: промпт
# уходил в модель как есть, а результат никто не смотрел. Обе проверки дешёвые
# (короткая модель + разбор картинки) и обе «не мешают»: при отсутствии ключей
# или сбое проверки генерация идёт как раньше, а не встаёт.

_PROMPT_CHECK = (
    "Ты режиссёр-постановщик. Оцени промпт для генеративной модели и почини его, "
    "если нужно. Верни JSON: {\"ok\": true|false, \"reason\": \"что не так\", "
    "\"prompt\": \"исправленный промпт\"}. Промпт должен: отвечать задаче, "
    "описывать композицию и свет конкретно, не противоречить сам себе. "
    "Если промпт годится — ok:true и верни его без изменений."
)


async def check_prompt(prompt: str, task: str, model: str, kind: str) -> dict:
    """Промпт перед отправкой в модель. Возвращает {ok, prompt, reason, checked}."""
    from core.ai_router import ai_available, ai_router, ECONOMY_MODELS
    if not ai_available():
        return {"ok": True, "prompt": prompt, "checked": False,
                "reason": "нет модели для проверки"}
    try:
        from core import ai_escrow
        with ai_escrow.suppressed():
            res = await ai_router.call(
                ECONOMY_MODELS.get("reviewer", "gemini-2.0-flash"), _PROMPT_CHECK,
                f"ЗАДАЧА: {task[:600]}\nМОДЕЛЬ: {model} ({kind})\n"
                f"ПРОМПТ:\n{prompt[:1500]}")
        text = res.get("text", "")
        data = json.loads(text[text.find("{"):text.rfind("}") + 1])
        fixed = (data.get("prompt") or "").strip() or prompt
        return {"ok": bool(data.get("ok", True)), "prompt": fixed,
                "reason": str(data.get("reason") or "")[:200], "checked": True}
    except BaseException as e:
        _reraise_control_flow(e)
        # Проверка — служебный шаг: её отказ не должен отменять генерацию.
        return {"ok": True, "prompt": prompt, "checked": False,
                "reason": f"{type(e).__name__}"}


async def check_result(url: str, task: str, kind: str) -> dict:
    """Готовый результат глазами модели. {ok, reason, checked}."""
    try:
        from core.vision import analyze_image, analyze_video
        fn = analyze_video if kind == "video" else analyze_image
        res = await fn(url, "Опиши кадр и ответь строкой ГОДНО или БРАК с причиной. "
                            f"Задача была: {task[:300]}")
    except BaseException as e:
        _reraise_control_flow(e)
        return {"ok": True, "checked": False, "reason": f"{type(e).__name__}"}
    if not res.get("ok"):
        return {"ok": True, "checked": False, "reason": str(res.get("error"))[:160]}
    text = (res.get("analysis") or "")
    bad = "БРАК" in text.upper()
    return {"ok": not bad, "checked": True, "reason": text[:300]}


async def generate(task: str, kind: str = "auto", ratio: str = None,
                   image_url: str = None, allow_free: bool = True,
                   qc: bool = True) -> dict:
    """Сгенерировать медиа с проверкой промпта до и результата после.

    Одна повторная попытка при браке: генерация — самый дорогой шаг, и цикл
    «не понравилось — ещё раз» без предела просто сжёг бы кредиты.

    {'ok': True, 'url', 'provider', 'kind', 'model'}
    {'ok': False, 'error': <человеческая причина>, 'tried': [...]}
    """
    kind_resolved = detect_kind(task, kind)
    if not qc:
        return await _generate_once(task, kind, ratio, image_url, allow_free)

    checked = await check_prompt(task, task, "auto", kind_resolved)
    prompt = checked.get("prompt") or task

    res = await _generate_once(prompt, kind, ratio, image_url, allow_free)
    if checked.get("checked"):
        res["prompt_check"] = checked.get("reason") or "промпт годится"
    if not res.get("ok") or not res.get("url"):
        return res

    verdict = await check_result(res["url"], task, res.get("kind", kind_resolved))
    res["qc"] = verdict
    if verdict.get("ok") or not verdict.get("checked"):
        return res

    # Брак: правим промпт по причине и пробуем ровно один раз ещё.
    again = await check_prompt(f"{prompt}\n\nИсправь: {verdict['reason'][:300]}",
                               task, res.get("model", "auto"), res.get("kind", kind_resolved))
    retry = await _generate_once(again.get("prompt") or prompt, kind, ratio,
                                 image_url, allow_free)
    if retry.get("ok"):
        retry["qc"] = {"ok": True, "checked": True,
                       "reason": f"перегенерация после брака: {verdict['reason'][:160]}"}
        retry["regenerated"] = True
        return retry
    res["qc_note"] = "результат не прошёл проверку, перегенерация не удалась"
    return res


async def _generate_once(task: str, kind: str = "auto", ratio: str = None,
                         image_url: str = None, allow_free: bool = True) -> dict:
    """Одна попытка генерации по цепочке путей. Никогда не бросает."""
    kind = detect_kind(task, kind)
    ratio = ratio or detect_ratio(task)
    tried = []

    # Тип генерации и формат определяем по ИСХОДНОМУ тексту — по-русски в нём и
    # написано «ролик» или «вертикально». А в саму модель уходит английское
    # описание: генеративные модели обучены на нём. Уже английский и подробный
    # запрос переписан не будет, поэтому двойной обработки не происходит.
    try:
        from core.media_generator import enrich_image_prompt
        task = await enrich_image_prompt(task)
    except Exception:
        pass

    # 1. MCP — основной рабочий путь
    if mcp_configured():
        try:
            return await _generate_via_mcp(task, kind, ratio, image_url)
        except BaseException as e:
            _reraise_control_flow(e)
            tried.append(f"MCP: {type(e).__name__}: {str(e)[:180]}")
    else:
        tried.append("MCP: не настроен (нет HIGGSFIELD_MCP_URL)")

    # 2. REST по ключу+секрету из Higgsfield Cloud.
    # Картинки идут сюда же: Soul умеет text2image, и раньше этот путь просто
    # отказывался их делать, из-за чего визуал уезжал на бесплатный Pollinations.
    from core.higgsfield import credentials as _hf_credentials
    if _hf_credentials():
        try:
            from core import higgsfield as hf
            # Ручной выбор пользователя важнее умолчаний: он выбрал модель и
            # ждёт именно её.
            chosen = await preferred_model(kind)
            if kind == "video":
                model = chosen if chosen in hf.DOP_MODELS else os.getenv(
                    "HIGGSFIELD_MODEL", "dop-turbo")
                done = await hf.generate_video(task, image_url=image_url or "",
                                               ratio=ratio, model=model)
            else:
                done = await hf.generate_image(task, ratio=ratio)
                model = "soul"
            if done.get("ok") and done.get("url"):
                out = {"ok": True, "url": done["url"], "provider": "higgsfield_api",
                       "kind": kind, "model": model}
                if done.get("preview_image"):
                    out["preview_image"] = done["preview_image"]
                return out
            tried.append(f"REST: {done.get('error', 'нет ссылки на результат')}")
        except BaseException as e:
            _reraise_control_flow(e)
            tried.append(f"REST: {type(e).__name__}: {str(e)[:200]}")
    else:
        tried.append("REST: не настроен (нужны HIGGSFIELD_API_KEY и HIGGSFIELD_SECRET)")

    # 3. Браузер-агент в залогиненном аккаунте (только видео)
    if kind == "video":
        try:
            from api.routes_desktop import desktop_connected
            if desktop_connected():
                from core.skills import higgsfield_via_browser
                res = await higgsfield_via_browser(task, image_url)
                if res.get("ok") and res.get("url"):
                    return {"ok": True, "url": res["url"], "provider": "higgsfield_browser",
                            "kind": "video", "model": "account"}
                tried.append(f"Браузер: {str(res.get('detail') or res.get('error'))[:200]}")
            else:
                tried.append("Браузер: агент на ПК не подключён")
        except Exception as e:
            tried.append(f"Браузер: {str(e)[:200]}")

    # 4. Бесплатная картинка — чтобы визуал был хоть какой-то
    if kind == "image" and allow_free:
        from core.skills import free_image
        return {"ok": True, "url": free_image(task, vertical=ratio != "16:9"),
                "provider": "pollinations_free", "kind": "image", "model": "free",
                "note": "HIXIIT недоступен, использован бесплатный генератор",
                "tried": tried}

    return {"ok": False, "kind": kind, "tried": tried,
            "error": "HIXIIT недоступен ни одним путём:\n• " + "\n• ".join(tried)}


# Выбранные пользователем модели HIXIIT. Хранятся там же, где остальное
# состояние системы (KV в таблице Connection), поэтому переживают перезапуск
# и не требуют миграции схемы.
PREF_KEYS = {"image": "hixiit_image_model", "video": "hixiit_video_model"}


async def preferred_model(kind: str) -> str:
    """Модель, выбранная пользователем для этого вида генерации. Пусто — «авто»."""
    key = PREF_KEYS.get(kind)
    if not key:
        return ""
    try:
        from sqlalchemy import select
        from database.db import AsyncSessionLocal
        from database.models import Connection
        async with AsyncSessionLocal() as db:
            r = await db.execute(select(Connection).where(Connection.key_name == key))
            row = r.scalar_one_or_none()
        return (row.key_value or "").strip() if row else ""
    except Exception:
        return ""


async def set_preferred_model(kind: str, value: str) -> bool:
    """Запоминает выбор модели. Пустое значение возвращает режим «авто»."""
    key = PREF_KEYS.get(kind)
    if not key:
        return False
    from sqlalchemy import select
    from database.db import AsyncSessionLocal
    from database.models import Connection
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Connection).where(Connection.key_name == key))
        row = r.scalar_one_or_none()
        if row:
            row.key_value = value
        else:
            db.add(Connection(key_name=key, key_value=value))
        await db.commit()
    return True


async def available_models(kind: str = "image") -> list[dict]:
    """Модели, из которых можно выбирать для этого вида генерации.

    Два источника: каталог аккаунта через MCP (он меняется, поэтому не зашит) и
    модели REST-пути. Раньше без MCP список был пустым, и меню отвечало «нет ни
    одной модели», хотя ключ Higgsfield работал и генерация шла.
    """
    out: list[dict] = []
    if mcp_configured():
        try:
            res = await _mcp_call("models_explore", {"action": "list", "type": kind,
                                                     "limit": 50}, timeout=60)
            out += [{"value": m["id"], "label": m["name"], "group": "HIXIIT",
                     "connected": True} for m in _as_model_list(res)]
        except BaseException as e:
            _reraise_control_flow(e)

    # Без MCP выбирать всё равно есть из чего: показываем проверенный каталог
    # платформы. Он честный — эти id существуют, — но пометка говорит, что путь
    # исполнения будет REST, если MCP не подключён.
    if not out:
        known = VIDEO_MODELS if kind == "video" else IMAGE_MODELS
        from core.higgsfield import credentials as _creds
        reachable = bool(_creds())
        out = [{"value": m["value"], "label": m["label"], "group": "Higgsfield",
                "connected": reachable} for m in known]
    return out


async def _key_sources() -> list[dict]:
    """Для каждой половины доступа: заполнена ли, откуда и последние 4 символа."""
    from core import credentials
    shadowed = set(credentials.LAST_LOAD.get("shadowed") or [])
    out = []
    for env_name, human in (("HIGGSFIELD_API_KEY", "ключ"),
                            ("HIGGSFIELD_SECRET", "секрет")):
        value = (os.getenv(env_name) or "").strip()
        # Именно запись в базе, а не credentials.get(): тот при отсутствии
        # записи возвращает значение окружения, и источник всегда выглядел бы
        # как «дашборд».
        try:
            from sqlalchemy import select
            from database.db import AsyncSessionLocal
            from database.models import Connection
            async with AsyncSessionLocal() as db:
                r = await db.execute(select(Connection).where(
                    Connection.key_name == env_name.lower()))
                saved = r.scalar_one_or_none() is not None
        except Exception:
            saved = False
        if not value:
            source = "не задан"
        elif env_name in shadowed:
            source = "дашборд (перекрывает Render)"
        elif saved:
            source = "дашборд"
        else:
            source = "переменная хостинга"
        # Длина и форма — то, чего не хватало, чтобы человек сам увидел, что
        # «вроде настроил» не равно «настроил»: в панели хостинга значение
        # скрыто точками, и неверное выглядит как верное.
        #
        # Форма UUID требуется ТОЛЬКО от ключа — это единственное, что
        # подтверждено ответом платформы. Секрет в кабинете выдаётся длинной
        # строкой без дефисов, и требовать от него UUID значит помечать
        # правильное значение как ошибку.
        from core.higgsfield import _looks_like_uuid
        shape_ok = (_looks_like_uuid(value) if env_name == "HIGGSFIELD_API_KEY"
                    else bool(value))
        out.append({"name": human, "env": env_name, "filled": bool(value),
                    "source": source, "tail": value[-4:] if len(value) > 4 else "",
                    "length": len(value), "shape_ok": bool(value) and shape_ok})
    return out


async def status() -> dict:
    """Диагностика генеративного слоя — для команды /hixiit в Telegram."""
    from core.higgsfield import credentials as _hf_creds
    out = {
        "mcp_configured": mcp_configured(),
        "api_key": bool(_hf_creds()),
        "default_model": os.getenv("HIGGSFIELD_MODEL", "auto"),
    }
    # Откуда приехали ключ и секрет и чем заканчиваются: без этого нельзя
    # понять, почему «в Render всё вписано», а запрос отклонён — значение из
    # дашборда молча перекрывает переменную хостинга.
    out["key_sources"] = await _key_sources()

    # Наличие ключа ничего не доказывает: он бывает от другого аккаунта, без
    # кредитов или просрочен. Поэтому спрашиваем сам Higgsfield.
    if out["api_key"]:
        try:
            from core.higgsfield import check as _hf_check
            res = await _hf_check()
            out["api_ok"] = bool(res.get("ok"))
            if not res.get("ok"):
                out["api_error"] = res.get("error", "")
        except BaseException as e:
            _reraise_control_flow(e)
            out["api_ok"] = False
            out["api_error"] = f"{type(e).__name__}: {str(e)[:150]}"
    try:
        from api.routes_desktop import desktop_connected
        out["browser_agent"] = desktop_connected()
    except Exception:
        out["browser_agent"] = False

    if out["mcp_configured"]:
        try:
            out["unlim"] = await unlim_status()
        except BaseException as e:
            _reraise_control_flow(e)
        try:
            bal = await _mcp_call("balance", {}, timeout=30)
            out["mcp_ok"] = True
            if isinstance(bal, dict):
                out["credits"] = bal.get("credits")
                out["plan"] = bal.get("subscription_plan_type")
        except BaseException as e:
            _reraise_control_flow(e)
            out["mcp_ok"] = False
            out["mcp_error"] = f"{type(e).__name__}: {str(e)[:180]}"
    return out
