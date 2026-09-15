"""Самопроверка не выдаёт доступ за работу и не обрезает причину отказа.

Две конкретные жалобы с живого сервера:
  * «Higgsfield ✅ доступ подтверждён» — при том, что генерация ни разу не
    проверялась. Зелёная галочка означала ключ, а человек читал «работает».
  * причина отказа поиска обрывалась на середине последнего источника («http»),
    а именно он и был интересен.
"""
import pytest

from core import system_test, capabilities


@pytest.fixture
def access(monkeypatch):
    async def fake_status():
        return {"mcp_ok": False, "api_ok": True, "browser_agent": False,
                "credits": None, "api_error": "", "mcp_error": ""}

    monkeypatch.setattr("core.hixiit.status", fake_status)


def _proof(monkeypatch, state, why="", when="15.09 03:29", evidence=""):
    async def fake_state(cap):
        return {"state": state, "why": why, "when": when, "evidence": evidence}

    monkeypatch.setattr(capabilities, "state", fake_state)


@pytest.mark.asyncio
async def test_access_without_generation_is_not_green(access, monkeypatch):
    _proof(monkeypatch, "unknown", "настоящей попытки ещё не было")
    res = await system_test.check_hixiit(deep=False)
    assert res["warn"] is True
    assert "ни разу не" in res["evidence"]


@pytest.mark.asyncio
async def test_confirmed_generation_makes_it_green(access, monkeypatch):
    _proof(monkeypatch, "yes", evidence="https://cdn/x.png")
    res = await system_test.check_hixiit(deep=False)
    assert res["ok"] and not res.get("warn")
    assert "получалась" in res["detail"]


@pytest.mark.asyncio
async def test_failed_generation_makes_it_red(access, monkeypatch):
    _proof(monkeypatch, "no", why="400 Unavailable model")
    res = await system_test.check_hixiit(deep=False)
    assert res["ok"] is False
    assert "Unavailable model" in res["detail"]


@pytest.mark.asyncio
async def test_unchecked_does_not_count_as_passed(monkeypatch):
    """Итог «все проверки пройдены» не собирается из непроверенного."""
    async def one_warn():
        r = system_test._ok("Higgsfield", "доступ", "не проверялось")
        r["warn"] = True
        return r

    monkeypatch.setattr(system_test, "CHECKS", (one_warn,))
    report = await system_test.run()
    assert report["ok"] is False and report["passed"] == 0
    text = system_test.as_text(report)
    assert "непроверенных: 1" in text
    assert text.count("⚠️ <b>Higgsfield</b>") == 1


@pytest.mark.asyncio
async def test_search_failure_reason_is_not_cut_in_half(monkeypatch):
    long_reason = ("поиск не дал результатов — perplexity: нет ключа "
                   "PERPLEXITY_API_KEY; duckduckgo: " + "x" * 120
                   + "; браузер: страница показала проверку на робота")

    async def fake_search(q, n=8, budget=60.0):
        return {"ok": False, "items": [], "error": long_reason}

    monkeypatch.setattr("core.websearch.search", fake_search)
    res = await system_test.check_search()
    assert res["ok"] is False
    # Последний источник — самый интересный — обязан дойти целиком.
    assert "браузер: страница показала проверку на робота" in res["detail"]
