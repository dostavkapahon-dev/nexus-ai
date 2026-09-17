"""Поиск не должен падать вместе с квотой модели.

С хостинга бесплатные пути перекрыты: DuckDuckGo отвечает проверкой на робота,
Mojeek не открывается, а «поиск через Google» идёт ключом Gemini — исчерпанная
квота модели гасила заодно и поиск. Brave от этого не зависит.
"""
import httpx
import pytest

from core import websearch


class _Resp:
    def __init__(self, status=200, data=None):
        self.status_code = status
        self._data = data or {}
        self.content = b"{}"

    def json(self):
        return self._data


@pytest.fixture
def brave_key(monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "test-key")


def _client(resp, seen):
    class C:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None, headers=None):
            seen.append({"url": url, "params": params, "headers": headers})
            return resp
    return lambda *a, **k: C()


@pytest.mark.asyncio
async def test_no_key_says_which_one(monkeypatch):
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    with pytest.raises(websearch.NoKey) as e:
        await websearch._search_brave("шашлык", 5)
    assert "BRAVE_API_KEY" in str(e.value)


@pytest.mark.asyncio
async def test_results_are_parsed(brave_key, monkeypatch):
    seen = []
    data = {"web": {"results": [
        {"title": "Шашлык", "description": "рецепт", "url": "https://a.example/1"},
        {"title": "Без ссылки", "description": "", "url": "не-ссылка"},
    ]}}
    monkeypatch.setattr(httpx, "AsyncClient", _client(_Resp(200, data), seen))
    out = await websearch._search_brave("шашлык", 5)
    assert out == [{"title": "Шашлык", "snippet": "рецепт",
                    "url": "https://a.example/1", "source": "brave"}]
    # Ключ уходит заголовком, а не в адресе: адреса попадают в логи.
    assert seen[0]["headers"]["X-Subscription-Token"] == "test-key"
    assert "test-key" not in str(seen[0]["params"])


@pytest.mark.asyncio
async def test_limit_and_bad_key_are_named(brave_key, monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _client(_Resp(429), []))
    with pytest.raises(RuntimeError, match="лимит"):
        await websearch._search_brave("шашлык", 5)

    monkeypatch.setattr(httpx, "AsyncClient", _client(_Resp(401), []))
    with pytest.raises(RuntimeError, match="не принят"):
        await websearch._search_brave("шашлык", 5)


@pytest.mark.asyncio
async def test_brave_is_tried_before_the_google_path(monkeypatch):
    """Порядок важен: у пути «через Google» общая квота с моделью."""
    import inspect
    src = inspect.getsource(websearch.search)
    assert src.index('"brave"') < src.index('"google"')
