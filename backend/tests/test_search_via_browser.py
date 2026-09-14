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
    async def fake_open(url):
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
