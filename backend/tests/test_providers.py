"""Реестр провайдеров: «ключ задан» — это не «работает».

Требование ТЗ §37: разделить состояния. До сих пор система показывала
«подключено» по наличию ключа, и человек читал это как «сделает контент».
Четыре состояния существуют именно чтобы такое чтение стало невозможным.
"""
import pytest

from core import providers as pr


def _cap(monkeypatch, state, why="", when=""):
    async def fake_state(cap):
        return {"state": state, "why": why, "when": when, "evidence": ""}

    monkeypatch.setattr("core.capabilities.state", fake_state)


@pytest.mark.asyncio
async def test_no_key_is_not_configured(monkeypatch):
    monkeypatch.delenv("HIGGSFIELD_API_KEY", raising=False)
    monkeypatch.delenv("HIGGSFIELD_SECRET", raising=False)
    row = await pr.state({"id": "higgsfield", "name": "Higgsfield", "cap": "image",
                          "env": ("HIGGSFIELD_API_KEY", "HIGGSFIELD_SECRET"),
                          "does": "картинки"})
    assert row["status"] == pr.NOT_CONFIGURED


@pytest.mark.asyncio
async def test_key_alone_is_only_authenticated(monkeypatch):
    """Главное правило: ключ не делает провайдера рабочим."""
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "k")
    monkeypatch.setenv("HIGGSFIELD_SECRET", "s")
    _cap(monkeypatch, "unknown")
    row = await pr.state({"id": "higgsfield", "name": "Higgsfield", "cap": "image",
                          "env": ("HIGGSFIELD_API_KEY", "HIGGSFIELD_SECRET"),
                          "does": "картинки"})
    assert row["status"] == pr.AUTHENTICATED
    assert "настоящей работы ещё не было" in row["why"]


@pytest.mark.asyncio
async def test_real_result_makes_it_ready(monkeypatch):
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "k")
    monkeypatch.setenv("HIGGSFIELD_SECRET", "s")
    _cap(monkeypatch, "yes", when="16.09 08:09")
    row = await pr.state({"id": "higgsfield", "name": "Higgsfield", "cap": "image",
                          "env": ("HIGGSFIELD_API_KEY", "HIGGSFIELD_SECRET"),
                          "does": "картинки"})
    assert row["status"] == pr.READY and row["when"] == "16.09 08:09"


@pytest.mark.asyncio
async def test_failed_work_is_an_error_with_reason(monkeypatch):
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "k")
    monkeypatch.setenv("HIGGSFIELD_SECRET", "s")
    _cap(monkeypatch, "no", why="400 Unavailable model")
    row = await pr.state({"id": "higgsfield", "name": "Higgsfield", "cap": "image",
                          "env": ("HIGGSFIELD_API_KEY", "HIGGSFIELD_SECRET"),
                          "does": "картинки"})
    assert row["status"] == pr.ERROR and "Unavailable model" in row["why"]


@pytest.mark.asyncio
async def test_half_a_key_pair_is_not_configured(monkeypatch):
    """Ключ без секрета — не доступ; половина пары ничего не открывает."""
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "k")
    monkeypatch.delenv("HIGGSFIELD_SECRET", raising=False)
    row = await pr.state({"id": "higgsfield", "name": "Higgsfield", "cap": "image",
                          "env": ("HIGGSFIELD_API_KEY", "HIGGSFIELD_SECRET"),
                          "does": "картинки"})
    assert row["status"] == pr.NOT_CONFIGURED


@pytest.mark.asyncio
async def test_provider_without_proof_never_turns_green(monkeypatch):
    """У кого нечем доказать — тот остаётся жёлтым, а не зеленеет по ключу."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    row = await pr.state({"id": "anthropic", "name": "Claude", "cap": "",
                          "env": ("ANTHROPIC_API_KEY",), "does": "оркестратор"})
    assert row["status"] == pr.AUTHENTICATED


@pytest.mark.asyncio
async def test_text_counts_only_the_proven(monkeypatch):
    rows = [{"id": "a", "name": "A", "does": "x", "status": pr.READY,
             "why": "", "when": "16.09", "note": ""},
            {"id": "b", "name": "B", "does": "y", "status": pr.AUTHENTICATED,
             "why": "не проверен", "when": "", "note": ""},
            {"id": "c", "name": "C", "does": "z", "status": pr.ERROR,
             "why": "отказ", "when": "", "note": ""}]
    text = pr.as_text(rows)
    assert "Подтверждено работой: 1 из 3" in text
    assert "🟢 <b>A</b>" in text and "🟡 <b>B</b>" in text and "🔴 <b>C</b>" in text


@pytest.mark.asyncio
async def test_browser_state_comes_from_a_check_not_a_key(monkeypatch):
    async def fake_available(quick=False):
        return {"available": True, "where": "на сервере", "why": ""}

    monkeypatch.setattr("core.hixiit.browser_available", fake_available)
    monkeypatch.setattr("core.hixiit.higgsfield_session",
                        lambda: {"ok": True, "domains": ["higgsfield.ai"], "why": ""})
    row = await pr.state({"id": "browser", "name": "Браузер", "cap": "",
                          "env": (), "does": "сайты"})
    assert row["status"] == pr.AUTHENTICATED
    assert "вход в higgsfield.ai есть" in row["note"]


@pytest.mark.asyncio
async def test_drive_without_folder_is_not_configured(monkeypatch):
    monkeypatch.setattr("core.drive_store.configured",
                        lambda: {"ok": False, "why": "не задан GOOGLE_DRIVE_FOLDER_ID"})
    row = await pr.state({"id": "drive", "name": "Google Drive", "cap": "",
                          "env": (), "does": "архив"})
    assert row["status"] == pr.NOT_CONFIGURED
    assert "GOOGLE_DRIVE_FOLDER_ID" in row["why"]
