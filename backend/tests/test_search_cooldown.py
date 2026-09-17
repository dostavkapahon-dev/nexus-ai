"""Недоступный источник не должен каждый раз съедать время рабочего.

Симптом из самопроверки: поиск падал, потратив по 8 секунд на DuckDuckGo и
Mojeek (с этого хоста они не открываются вовсе — замер /netcheck), после чего
браузеру — единственному рабочему пути — осталось 13 секунд, и он не успел.
"""
import pytest

from core import websearch as ws


@pytest.fixture(autouse=True)
def clean():
    ws._DEAD.clear()
    yield
    ws._DEAD.clear()


def test_connect_timeout_is_remembered():
    ws._mark_dead("mojeek", "ConnectTimeout")
    assert "недоступен" in ws._dead_reason("mojeek")


def test_quota_is_remembered_separately():
    ws._mark_dead("google", "429 You exceeded your current quota")
    assert "квота" in ws._dead_reason("google")


def test_ordinary_failure_is_not_remembered():
    """«Пусто» или «нет ссылок» повторится не обязательно — не баним."""
    ws._mark_dead("google", "Google не вернул ссылок на эту тему")
    assert ws._dead_reason("google") == ""


def test_reason_names_when_we_try_again():
    ws._mark_dead("duckduckgo", "ConnectError")
    assert "мин" in ws._dead_reason("duckduckgo")


def test_unknown_source_is_not_skipped():
    assert ws._dead_reason("браузер") == ""


@pytest.mark.asyncio
async def test_dead_source_is_skipped_and_named(monkeypatch):
    calls = []

    async def never(query, n):
        calls.append("ddg")
        raise RuntimeError("не должно вызываться")

    async def works(query, n):
        return [{"title": "t", "url": "https://e.com", "snippet": ""}]

    monkeypatch.setattr(ws, "_search_perplexity", _nokey)
    monkeypatch.setattr(ws, "_search_gemini", _nokey)
    monkeypatch.setattr(ws, "_search_ddg", never)
    monkeypatch.setattr(ws, "_search_mojeek", _nokey)
    monkeypatch.setattr(ws, "_search_browser", works)
    ws._mark_dead("duckduckgo", "ConnectTimeout")

    res = await ws.search("тема", budget=5)

    assert res["ok"] is True and res["provider"] == "браузер"
    assert calls == [], "забаненный источник не должен вызываться"


async def _nokey(query, n):
    raise ws.NoKey("нет ключа")
