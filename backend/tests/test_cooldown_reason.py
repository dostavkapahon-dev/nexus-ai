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
