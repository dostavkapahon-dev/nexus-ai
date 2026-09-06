"""Сервис не должен зависеть от того, открыт ли сайт.

Telegram-бот работает внутри серверного процесса. На бесплатном Render этот
процесс засыпает без входящих запросов — и бот замолкает до тех пор, пока
кто-нибудь не откроет адрес. Снаружи это неотличимо от «работает только с сайтом».
"""
import pytest
import httpx

from core import keepalive


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for var in ("RENDER_EXTERNAL_URL", "NEXUS_PUBLIC_URL", "NEXUS_KEEPALIVE"):
        monkeypatch.delenv(var, raising=False)
    yield


def test_off_without_known_address(monkeypatch):
    """Без адреса пинговать некуда — говорим об этом прямо, а не молчим."""
    st = keepalive.status()
    assert st["on"] is False
    assert "адрес" in st["reason"]


def test_on_when_render_gives_the_address(monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://nexus.example.com/")
    st = keepalive.status()
    assert st["on"] is True
    assert st["url"] == "https://nexus.example.com"
    assert st["interval_sec"] < 15 * 60, "Render усыпляет через 15 минут"


def test_can_be_switched_off(monkeypatch):
    """На платном тарифе или при внешней пинговалке самопинг не нужен."""
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://nexus.example.com")
    monkeypatch.setenv("NEXUS_KEEPALIVE", "off")
    assert keepalive.status()["on"] is False


@pytest.mark.asyncio
async def test_ping_hits_own_health_endpoint(monkeypatch):
    monkeypatch.setenv("NEXUS_PUBLIC_URL", "https://nexus.example.com")
    seen = {}

    class Fake:
        def __call__(self, *a, **kw):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            seen["url"] = url
            return httpx.Response(200, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "AsyncClient", Fake())

    assert await keepalive.ping_once() is True
    assert seen["url"] == "https://nexus.example.com/api/health"


@pytest.mark.asyncio
async def test_ping_failure_is_not_fatal(monkeypatch):
    """Фоновая задача не должна ронять процесс из-за сетевой ошибки."""
    monkeypatch.setenv("NEXUS_PUBLIC_URL", "https://nexus.example.com")

    class Boom:
        def __call__(self, *a, **kw):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            raise httpx.ConnectError("нет сети")

    monkeypatch.setattr(httpx, "AsyncClient", Boom())
    assert await keepalive.ping_once() is False
