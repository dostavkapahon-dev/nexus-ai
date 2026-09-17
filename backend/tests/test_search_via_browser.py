"""Поиск через браузер — третий источник, без ключей.

Perplexity требует платный ключ, DuckDuckGo по http блокирует серверные
адреса. Браузер открывает ту же выдачу как обычный посетитель и работает там,
где http-запрос отбивают, — поэтому «интернет-поиск» перестаёт зависеть от
покупки ключа.
"""
import pytest

from core import websearch as ws


def _browser(monkeypatch, available=True, why=""):
    async def fake_available():
        return {"available": available, "where": "облако", "why": why}

    monkeypatch.setattr("core.hixiit.browser_available", fake_available)


def _page(monkeypatch, text="Результат 1 https://a.test", ok=True, error=""):
    async def fake_open(url, timeout_ms=0):
        return {"ok": ok, "text": text, "error": error}

    monkeypatch.setattr("core.browser_reader._open_text", fake_open)


def _extract(monkeypatch, data):
    async def fake_extract(system, prompt):
        return data

    monkeypatch.setattr("core.browser_reader._extract", fake_extract)


@pytest.mark.asyncio
async def test_browser_search_returns_items(monkeypatch):
    _browser(monkeypatch)
    _page(monkeypatch)
    _extract(monkeypatch, {"items": [
        {"title": "Тренды", "snippet": "о трендах", "url": "https://a.test/1"}]})
    items = await ws._search_browser("тренды", 5)
    assert items and items[0]["url"] == "https://a.test/1"
    assert items[0]["source"] == "браузер" or items[0]["source"] == "browser"


@pytest.mark.asyncio
async def test_items_without_real_links_are_dropped(monkeypatch):
    """Модель иногда выдумывает ссылку — без http это не результат."""
    _browser(monkeypatch)
    _page(monkeypatch)
    _extract(monkeypatch, {"items": [{"title": "x", "snippet": "y", "url": "нет"}]})
    assert await ws._search_browser("тренды", 5) == []


@pytest.mark.asyncio
async def test_no_browser_is_a_missing_key_not_an_error(monkeypatch):
    """«Не настроен» и «сломался» чинятся по-разному — каскад их различает."""
    _browser(monkeypatch, available=False, why="нет NEXUS_BROWSER_CDP")
    with pytest.raises(ws.NoKey) as e:
        await ws._search_browser("тренды", 5)
    assert "NEXUS_BROWSER_CDP" in str(e.value)


@pytest.mark.asyncio
async def test_empty_page_is_an_error(monkeypatch):
    _browser(monkeypatch)
    _page(monkeypatch, text="   ")
    with pytest.raises(RuntimeError):
        await ws._search_browser("тренды", 5)


@pytest.mark.asyncio
async def test_limit_is_respected(monkeypatch):
    _browser(monkeypatch)
    _page(monkeypatch)
    _extract(monkeypatch, {"items": [
        {"title": f"t{i}", "snippet": "s", "url": f"https://a.test/{i}"}
        for i in range(10)]})
    assert len(await ws._search_browser("тренды", 3)) == 3


@pytest.mark.asyncio
async def test_cascade_falls_through_to_browser(monkeypatch):
    """Главное: когда ключа нет и http отбит, поиск всё равно отвечает."""
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

    async def ddg_blocked(query, n):
        raise RuntimeError("403 заблокировано")

    monkeypatch.setattr(ws, "_search_ddg", ddg_blocked)
    _browser(monkeypatch)
    _page(monkeypatch)
    _extract(monkeypatch, {"items": [
        {"title": "Тренды", "snippet": "о трендах", "url": "https://a.test/1"}]})

    res = await ws.search("тренды", 5)
    assert res["ok"] and res["provider"] == "браузер"


@pytest.mark.asyncio
async def test_all_sources_down_names_every_reason(monkeypatch):
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

    async def ddg_blocked(query, n):
        raise RuntimeError("403 заблокировано")

    monkeypatch.setattr(ws, "_search_ddg", ddg_blocked)
    _browser(monkeypatch, available=False, why="нет NEXUS_BROWSER_CDP")

    res = await ws.search("тренды", 5)
    assert not res["ok"]
    assert "PERPLEXITY" in res["error"] and "403" in res["error"]
    assert "NEXUS_BROWSER_CDP" in res["error"]


@pytest.mark.asyncio
async def test_browser_search_uses_a_reachable_index(monkeypatch):
    """DuckDuckGo с хостинга не открывается вовсе — ни обычный, ни lite."""
    from core import websearch
    opened = {}

    async def fake_open(url, timeout_ms=0):
        opened["url"] = url
        return {"ok": True, "text": "Результаты"}

    async def fake_extract(system, text):
        return {"items": [{"title": "т", "url": "https://x.test"}]}

    async def available():
        return {"available": True, "where": "на сервере", "why": ""}

    monkeypatch.setattr("core.hixiit.browser_available", available)
    monkeypatch.setattr("core.browser_reader._open_text", fake_open)
    monkeypatch.setattr("core.browser_reader._extract", fake_extract)
    await websearch._search_browser("маркетинг", 2)
    assert opened["url"].startswith("https://www.google.com/search")


@pytest.mark.asyncio
async def test_robot_check_is_named_not_called_empty(monkeypatch):
    from core import websearch

    async def fake_open(url, timeout_ms=0):
        return {"ok": True, "text": "Unusual traffic from your computer network"}

    async def available():
        return {"available": True, "where": "на сервере", "why": ""}

    monkeypatch.setattr("core.hixiit.browser_available", available)
    monkeypatch.setattr("core.browser_reader._open_text", fake_open)
    with pytest.raises(RuntimeError) as e:
        await websearch._search_browser("маркетинг", 2)
    # Причина называется по каждому индексу: какой именно нас отбил — это и
    # есть то, что чинят дальше.
    assert "проверка на робота" in str(e.value)
    assert "google" in str(e.value)


@pytest.mark.asyncio
async def test_mojeek_parses_real_results(monkeypatch):
    """DuckDuckGo с хостинга не открылся даже за 45 секунд — нужен другой индекс."""
    from core import websearch

    html = ('<html><body>'
            '<a href="https://example.test/a" class="ob">Первый результат</a>'
            '<a href="https://example.test/b" class="ob">Второй результат</a>'
            '</body></html>')

    class _R:
        status_code = 200
        text = html

    class _C:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            assert "mojeek.com" in url
            return _R()

    monkeypatch.setattr("httpx.AsyncClient", _C)
    items = await websearch._search_mojeek("вирусные темы", 5)
    assert [i["url"] for i in items] == ["https://example.test/a",
                                         "https://example.test/b"]
    assert items[0]["title"] == "Первый результат"


@pytest.mark.asyncio
async def test_mojeek_failure_is_named(monkeypatch):
    from core import websearch

    class _R:
        status_code = 429
        text = ""

    class _C:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            return _R()

    monkeypatch.setattr("httpx.AsyncClient", _C)
    with pytest.raises(RuntimeError) as e:
        await websearch._search_mojeek("тест", 3)
    assert "429" in str(e.value)


@pytest.mark.asyncio
async def test_browser_search_does_not_wait_45_seconds(monkeypatch):
    """Ждать полминуты бессмысленно: за это время источник всё равно молчит."""
    from core import websearch
    opened = {}

    async def fake_open(url, timeout_ms=0):
        opened.update(url=url, timeout_ms=timeout_ms)
        return {"ok": True, "text": "Результаты"}

    async def fake_extract(system, text):
        return {"items": [{"title": "т", "url": "https://x.test"}]}

    async def available():
        return {"available": True, "where": "на сервере", "why": ""}

    monkeypatch.setattr("core.hixiit.browser_available", available)
    monkeypatch.setattr("core.browser_reader._open_text", fake_open)
    monkeypatch.setattr("core.browser_reader._extract", fake_extract)
    await websearch._search_browser("маркетинг", 2)
    # Двадцать секунд на индекс: их теперь несколько, и ждать бесконечно
    # нельзя, но и пятнадцати живой выдаче не всегда хватало.
    assert opened["timeout_ms"] == 20000
    assert "google.com" in opened["url"], "первым — индекс, доступный с сервера"


@pytest.mark.asyncio
async def test_google_source_extracts_real_links(monkeypatch):
    """Замер сети: DuckDuckGo и Mojeek с хостинга закрыты, Google отвечает.

    Ссылки берём из метаданных ответа — это адреса, которые Google реально
    нашёл, а не то, что модель могла придумать.
    """
    from core import websearch

    class _Web:
        uri = "https://example.test/article"
        title = "Живая статья"

    class _Chunk:
        web = _Web()

    class _Meta:
        grounding_chunks = [_Chunk()]

    class _Cand:
        grounding_metadata = _Meta()

    class _Resp:
        candidates = [_Cand()]

    class _Model:
        def __init__(self, *a, **k):
            pass

        def generate_content(self, prompt):
            return _Resp()

    # Подменяем атрибуты самого модуля: `import google.generativeai` внутри
    # функции берёт уже загруженный модуль, и запись в sys.modules его не
    # заменит.
    import google.generativeai as genai
    monkeypatch.setattr(genai, "configure", lambda **k: None)
    monkeypatch.setattr(genai, "GenerativeModel", _Model)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    items = await websearch._search_gemini("вирусные темы", 5)
    assert items[0]["url"] == "https://example.test/article"
    assert items[0]["source"] == "google"


@pytest.mark.asyncio
async def test_google_source_without_key_says_so(monkeypatch):
    from core import websearch
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(websearch.NoKey):
        await websearch._search_gemini("тест", 3)


def test_unreachable_sources_are_no_longer_first():
    """Порядок источников следует измеренной доступности, а не привычке."""
    import inspect
    from core import websearch
    body = inspect.getsource(websearch.search)
    google_at = body.index('"google"')
    ddg_at = body.index('"duckduckgo"')
    assert google_at < ddg_at, "доступный источник должен идти раньше закрытого"
