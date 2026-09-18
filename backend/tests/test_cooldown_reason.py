"""«Пропущен — отказал недавно» не говорит, что чинить.

Ровно это и приходило в самопроверке: все три канала Higgsfield помечены
«отказал недавно, повтор через 9 мин», а из-за чего именно отказали — нигде.
Причина сохранялась в аргументе `why` и молча выбрасывалась.
"""
import pytest

from core import hixiit, exec_router


def test_reason_is_remembered_with_the_cooldown():
    hixiit._chill("mcp", "вход не выполнен — /hfconnect")
    assert "hfconnect" in hixiit.cold_reason("mcp")


def test_success_clears_both():
    hixiit._chill("rest", "400 Unavailable model")
    hixiit._warm("rest")
    assert hixiit.cold_reason("rest") == ""
    assert hixiit._cold("rest") == 0.0


def test_no_cooldown_means_no_reason():
    assert hixiit.cold_reason("browser") == ""


@pytest.mark.asyncio
async def test_router_shows_the_reason():
    rows = await exec_router.order(
        "auto", "auto",
        configured={"mcp": True, "rest": True, "browser": True},
        cooling={"mcp": 540.0},
        reasons={"mcp": "400 Unavailable model"})
    mcp = next(r for r in rows if r["channel"] == "mcp")
    assert mcp["use"] is False
    assert "Unavailable model" in mcp["why"]
    assert "9 мин" in mcp["why"], "срок тоже нужен — он говорит, когда повторит"


@pytest.mark.asyncio
async def test_router_without_reason_keeps_the_old_wording():
    rows = await exec_router.order(
        "auto", "auto",
        configured={"mcp": True, "rest": True, "browser": True},
        cooling={"rest": 300.0})
    rest = next(r for r in rows if r["channel"] == "rest")
    assert "отказал недавно" in rest["why"]


@pytest.mark.asyncio
async def test_reason_survives_restart_through_history(monkeypatch):
    """Память процесса гибнет при деплое, история в базе — нет.

    После перезапуска оставалось «пропущен — отказал недавно» без причины:
    причина жила только в памяти. Теперь недостающее берётся из истории
    маршрутов, которая лежит в базе.
    """
    async def fake_stats():
        blank = exec_router._blank()
        return {"mcp": {**blank, "fail": 3,
                        "last_error": "вход не выполнен — /hfconnect"},
                "rest": dict(blank), "browser": dict(blank)}

    monkeypatch.setattr(exec_router, "stats", fake_stats)
    rows = await exec_router.order(
        "auto", "auto",
        configured={"mcp": True, "rest": True, "browser": True},
        cooling={"mcp": 240.0})            # причины в памяти нет
    mcp = next(r for r in rows if r["channel"] == "mcp")
    assert "hfconnect" in mcp["why"]


@pytest.mark.asyncio
async def test_available_channel_shows_its_last_failure(monkeypatch):
    async def fake_stats():
        blank = exec_router._blank()
        return {"mcp": {**blank, "ok": 1, "fail": 1,
                        "last_error": "400 Unavailable model"},
                "rest": dict(blank), "browser": dict(blank)}

    monkeypatch.setattr(exec_router, "stats", fake_stats)
    rows = await exec_router.order(
        "auto", "auto", configured={"mcp": True, "rest": True, "browser": True})
    assert "Unavailable model" in exec_router.as_text(rows)


@pytest.mark.asyncio
async def test_system_test_adds_channel_errors_from_history(monkeypatch):
    """В отчёте самопроверки должно быть видно, что ответила платформа."""
    from core import system_test, exec_router

    async def fake_stats():
        blank = exec_router._blank()
        return {"mcp": {**blank, "last_error": "вход не выполнен"},
                "rest": {**blank, "last_error": "400 Unavailable model"},
                "browser": dict(blank)}

    monkeypatch.setattr(exec_router, "stats", fake_stats)
    text = await system_test._channel_errors()
    assert "Unavailable model" in text and "вход не выполнен" in text
    assert "Браузер" not in text, "канал без отказов в список не попадает"
