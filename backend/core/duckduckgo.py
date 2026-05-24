"""
Free DuckDuckGo search — no API key required.
Used by TrendAnalyst for daily trend scraping.
"""
import httpx
import json
import re

DDG_URL = "https://api.duckduckgo.com/"
DDG_SEARCH = "https://html.duckduckgo.com/html/"

async def search(query: str, max_results: int = 10) -> list[dict]:
    """Search DuckDuckGo and return list of {title, snippet, url}."""
    try:
        async with httpx.AsyncClient(timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }) as c:
            r = await c.post(DDG_SEARCH, data={"q": query, "b": ""})
            text = r.text
            results = []
            # Parse result snippets from HTML
            blocks = re.findall(
                r'class="result__title".*?href="([^"]+)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</span>',
                text, re.DOTALL
            )
            for url, title, snippet in blocks[:max_results]:
                title_clean = re.sub(r'<[^>]+>', '', title).strip()
                snippet_clean = re.sub(r'<[^>]+>', '', snippet).strip()
                if title_clean and len(title_clean) > 3:
                    results.append({"title": title_clean, "snippet": snippet_clean, "url": url})
            return results
    except Exception as e:
        return [{"title": "Search error", "snippet": str(e), "url": ""}]

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
