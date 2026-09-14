"""Проверки должны читать те ключи, которые источник реально возвращает.

Дважды в одном проекте статус поиска читал ключ `results`, которого в ответе
нет (`search` возвращает `items`). Такая проверка не может стать зелёной
никогда — и «поиск не работает» показывалось днями, хотя ломалась сама
проверка. Это худший сорт дефекта: он маскируется под чужую поломку.
"""
import pytest

from core import health, system_test, websearch


def _found(provider="браузер"):
    return {"ok": True, "query": "тест", "provider": provider,
            "items": [{"title": "Заголовок", "snippet": "о чём",
                       "url": "https://a.test/1"}]}


@pytest.mark.asyncio
async def test_search_returns_items_key(monkeypatch):
    """Контракт: успешная выдача лежит в `items`."""
    async def fake(query, n):
        return [{"title": "t", "snippet": "s", "url": "https://a.test"}]

    monkeypatch.setattr(websearch, "_search_ddg", fake)
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    res = await websearch.search("тест", 1)
    assert "items" in res and res["items"]
    assert "results" not in res


@pytest.mark.asyncio
async def test_health_probe_goes_green_on_real_output(monkeypatch):
    async def fake_search(query, n, budget=60.0):
        return _found()

    monkeypatch.setattr("core.websearch.search", fake_search)
    assert (await health._probe_web())["ok"]


@pytest.mark.asyncio
async def test_system_test_goes_green_on_real_output(monkeypatch):
    """Второе место с тем же дефектом."""
    async def fake_search(query, n, budget=60.0):
        return _found()

    monkeypatch.setattr("core.websearch.search", fake_search)
    assert (await system_test.check_search())["ok"]


@pytest.mark.asyncio
async def test_system_test_names_the_provider(monkeypatch):
    async def fake_search(query, n, budget=60.0):
        return _found(provider="perplexity")

    monkeypatch.setattr("core.websearch.search", fake_search)
    res = await system_test.check_search()
    assert "perplexity" in str(res)


@pytest.mark.asyncio
async def test_system_test_bounds_its_budget(monkeypatch):
    """Самопроверка не должна висеть на медленном источнике минутами."""
    seen = {}

    async def fake_search(query, n, budget=60.0):
        seen["budget"] = budget
        return _found()

    monkeypatch.setattr("core.websearch.search", fake_search)
    await system_test.check_search()
    assert seen["budget"] <= 30


@pytest.mark.asyncio
async def test_empty_output_is_still_a_failure(monkeypatch):
    """Починка ключа не должна превратить пустую выдачу в успех."""
    async def fake_search(query, n, budget=60.0):
        return {"ok": True, "provider": "браузер", "items": []}

    monkeypatch.setattr("core.websearch.search", fake_search)
    assert not (await health._probe_web())["ok"]
    assert not (await system_test.check_search())["ok"]
