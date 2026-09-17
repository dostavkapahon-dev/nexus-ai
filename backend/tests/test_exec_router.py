"""Порядок каналов считается, а не зашит.

§6/§14/§36 ТЗ: система должна выбирать канал выполнения по пригодности и
истории, а не идти по списку MCP → REST → браузер. Канал, который ни разу не
довёл задачу до файла, не должен идти первым только потому, что он «основной».
"""
import pytest

from core import exec_router as er

ALL = {"mcp": True, "rest": True, "browser": True}


@pytest.fixture(autouse=True)
def no_history(monkeypatch):
    async def blank():
        return {c: er._blank() for c in er.CHANNELS}
    monkeypatch.setattr(er, "stats", blank)


def _live(rows):
    return [r["channel"] for r in rows if r["use"]]


def _why(rows, channel):
    return next(r["why"] for r in rows if r["channel"] == channel)


@pytest.mark.asyncio
async def test_every_channel_is_listed_even_when_skipped():
    rows = await er.order("auto", "auto", {"mcp": False}, {})
    assert {r["channel"] for r in rows} == set(er.CHANNELS)


@pytest.mark.asyncio
async def test_unconfigured_channel_is_named_not_hidden():
    rows = await er.order("auto", "auto", {"mcp": False, "rest": True,
                                           "browser": True}, {})
    # У MCP причина своя: он авторизует пользователя, а не ключ, поэтому
    # человеку нужна команда входа, а не имя переменной.
    assert "/hfconnect" in _why(rows, "mcp")
    assert "mcp" not in _live(rows)


@pytest.mark.asyncio
async def test_mode_limits_to_one_channel():
    rows = await er.order("browser", "auto", ALL, {})
    assert _live(rows) == ["browser"]
    assert "режим" in _why(rows, "mcp")


@pytest.mark.asyncio
async def test_api_mode_selects_rest():
    rows = await er.order("api", "auto", ALL, {})
    assert _live(rows) == ["rest"]


@pytest.mark.asyncio
async def test_cooling_channel_says_when_to_retry():
    rows = await er.order("auto", "auto", ALL, {"mcp": 600})
    assert "пропущен — отказал недавно" in _why(rows, "mcp")
    assert "mcp" not in _live(rows)


@pytest.mark.asyncio
async def test_history_moves_the_working_channel_first(monkeypatch):
    async def history():
        data = {c: er._blank() for c in er.CHANNELS}
        data["mcp"].update(ok=0, fail=9)
        data["browser"].update(ok=9, fail=0, sec=40)
        return data
    monkeypatch.setattr(er, "stats", history)
    rows = await er.order("auto", "auto", ALL, {})
    assert _live(rows)[0] == "browser", "первым идёт тот, кто доводит до файла"


@pytest.mark.asyncio
async def test_economy_prefers_the_account_channel(monkeypatch):
    """В аккаунте безлимит — экономия означает браузер, а не платный ключ."""
    rows = await er.order("auto", "economy", ALL, {})
    assert _live(rows)[0] == "browser"


@pytest.mark.asyncio
async def test_fast_deprioritises_a_slow_channel(monkeypatch):
    async def history():
        data = {c: er._blank() for c in er.CHANNELS}
        data["browser"].update(ok=5, fail=0, sec=400)
        data["rest"].update(ok=5, fail=0, sec=20)
        return data
    monkeypatch.setattr(er, "stats", history)
    rows = await er.order("auto", "fast", ALL, {})
    assert _live(rows).index("rest") < _live(rows).index("browser")


@pytest.mark.asyncio
async def test_no_attempts_is_neither_praise_nor_burial():
    assert er.success_rate(er._blank()) == 0.5


@pytest.mark.asyncio
async def test_rate_counts_only_real_attempts():
    assert er.success_rate({"ok": 3, "fail": 1}) == 0.75


@pytest.mark.asyncio
async def test_text_names_the_order_and_every_reason():
    rows = await er.order("auto", "auto", {"mcp": False, "rest": True,
                                           "browser": True}, {"rest": 300})
    text = er.as_text(rows)
    assert "Порядок:" in text and "/hfconnect" in text and "повтор через" in text


@pytest.mark.asyncio
async def test_text_says_plainly_when_nothing_is_available():
    rows = await er.order("auto", "auto", {}, {})
    assert "генерация сейчас невозможна" in er.as_text(rows)
