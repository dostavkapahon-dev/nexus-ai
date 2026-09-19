"""Заведомо нерабочий канал — не запасной вариант, а ловушка.

Браузер считался доступным всегда. Задача честно доходила до него последним
шагом, пыталась поднять Chromium, и на маленьком инстансе ядро убивало весь
сервис: «Сервер перезапустился» каждые четыре минуты. Теперь канал отвечает
заранее и называет причину.
"""
import pytest

from core import server_browser as sb, exec_router


@pytest.fixture(autouse=True)
def no_cloud(monkeypatch):
    monkeypatch.delenv("NEXUS_BROWSER_CDP", raising=False)
    monkeypatch.delenv("BRIGHTDATA_BROWSER_URL", raising=False)
    monkeypatch.setenv("NEXUS_SERVER_BROWSER", "1")


def test_small_instance_without_cloud_browser_says_no(monkeypatch):
    monkeypatch.setattr(sb, "available_mb", lambda: 120.0)
    monkeypatch.setattr(sb, "MIN_FREE_MB", 300.0)
    ok, why = sb.usable_now()
    assert ok is False
    assert "120" in why and "NEXUS_BROWSER_CDP" in why


def test_cloud_browser_needs_no_local_memory(monkeypatch):
    monkeypatch.setenv("NEXUS_BROWSER_CDP", "wss://user:pass@host:9222")
    monkeypatch.setattr(sb, "available_mb", lambda: 50.0)
    assert sb.usable_now() == (True, "")


def test_disabled_by_flag(monkeypatch):
    monkeypatch.setenv("NEXUS_SERVER_BROWSER", "0")
    ok, why = sb.usable_now()
    assert ok is False and "NEXUS_SERVER_BROWSER" in why


def test_roomy_machine_keeps_the_browser(monkeypatch):
    monkeypatch.setattr(sb, "available_mb", lambda: 4000.0)
    assert sb.usable_now() == (True, "")


@pytest.mark.asyncio
async def test_router_prints_the_real_reason(monkeypatch):
    async def blank():
        return {c: exec_router._blank() for c in exec_router.CHANNELS}

    monkeypatch.setattr(exec_router, "stats", blank)
    rows = await exec_router.order(
        "auto", "auto",
        configured={"mcp": True, "rest": True, "browser": False},
        missing={"browser": "не хватит памяти — задайте NEXUS_BROWSER_CDP"})
    browser = next(r for r in rows if r["channel"] == "browser")
    assert browser["use"] is False
    assert "памяти" in browser["why"]
    # Остальные каналы при этом работают: отказ одного не отменяет генерацию.
    assert [r["channel"] for r in rows if r["use"]] == ["mcp", "rest"]
