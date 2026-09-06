"""
Free DuckDuckGo search — no API key required.
Used by TrendAnalyst for daily trend scraping.
"""
import httpx
import json
import re

DDG_URL = "https://api.duckduckgo.com/"
# Два адреса, потому что один регулярно отвечает страницей-заглушкой для
# серверных IP. lite отдаёт простую разметку и переживает изменения вёрстки.
ENDPOINTS = ("https://html.duckduckgo.com/html/", "https://lite.duckduckgo.com/lite/")

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# Ссылки в выдаче обёрнуты редиректом //duckduckgo.com/l/?uddg=<адрес>.
_UDDG = re.compile(r"[?&]uddg=([^&\"']+)")

# Разбор ведём несколькими шаблонами: вёрстка DuckDuckGo меняется, и один
# жёсткий шаблон — это молчаливое «ничего не найдено» вместо результатов.
_PATTERNS = (
    # html-версия: заголовок и сниппет рядом
    re.compile(r'class="result__title".*?href="([^"]+)"[^>]*>(.*?)</a>'
               r'.*?class="result__snippet"[^>]*>(.*?)</(?:span|a|div)>', re.S),
    # html-версия без сниппета
    re.compile(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>()', re.S),
    # lite-версия
    re.compile(r'class="result-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>()', re.S),
)

_TAGS = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    text = _TAGS.sub("", text or "")
    for a, b in (("&amp;", "&"), ("&quot;", '"'), ("&#x27;", "'"), ("&nbsp;", " ")):
        text = text.replace(a, b)
    return " ".join(text.split()).strip()


def _real_url(href: str) -> str:
    """Разворачивает редирект DuckDuckGo в настоящий адрес страницы."""
    from urllib.parse import unquote
    m = _UDDG.search(href or "")
    if m:
        href = unquote(m.group(1))
    if href.startswith("//"):
        href = "https:" + href
    return href


def _parse(html: str, max_results: int) -> list[dict]:
    out, seen = [], set()
    for pattern in _PATTERNS:
        for href, title, snippet in pattern.findall(html):
            url = _real_url(href)
            title = _clean(title)
            if not url.startswith("http") or len(title) < 4 or url in seen:
                continue
            seen.add(url)
            out.append({"title": title[:200], "snippet": _clean(snippet)[:400],
                        "url": url})
            if len(out) >= max_results:
                return out
        if out:
            return out
    return out


async def search_detailed(query: str, max_results: int = 10) -> dict:
    """Поиск с причиной отказа.

    Пустой список и «сайт нас заблокировал» — разные вещи, и разница видна
    только здесь. Раньше наверх уходило одинаковое «пусто», и понять, что
    чинить, было нельзя.
    """
    reasons = []
    async with httpx.AsyncClient(timeout=15, headers={"User-Agent": _UA},
                                 follow_redirects=True) as c:
        for url in ENDPOINTS:
            for send in ("post", "get"):
                try:
                    r = (await c.post(url, data={"q": query, "b": ""}) if send == "post"
                         else await c.get(url, params={"q": query}))
                except Exception as e:
                    reasons.append(f"{url}: {type(e).__name__}")
                    continue
                if r.status_code >= 400:
                    reasons.append(f"{url}: HTTP {r.status_code}"
                                   + (" (запросы с сервера блокируются)"
                                      if r.status_code in (403, 429) else ""))
                    continue
                items = _parse(r.text, max_results)
                if items:
                    return {"ok": True, "items": items}
                low = r.text.lower()
                reasons.append(f"{url}: "
                               + ("проверка на робота" if "anomaly" in low
                                  or "challenge" in low else "результатов нет"))
    return {"ok": False, "items": [], "error": "; ".join(reasons[:4])}


async def search(query: str, max_results: int = 10) -> list[dict]:
    """Search DuckDuckGo and return list of {title, snippet, url}."""
    res = await search_detailed(query, max_results)
    if res["ok"]:
        return res["items"]
    return [{"title": "Search error", "snippet": res.get("error", ""), "url": ""}]


async def search_trends(niche: str, city: str = "") -> str:
    """Return formatted string of trending topics for given niche."""
    queries = [
        f"{niche} {city} тренды 2025" if city else f"{niche} тренды 2025",
        f"{niche} viral content TikTok Instagram",
        f"{niche} popular topics trends",
    ]
    all_results = []
    async with httpx.AsyncClient(timeout=15, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }) as c:
        for q in queries[:2]:
            try:
                r = await c.post(DDG_SEARCH, data={"q": q})
                blocks = re.findall(
                    r'class="result__snippet"[^>]*>(.*?)</span>',
                    r.text, re.DOTALL
                )
                for b in blocks[:5]:
                    clean = re.sub(r'<[^>]+>', '', b).strip()
                    if len(clean) > 20:
                        all_results.append(clean)
            except Exception:
                pass

    if not all_results:
        return f"Тренды по нише '{niche}' недоступны"
    return "\n".join(f"• {r}" for r in all_results[:10])
