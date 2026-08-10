"""
Чтение соцсетей БЕЗ API — через браузер (тот же, что и для публикации).

Симметрично публикации без API: серверный/удалённый браузер открывает публичную
страницу профиля или ролика, забирает текст (и при необходимости скриншот), а
дешёвый LLM извлекает метрики. Ключи площадок не нужны.

Приватная статистика (охваты/удержание) видна только в залогиненном кабинете —
для неё браузер должен быть залогинен теми же cookies (NEXUS_BROWSER_STORAGE_STATE),
что и для публикации. Без логина возвращаются публичные данные.
"""
import re
import json

from core import server_browser

# Ник для URL: только безопасные символы, чтобы нельзя было подменить путь/хост.
_HANDLE_RE = re.compile(r"[^A-Za-z0-9._-]")


def enabled() -> bool:
    return server_browser.enabled()


def _profile_url(platform: str, handle: str) -> str | None:
    h = _HANDLE_RE.sub("", (handle or "").lstrip("@").strip())
    if not h:
        return None
    if platform == "instagram":
        return f"https://www.instagram.com/{h}/"
    if platform == "tiktok":
        return f"https://www.tiktok.com/@{h}"
    if platform == "youtube":
        return f"https://www.youtube.com/@{h}/videos"
    return None


async def _open_text(url: str) -> dict:
    """Открывает URL в браузере и возвращает {ok, text}."""
    nav = await server_browser.execute({"action": "navigate", "url": url})
    if not nav.get("ok"):
        return {"ok": False, "error": nav.get("error", "navigate failed")}
    txt = await server_browser.execute({"action": "page_text"})
    text = (txt.get("text") or "") if txt.get("ok") else ""
    return {"ok": True, "text": text}


async def _extract(system: str, prompt: str) -> dict:
    """Извлекает JSON дешёвым LLM из текста страницы."""
    from core.ai_router import ai_router, ECONOMY_MODELS
    model = ECONOMY_MODELS.get("niche_analyst", "gemini-2.0-flash")
    try:
        res = await ai_router.call(model, system, prompt)
        text = res.get("text", "")
        s, e = text.find("{"), text.rfind("}") + 1
        return json.loads(text[s:e])
    except Exception as ex:
        return {"_error": str(ex)[:150]}


_PROFILE_SYS = ("Ты извлекаешь метрики соцсети из текста веб-страницы. Верни СТРОГО JSON, "
                "числа — как целые (10.5K → 10500, 2.3M → 2300000), без пояснений.")


async def analyze_profile(platform: str, handle: str) -> dict:
    """Публичное досье аккаунта через браузер (без API)."""
    url = _profile_url(platform, handle)
    if not url:
        return {"ok": False, "platform": platform, "handle": handle, "error": "no url"}
    if not enabled():
        return {"ok": False, "platform": platform, "handle": handle, "error": "браузер выключен"}

    page = await _open_text(url)
    if not page.get("ok"):
        return {"ok": False, "platform": platform, "handle": handle, "error": page.get("error")}

    prompt = (
        f"Площадка: {platform}. Со страницы профиля извлеки данные аккаунта.\n"
        f"ТЕКСТ СТРАНИЦЫ:\n{page.get('text','')[:6000]}\n\n"
        'Верни JSON: {"followers": int|null, "posts_count": int|null, '
        '"bio": "строка|null", "top_posts": [{"title":"...","views":int|null,'
        '"likes":int|null,"url":"...|null"}]}'
    )
    data = await _extract(_PROFILE_SYS, prompt)
    if data.get("_error"):
        return {"ok": False, "platform": platform, "handle": handle, "error": data["_error"]}

    return {
        "ok": True,
        "platform": platform,
        "handle": handle,
        "followers": data.get("followers"),
        "posts_count": data.get("posts_count"),
        "bio": data.get("bio"),
        "top_posts": data.get("top_posts") or [],
        "source": "browser",
    }


async def analyze_post(url: str) -> dict:
    """Метрики одного ролика/поста по ссылке через браузер (без API)."""
    if not enabled():
        return {"ok": False, "url": url, "error": "браузер выключен"}
    if not server_browser.url_allowed(url):
        return {"ok": False, "url": url, "error": "недопустимый URL (только внешние http(s))"}
    page = await _open_text(url)
    if not page.get("ok"):
        return {"ok": False, "url": url, "error": page.get("error")}
    prompt = (
        f"Со страницы ролика/поста извлеки метрики.\n"
        f"ТЕКСТ СТРАНИЦЫ:\n{page.get('text','')[:6000]}\n\n"
        'Верни JSON: {"title":"...","author":"...","views":int|null,"likes":int|null,'
        '"comments":int|null,"duration":int|null}'
    )
    data = await _extract(_PROFILE_SYS, prompt)
    if data.get("_error"):
        return {"ok": False, "url": url, "error": data["_error"]}
    return {"ok": True, "url": url, "source": "browser", **data}
