"""Поиск должен объяснять отказ, а не отвечать «пусто».

В диагностике было «ни один источник не дал результатов (perplexity: пусто;
duckduckgo: пусто)». На деле у Perplexity просто нет ключа, а DuckDuckGo
блокирует запросы с серверных адресов — это чинится совершенно по-разному, но
из сообщения этого было не понять.
"""
import pytest
import httpx

from core import duckduckgo, websearch


class _Reply:
    """Отдаёт заранее заданные ответы вместо сети."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, *a, **kw):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def _next(self, url):
        self.calls.append(url)
        status, body = self.responses.pop(0) if self.responses else (200, "")
        return httpx.Response(status, text=body, request=httpx.Request("GET", url))

    async def post(self, url, data=None):
        return self._next(url)

    async def get(self, url, params=None):
        return self._next(url)


HTML_RESULT = '''
<div class="result">
  <h2 class="result__title"><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpost">
  Тренды доставки</a></h2>
  <a class="result__snippet">Что растёт в 2026 году</a>
</div>
'''


@pytest.mark.asyncio
async def test_redirect_link_is_unwrapped(monkeypatch):
    """В выдаче ссылки завёрнуты в редирект — наверх должен уйти живой адрес."""
    monkeypatch.setattr(httpx, "AsyncClient", _Reply((200, HTML_RESULT)))

    res = await duckduckgo.search_detailed("доставка", 5)

    assert res["ok"]
    assert res["items"][0]["url"] == "https://example.com/post"
    assert res["items"][0]["title"] == "Тренды доставки"


@pytest.mark.asyncio
async def test_lite_endpoint_is_tried_after_block(monkeypatch):
    """Один адрес блокирует серверные запросы — берём второй, а не сдаёмся."""
    lite = '<a class="result-link" href="https://example.org/x">Заголовок статьи</a>'
    fake = _Reply((403, "blocked"), (403, "blocked"), (200, lite))
    monkeypatch.setattr(httpx, "AsyncClient", fake)

    res = await duckduckgo.search_detailed("тест", 5)

    assert res["ok"] and res["items"][0]["url"] == "https://example.org/x"
    assert any("lite" in u for u in fake.calls)


@pytest.mark.asyncio
async def test_block_is_named_not_called_empty(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _Reply(*[(403, "b")] * 4))

    res = await duckduckgo.search_detailed("тест", 5)

    assert res["ok"] is False
    assert "403" in res["error"] and "блокир" in res["error"]


@pytest.mark.asyncio
async def test_robot_check_is_named(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _Reply(*[(200, "<html>anomaly</html>")] * 4))

    res = await duckduckgo.search_detailed("тест", 5)
    assert "робот" in res["error"]


@pytest.mark.asyncio
async def test_missing_key_is_not_reported_as_empty(monkeypatch):
    """Главное: «нет ключа» и «пусто» — разные диагнозы."""
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    monkeypatch.setattr(httpx, "AsyncClient", _Reply(*[(403, "b")] * 4))

    res = await websearch.search("тренды доставки")

    assert res["ok"] is False
    assert "PERPLEXITY_API_KEY" in res["error"], "должно быть видно, чего не хватает"
    assert "duckduckgo: пусто" not in res["error"]
    assert "403" in res["error"]
