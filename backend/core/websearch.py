"""
Исследование интернета: поиск, чтение страниц и сводка по теме.

Зачем модуль. Раньше «поиск» был один — скрейпинг html.duckduckgo.com
регулярками из `core/duckduckgo.py`, и вызывал его ровно один агент трендов.
Дирижёр в интернет ходить не умел вовсе: у него не было такого инструмента.

Здесь собран каскад источников, чтобы отказ одного не оставлял систему без
данных: Perplexity (живой поиск с ключом) → DuckDuckGo (без ключа, хрупкий).
Список сайтов намеренно не ограничен — агент сам решает, где искать.

Ограничения оставлены только те, что защищают сервер, а не сужают кругозор:
таймаут, размер страницы, число страниц за один вызов и запрет ходить во
внутреннюю сеть — включая случай, когда туда уводит редирект.
"""
import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

import httpx

MAX_PAGE_CHARS = 20000        # длиннее не нужно: в промпт всё равно уедет выжимка
MAX_PAGES_PER_CALL = 5
TIMEOUT = 20

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


# ─────────────────────────── безопасность адресов ───────────────────────────

def url_allowed(url: str) -> bool:
    """Разрешён ли адрес: только http(s) и не внутренняя сеть.

    Переиспользуем проверку серверного браузера — правило про SSRF должно быть
    одно на систему, а не два расходящихся.
    """
    from core.server_browser import url_allowed as base_allowed
    return base_allowed(url)


def _host_is_private(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
        return (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified)
    except ValueError:
        pass
    try:
        for info in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(info[4][0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local
                    or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
                return True
    except Exception:
        return True
    return False


def redirect_allowed(url: str) -> bool:
    """Проверка адреса, на который увёл редирект.

    Разрешить внешний адрес и не смотреть, куда он перебросил, — значит оставить
    открытой ту самую дыру: 302 на 127.0.0.1 или на адрес облачных метаданных.
    """
    try:
        u = urlparse((url or "").strip())
    except Exception:
        return False
    if u.scheme not in ("http", "https"):
        return False
    host = (u.hostname or "").lower()
    return bool(host) and not _host_is_private(host)


# ─────────────────────────── поиск ───────────────────────────

async def _search_perplexity(query: str, max_results: int) -> list[dict]:
    """Живой поиск через Perplexity — единственный источник, который сам читает
    сеть и возвращает актуальные ссылки."""
    import os
    if not os.getenv("PERPLEXITY_API_KEY"):
        return []
    from core.ai_router import ai_router
    res = await ai_router.call(
        "sonar-pro",
        "Ты поисковый ассистент. Возвращай факты со ссылками, без воды.",
        f"Найди в интернете: {query}\n\n"
        f"Верни до {max_results} пунктов, каждый строкой вида:\n"
        f"НАЗВАНИЕ | КРАТКО О ЧЁМ | URL")
    out = []
    for line in (res.get("text") or "").splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 3 and parts[2].startswith("http"):
            out.append({"title": parts[0][:200], "snippet": parts[1][:400],
                        "url": parts[2], "source": "perplexity"})
    return out[:max_results]


async def _search_ddg(query: str, max_results: int) -> list[dict]:
    from core.duckduckgo import search as ddg_search
    items = await ddg_search(query, max_results)
    # duckduckgo.search на сбое возвращает псевдорезультат «Search error» —
    # он не должен утекать наверх как найденная страница.
    return [{**i, "source": "duckduckgo"} for i in items
            if i.get("url", "").startswith("http") and i.get("title") != "Search error"]


async def search(query: str, max_results: int = 8) -> dict:
    """Поиск по интернету. Каскад источников: отказ одного — не отказ поиска."""
    query = (query or "").strip()
    if not query:
        return {"ok": False, "error": "пустой запрос", "items": []}

    tried = []
    for name, fn in (("perplexity", _search_perplexity), ("duckduckgo", _search_ddg)):
        try:
            items = await fn(query, max_results)
        except Exception as e:
            tried.append(f"{name}: {type(e).__name__}")
            continue
        if items:
            return {"ok": True, "query": query, "provider": name, "items": items}
        tried.append(f"{name}: пусто")

    return {"ok": False, "query": query, "items": [],
            "error": "ни один источник не дал результатов (" + "; ".join(tried) + ")"}


# ─────────────────────────── чтение страницы ───────────────────────────

def _strip_html(html: str) -> str:
    import re
    text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"'))
    return re.sub(r"\s+", " ", text).strip()


def _title_of(html: str) -> str:
    import re
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    return _strip_html(m.group(1))[:200] if m else ""


async def fetch(url: str) -> dict:
    """Читает страницу: сперва обычным запросом, при неудаче — браузером.

    Браузер нужен для сайтов, которые рисуют содержимое скриптами: без него
    вместо статьи возвращается пустая разметка, и агент делает выводы из ничего.
    """
    url = (url or "").strip()
    if not url_allowed(url):
        return {"ok": False, "url": url,
                "error": "адрес недопустим: разрешены только внешние http(s)-адреса"}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False,
                                     headers={"User-Agent": _UA}) as c:
            r = await c.get(url)
            hops = 0
            while r.is_redirect and hops < 5:
                target = str(r.headers.get("location") or "")
                target = str(httpx.URL(url).join(target))
                if not redirect_allowed(target):
                    return {"ok": False, "url": url,
                            "error": "редирект ведёт во внутреннюю сеть — прервано"}
                url, hops = target, hops + 1
                r = await c.get(url)
        html = r.text or ""
        text = _strip_html(html)[:MAX_PAGE_CHARS]
        if len(text) > 400:
            return {"ok": True, "url": url, "title": _title_of(html), "text": text,
                    "via": "http"}
    except Exception as e:
        text = ""
        err = f"{type(e).__name__}: {str(e)[:150]}"
    else:
        err = "страница почти пустая — вероятно, содержимое рисуется скриптами"

    # Фолбэк: браузер на сервере (или удалённый по CDP).
    try:
        from core.browser_reader import _open_text
        res = await _open_text(url)
        if res.get("ok") and len(res.get("text") or "") > 200:
            return {"ok": True, "url": url, "title": "",
                    "text": res["text"][:MAX_PAGE_CHARS], "via": "browser"}
        browser_err = res.get("error") or "браузер вернул пустую страницу"
    except Exception as e:
        browser_err = f"{type(e).__name__}: {str(e)[:150]}"

    return {"ok": False, "url": url, "error": err, "fallback_error": browser_err}


# ─────────────────────────── исследование темы ───────────────────────────

async def deep_research(topic: str, pages: int = 3, niche_id: str = "") -> dict:
    """Поиск → чтение нескольких страниц → сводка. Результат ложится в историю
    исследований, чтобы к нему можно было вернуться и из веба, и из Telegram."""
    found = await search(topic, max_results=max(pages * 2, 6))
    if not found.get("ok"):
        return {"ok": False, "topic": topic, "error": found.get("error"), "sources": []}

    pages = max(1, min(pages, MAX_PAGES_PER_CALL))
    texts, sources = [], []
    for item in found["items"]:
        if len(texts) >= pages:
            break
        page = await fetch(item["url"])
        sources.append({"title": item.get("title", ""), "url": item["url"],
                        "read": bool(page.get("ok")),
                        "error": page.get("error") if not page.get("ok") else ""})
        if page.get("ok"):
            texts.append(f"### {item.get('title') or page.get('title')}\n"
                         f"{item['url']}\n{page['text'][:6000]}")

    if not texts:
        # Ссылки есть, а читать нечего — честно возвращаем ссылки без выводов.
        return {"ok": True, "topic": topic, "summary": "",
                "note": "страницы не удалось прочитать — ниже только ссылки",
                "sources": sources, "provider": found["provider"]}

    summary = await _summarize(topic, "\n\n".join(texts))

    try:
        from core.research_store import save
        await save(kind="web", query=topic, summary=summary,
                   findings={"provider": found["provider"]},
                   sources=[s["url"] for s in sources], niche_id=niche_id)
    except Exception:
        pass

    return {"ok": True, "topic": topic, "summary": summary, "sources": sources,
            "provider": found["provider"]}


async def _summarize(topic: str, raw: str) -> str:
    """Выжимка самым дешёвым доступным исполнителем: суммаризация — не та задача,
    ради которой стоит платить за дорогую модель."""
    from core.dispatch import cheapest_available, delegate
    executor = cheapest_available()
    if not executor:
        return raw[:1500]
    res = await delegate(
        executor,
        f"Сведи найденное по теме «{topic}» в короткую выжимку: что происходит, "
        f"какие факты и цифры важны, что из этого следует. Без воды, по пунктам.",
        system="Ты аналитик. Пиши по-русски, кратко и конкретно.",
        context=raw[:15000])
    return (res.get("text") or "")[:4000] if res.get("ok") else raw[:1500]
