"""Когда таймаутит всё подряд — надо мерить, а не гадать.

С живого сервера трижды приходила одна и та же картина: Telegram и Groq
отвечают, а DuckDuckGo, Mojeek, браузер и Higgsfield молчат все разом. У такого
три разные причины — выборочная сеть хостинга, нехватка памяти и занятый
событийный цикл, — и лечатся они по-разному. Замер их различает.
"""
import pytest

from core import netcheck as nc


def test_verdict_names_a_busy_loop():
    """Если цикл занят, «сайт не ответил» — это не про сайт."""
    text = nc.as_text({"targets": [{"name": "A", "ok": False, "code": "Timeout",
                                    "sec": 8.0}],
                       "lag_before": 0.0, "lag_after": 3.5, "memory": {}})
    assert "цикл занят" in text


def test_verdict_names_memory_pressure():
    text = nc.as_text({"targets": [{"name": "A", "ok": False, "code": "Timeout",
                                    "sec": 8.0}],
                       "lag_before": 0.0, "lag_after": 0.0,
                       "memory": {"rss_mb": 470.0, "limit_mb": 512.0}})
    assert "память на исходе" in text


def test_verdict_names_selective_network():
    text = nc.as_text({
        "targets": [{"name": "Telegram API", "ok": True, "code": 200, "sec": 0.2},
                    {"name": "Mojeek", "ok": False, "code": "Timeout", "sec": 8.0}],
        "lag_before": 0.0, "lag_after": 0.0, "memory": {"rss_mb": 100.0}})
    assert "выборочно" in text and "Mojeek" in text


def test_verdict_when_everything_works():
    text = nc.as_text({
        "targets": [{"name": "A", "ok": True, "code": 200, "sec": 0.2}],
        "lag_before": 0.0, "lag_after": 0.0, "memory": {"rss_mb": 100.0}})
    assert "причина таймаутов не здесь" in text


def test_absent_memory_limit_is_not_reported_as_petabytes():
    """Ядро пишет «без лимита» гигантским числом — это не 8 петабайт."""
    mem = nc.memory()
    assert mem["limit_mb"] == 0 or mem["limit_mb"] < 1_000_000


@pytest.mark.asyncio
async def test_each_address_is_measured_separately(monkeypatch):
    """Пачкой мерить нельзя: она маскирует нехватку ресурсов у процесса."""
    seen = []

    async def fake_one(name, url):
        seen.append(name)
        return {"name": name, "ok": True, "code": 200, "sec": 0.1}

    monkeypatch.setattr(nc, "_one", fake_one)
    report = await nc.run()
    assert seen == [t[0] for t in nc.TARGETS]
    assert len(report["targets"]) == len(nc.TARGETS)


@pytest.mark.asyncio
async def test_failure_of_one_address_does_not_stop_the_rest(monkeypatch):
    async def fake_one(name, url):
        if name == "Google":
            return {"name": name, "ok": False, "code": "Timeout", "sec": 8.0}
        return {"name": name, "ok": True, "code": 200, "sec": 0.1}

    monkeypatch.setattr(nc, "_one", fake_one)
    report = await nc.run()
    assert len(report["targets"]) == len(nc.TARGETS)
