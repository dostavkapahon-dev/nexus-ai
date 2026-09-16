"""Полный ответ платформы вместо обрезанного «400: Unavailabl…».

Отчёты с сервера показывали кусок сообщения, по которому чинить нечего:
непонятно даже, о какой модели речь, если поле `model` мы не отправляем вовсе.
Проверка делает один настоящий запрос и показывает ответ целиком.
"""
import pytest

from core import higgsfield as hf

UUID_A = "3f8c1a2b-4d5e-6f70-8192-a3b4c5d6e7f8"
SECRET = "8f" * 32


@pytest.fixture(autouse=True)
def creds(monkeypatch):
    monkeypatch.setenv("HIGGSFIELD_API_KEY", UUID_A)
    monkeypatch.setenv("HIGGSFIELD_SECRET", SECRET)


def _client(monkeypatch, status, payload):
    class _R:
        status_code = status

        def json(self):
            return payload

        @property
        def text(self):
            return str(payload)

    class _C:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            _C.sent = json
            return _R()

    monkeypatch.setattr("httpx.AsyncClient", _C)
    return _C


@pytest.mark.asyncio
async def test_full_error_body_is_returned(monkeypatch):
    _client(monkeypatch, 400, {"detail": "Unavailable model for this account"})
    res = await hf.probe()
    assert res["ok"] is False
    assert res["status"] == 400
    assert "Unavailable model for this account" in str(res["response"]), \
        "ответ должен доходить целиком, а не обрезком"


@pytest.mark.asyncio
async def test_probe_shows_what_was_sent(monkeypatch):
    """Чтобы спорить о теле запроса, надо его видеть."""
    _client(monkeypatch, 400, {"detail": "x"})
    res = await hf.probe()
    assert "model" not in res["sent"], "поля model в схеме нет — и мы его не шлём"
    assert res["sent"]["width_and_height"] == hf.SIZES["9:16"]
    assert res["sent"]["quality"] in ("720p", "1080p")


@pytest.mark.asyncio
async def test_probe_lists_header_names_not_values(monkeypatch):
    """Имена заголовков полезны, значения — это ключи, им в чате не место."""
    _client(monkeypatch, 400, {"detail": "x"})
    res = await hf.probe()
    assert res["headers"]
    for name in res["headers"]:
        assert UUID_A not in name and SECRET not in name


@pytest.mark.asyncio
async def test_success_is_reported_as_accepted(monkeypatch):
    _client(monkeypatch, 200, {"id": "job-1"})
    res = await hf.probe()
    assert res["ok"] is True and res["stage"] == "принято"


@pytest.mark.asyncio
async def test_bad_key_stops_before_the_request(monkeypatch):
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "короткий")
    res = await hf.probe()
    assert res["ok"] is False and res["stage"] == "ключ"
