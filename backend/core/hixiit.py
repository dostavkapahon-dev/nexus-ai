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
        from mcp.client.streamable_http import streamablehttp_client
    except BaseException as e:
        raise RuntimeError(
            f"клиент mcp недоступен ({type(e).__name__}: {str(e)[:100]}); "
            "проверь установку пакета mcp") from None

    headers = {}
    token = os.getenv("HIGGSFIELD_MCP_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async def _run():
        async with streamablehttp_client(url, headers=headers or None) as (read, write, _):
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
    """Авто-выбор модели: спрашиваем РЕАЛЬНЫЙ каталог аккаунта, а не хардкод.

    Возвращает {'id': ..., 'name': ...} либо {} если каталог недоступен.
    """
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


async def _generate_via_mcp(task: str, kind: str, ratio: str,
                            image_url: str = None) -> dict:
    model = await pick_model(task, kind, has_reference=bool(image_url))
    tool = "generate_video" if kind == "video" else "generate_image"
    args = {"prompt": task[:1500], "aspect_ratio": ratio}
    if model.get("id"):
        args["model"] = model["id"]
    if image_url:
        args["image_url"] = image_url

    res = await _mcp_call(tool, args)
    url = _find_media_url(res)
    if not url:
        raise RuntimeError(f"MCP вернул результат без ссылки на медиа: {str(res)[:300]}")
    return {"ok": True, "url": url, "provider": "higgsfield_mcp",
            "kind": kind, "model": model.get("id") or "auto"}


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

async def generate(task: str, kind: str = "auto", ratio: str = None,
                   image_url: str = None, allow_free: bool = True) -> dict:
    """Сгенерировать медиа по задаче. Никогда не бросает — возвращает отчёт.

    {'ok': True, 'url', 'provider', 'kind', 'model'}
    {'ok': False, 'error': <человеческая причина>, 'tried': [...]}
    """
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

    # 2. REST по ключу+секрету из Higgsfield Cloud
    from core.higgsfield import credentials as _hf_credentials
    if _hf_credentials():
        if kind == "video":
            try:
                from core.higgsfield import create_video, poll_video
                started = await create_video(prompt=task, image_url=image_url, ratio=ratio)
                if started.get("ok"):
                    done = await poll_video(started["job_id"])
                    if done.get("ok") and done.get("url"):
                        return {"ok": True, "url": done["url"], "provider": "higgsfield_api",
                                "kind": "video", "model": os.getenv("HIGGSFIELD_MODEL", "default")}
                    tried.append(f"REST: {done.get('error', 'нет ссылки на видео')}")
                else:
                    tried.append(f"REST: {started.get('error', 'запуск не удался')}")
            except Exception as e:
                tried.append(f"REST: {str(e)[:200]}")
        else:
            tried.append("REST: генерация изображений через API не поддерживается")
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


async def available_models(kind: str = "image") -> list[dict]:
    """Модели HIXIIT, доступные аккаунту, — для выбора в настройках.

    Список берётся у аккаунта, а не из зашитого перечня: каталог Higgsfield
    меняется, и зашитые id рано или поздно перестают существовать. Если MCP
    недоступен, честно возвращаем пусто — выбирать не из чего.
    """
    if not mcp_configured():
        return []
    try:
        res = await _mcp_call("models_explore", {"action": "list", "type": kind,
                                                 "limit": 50}, timeout=60)
    except BaseException as e:
        _reraise_control_flow(e)
        return []
    return [{"value": m["id"], "label": m["name"], "group": "HIXIIT",
             "connected": True} for m in _as_model_list(res)]


async def status() -> dict:
    """Диагностика генеративного слоя — для команды /hixiit в Telegram."""
    from core.higgsfield import credentials as _hf_creds
    out = {
        "mcp_configured": mcp_configured(),
        "api_key": bool(_hf_creds()),
        "default_model": os.getenv("HIGGSFIELD_MODEL", "auto"),
    }
    try:
        from api.routes_desktop import desktop_connected
        out["browser_agent"] = desktop_connected()
    except Exception:
        out["browser_agent"] = False

    if out["mcp_configured"]:
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
