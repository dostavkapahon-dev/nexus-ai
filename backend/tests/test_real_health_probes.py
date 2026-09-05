"""Диагностика должна подтверждать статус настоящим вызовом.

Зелёный статус только потому, что ключ записан в настройках, — худший вид
ложной уверенности: человек считает, что всё подключено, и ищет поломку в
другом месте.
"""
import pytest

from core import health


@pytest.mark.asyncio
async def test_memory_probe_writes_and_reads_back(client):
    res = await health._probe_memory()

    assert "detail" in res
    # В тестах база временная, поэтому «не переживёт перезапуск» — честный ответ.
    assert res["ok"] or "перезапуск" in res["detail"]


@pytest.mark.asyncio
async def test_telegram_probe_is_not_fooled_by_a_present_token(client, monkeypatch):
    """Токен задан, но недействителен — это красный статус, а не зелёный."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:invalid")

    class FakeResponse:
        @staticmethod
        def json():
            return {"ok": False, "description": "Unauthorized"}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            return FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: FakeClient())

    res = await health._probe_telegram()

    assert res["ok"] is False
    assert "Unauthorized" in res["detail"]


@pytest.mark.asyncio
async def test_probe_all_never_raises(client, monkeypatch):
    """Один упавший сервис не должен ломать всю диагностику."""
    async def boom():
        raise RuntimeError("сервис недоступен")

    monkeypatch.setitem(health.PROBES, "Сломанный", boom)

    results = await health.probe_all()
    broken = [r for r in results if r["name"] == "Сломанный"]

    assert broken and broken[0]["ok"] is False
    assert "сервис недоступен" in broken[0]["detail"]
    assert len(results) == len(health.PROBES), "остальные проверки должны отработать"


@pytest.mark.asyncio
async def test_slow_service_does_not_hang_diagnostics(client, monkeypatch):
    """Диагностику открывают, когда что-то не работает — она не может зависнуть."""
    import asyncio

    async def never():
        await asyncio.sleep(300)

    monkeypatch.setitem(health.PROBES, "Зависший", never)
    monkeypatch.setattr("asyncio.wait_for", _immediate_timeout)

    results = await health.probe_all()
    hung = [r for r in results if r["name"] == "Зависший"][0]

    assert hung["ok"] is False


async def _immediate_timeout(coro, timeout=None):
    import asyncio
    coro.close()
    raise asyncio.TimeoutError
