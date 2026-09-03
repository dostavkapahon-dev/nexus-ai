"""
Исследование интернета: каскад источников, безопасность адресов, сводка.

Сеть в тестах не трогаем. Проверяется то, что решает поведение системы:
поиск не падает целиком из-за одного сломанного источника, и агент не может
через ссылку добраться до внутренней сети сервера.
"""
import httpx
import pytest

from core import websearch as ws


@pytest.mark.asyncio
async def test_search_falls_back_when_first_source_fails(monkeypatch):
    """Хрупкий источник не должен оставлять систему совсем без данных."""
    async def broken(query, n):
        raise RuntimeError("provider down")

    async def working(query, n):
        return [{"title": "Тренд", "snippet": "о чём", "url": "https://example.com/a",
                 "source": "duckduckgo"}]

    monkeypatch.setattr(ws, "_search_perplexity", broken)
    monkeypatch.setattr(ws, "_search_ddg", working)

    res = await ws.search("тренды доставки")
    assert res["ok"] and res["provider"] == "duckduckgo"
    assert res["items"][0]["url"] == "https://example.com/a"


@pytest.mark.asyncio
async def test_search_reports_when_nothing_worked(monkeypatch):
    async def empty(query, n):
        return []

    monkeypatch.setattr(ws, "_search_perplexity", empty)
    monkeypatch.setattr(ws, "_search_ddg", empty)

    res = await ws.search("что угодно")
    assert res["ok"] is False and res["items"] == []
    assert "duckduckgo" in res["error"]


@pytest.mark.asyncio
async def test_empty_query_is_refused():
    res = await ws.search("   ")
    assert res["ok"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "http://127.0.0.1:8000/admin",
    "http://localhost/",
    "http://169.254.169.254/latest/meta-data/",     # метаданные облака
    "not-a-url",
])
async def test_fetch_refuses_internal_and_non_http(url):
    res = await ws.fetch(url)
    assert res["ok"] is False and "недопустим" in res["error"]


def test_redirect_target_is_checked():
    """Внешний адрес может увести редиректом внутрь — это и закрываем."""
    assert ws.redirect_allowed("https://example.com/next") is True
    assert ws.redirect_allowed("http://127.0.0.1/admin") is False
    assert ws.redirect_allowed("http://169.254.169.254/") is False
    assert ws.redirect_allowed("file:///etc/passwd") is False


@pytest.mark.asyncio
async def test_fetch_stops_redirect_into_internal_network(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "example.com":
            return httpx.Response(302, headers={"location": "http://127.0.0.1:8000/secret"})
        return httpx.Response(200, text="<html><body>секрет</body></html>")

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)

    res = await ws.fetch("https://example.com/start")
    assert res["ok"] is False and "внутреннюю сеть" in res["error"]


@pytest.mark.asyncio
async def test_fetch_reads_page_text(monkeypatch):
    html = ("<html><head><title>Заголовок</title></head><body>"
            "<script>var x=1</script><p>" + "полезный текст " * 60 + "</p></body></html>")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda *a, **kw: real_client(*a, **{**kw, "transport": transport}))

    res = await ws.fetch("https://example.com/article")
    assert res["ok"] and res["title"] == "Заголовок"
    assert "полезный текст" in res["text"]
    assert "var x=1" not in res["text"]          # скрипты в текст не попадают


@pytest.mark.asyncio
async def test_deep_research_saves_to_history(client, monkeypatch):
    async def fake_search(query, max_results=8):
        return {"ok": True, "query": query, "provider": "duckduckgo",
                "items": [{"title": "Статья", "snippet": "о трендах",
                           "url": "https://example.com/a"}]}

    async def fake_fetch(url):
        return {"ok": True, "url": url, "title": "Статья", "text": "текст " * 200}

    async def fake_summarize(topic, raw):
        return "выжимка по теме"

    monkeypatch.setattr(ws, "search", fake_search)
    monkeypatch.setattr(ws, "fetch", fake_fetch)
    monkeypatch.setattr(ws, "_summarize", fake_summarize)

    res = await ws.deep_research("тренды доставки", pages=1)
    assert res["ok"] and res["summary"] == "выжимка по теме"
    assert res["sources"][0]["read"] is True

    from core.research_store import history
    saved = await history(kind="web", limit=5)
    assert saved and saved[0]["query"] == "тренды доставки"


@pytest.mark.asyncio
async def test_deep_research_without_readable_pages_returns_links(monkeypatch):
    """Ссылки есть, а прочитать нечего — отдаём ссылки, а не выдуманные выводы."""
    async def fake_search(query, max_results=8):
        return {"ok": True, "query": query, "provider": "duckduckgo",
                "items": [{"title": "Статья", "snippet": "", "url": "https://example.com/a"}]}

    async def fake_fetch(url):
        return {"ok": False, "url": url, "error": "403"}

    monkeypatch.setattr(ws, "search", fake_search)
    monkeypatch.setattr(ws, "fetch", fake_fetch)

    res = await ws.deep_research("тема", pages=1)
    assert res["ok"] and res["summary"] == "" and res["sources"][0]["read"] is False


@pytest.mark.asyncio
async def test_director_has_internet_tools():
    from core import marketing_director as md

    names = [t["name"] for t in md.TOOLS]
    assert {"web_search", "open_url", "research"} <= set(names)
    # Gemini-ветка работает по текстовому протоколу: без описания инструментов
    # поиск был бы доступен только через Claude.
    for tool in ("web_search", "open_url", "research"):
        assert tool in md._GEMINI_DIRECTOR_DOC


@pytest.mark.asyncio
async def test_director_tool_calls_search(monkeypatch):
    from core import marketing_director as md

    async def fake_search(query, n=8):
        return {"ok": True, "items": [{"title": "t", "url": "https://x.y", "snippet": ""}]}

    monkeypatch.setattr(ws, "search", fake_search)
    res = await md._exec_tool("web_search", {"query": "тренды"})
    assert res["ok"] and res["items"][0]["url"] == "https://x.y"
