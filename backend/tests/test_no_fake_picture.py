"""Подделка вместо отказа — хуже отказа.

С живого сервера: на просьбу сделать кадр пришла картинка чужого бесплатного
сервиса с его водяным знаком. Higgsfield не сработал ни одним путём, но об этом
не было сказано ни слова — человек получил «не то, что просил», и не узнал,
что чинить.
"""
import pytest

from core import hixiit


def _const(value):
    async def fn(*a, **k):
        return value
    return fn


@pytest.fixture
def all_paths_dead(monkeypatch):
    monkeypatch.setattr(hixiit, "execution_mode", _const("auto"))
    monkeypatch.setattr(hixiit, "mcp_configured", lambda: False)
    monkeypatch.setattr("core.higgsfield.credentials", lambda: None)
    monkeypatch.setattr(hixiit, "browser_available", _const(
        {"available": False, "where": "", "why": "браузер не запускается"}))


@pytest.mark.asyncio
async def test_no_free_picture_by_default(monkeypatch, all_paths_dead):
    monkeypatch.delenv("NEXUS_FREE_DRAFT", raising=False)

    def must_not_draw(*a, **k):
        raise AssertionError("бесплатный генератор не должен подменять результат")

    monkeypatch.setattr("core.skills.free_image", must_not_draw)
    res = await hixiit._generate_once_raw("шашлык", kind="image")
    assert res["ok"] is False
    assert "браузер не запускается" in res["error"]


@pytest.mark.asyncio
async def test_refusal_says_how_to_enable_the_draft(monkeypatch, all_paths_dead):
    monkeypatch.delenv("NEXUS_FREE_DRAFT", raising=False)
    res = await hixiit._generate_once_raw("шашлык", kind="image")
    assert "водяной знак" in res["error"]
    assert "NEXUS_FREE_DRAFT" in res["error"], "отказ обязан сказать, как включить черновик"


@pytest.mark.asyncio
async def test_draft_still_available_when_asked_for(monkeypatch, all_paths_dead):
    """Запретить совсем нельзя: иногда черновик нужен — но по явному согласию."""
    monkeypatch.setenv("NEXUS_FREE_DRAFT", "1")
    monkeypatch.setattr("core.skills.free_image",
                        lambda task, vertical=True: "https://free/x.png")
    res = await hixiit._generate_once_raw("шашлык", kind="image")
    assert res["ok"] and res["provider"] == "pollinations_free"
    assert "бесплатный генератор" in res["note"]


@pytest.mark.asyncio
async def test_video_never_had_a_free_path(monkeypatch, all_paths_dead):
    monkeypatch.setenv("NEXUS_FREE_DRAFT", "1")
    res = await hixiit._generate_once_raw("ролик", kind="video")
    assert res["ok"] is False


def test_draft_is_off_unless_explicitly_turned_on(monkeypatch):
    monkeypatch.delenv("NEXUS_FREE_DRAFT", raising=False)
    assert hixiit.free_draft_allowed() is False
    monkeypatch.setenv("NEXUS_FREE_DRAFT", "0")
    assert hixiit.free_draft_allowed() is False
    monkeypatch.setenv("NEXUS_FREE_DRAFT", "on")
    assert hixiit.free_draft_allowed() is True
