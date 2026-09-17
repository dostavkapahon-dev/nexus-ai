"""Браузер ищет там, куда с этого сервера вообще можно дойти.

Раньше здесь стоял единственный адрес — Mojeek, — который с хостинга не
открывается ни по http, ни браузером: браузер сидит на том же хосте. Поиск
ждал страницу, которой не будет.
"""
import pytest

from core import websearch as ws


def test_google_is_tried_first():
    assert "google.com" in ws._BROWSER_ENGINES[0]


def test_engines_are_named_for_humans():
    names = [ws._engine_name(u) for u in ws._BROWSER_ENGINES]
    assert names[:2] == ["google", "lite"] or names[0] == "google"


@pytest.mark.asyncio
async def test_falls_through_to_the_engine_that_opens(monkeypatch):
    opened = []

    async def fake_open(url, timeout_ms=0):
        opened.append(url)
        if "google" in url:
            return {"ok": False, "error": "timeout"}
        if "duckduckgo" in url:
            return {"ok": True, "text": "unusual traffic detected"}
        return {"ok": True, "text": "Заголовок — https://found.example"}

    async def fake_extract(sys, prompt):
        return {"items": [{"title": "Заголовок", "url": "https://found.example",
                           "snippet": "суть"}]}

    async def available(quick=False):
        return {"available": True, "why": ""}

    monkeypatch.setattr("core.browser_reader._open_text", fake_open)
    monkeypatch.setattr("core.browser_reader._extract", fake_extract)
    monkeypatch.setattr("core.hixiit.browser_available", available)

    items = await ws._search_browser("тема", 5)

    assert items and items[0]["url"] == "https://found.example"
    assert len(opened) >= 3, "должен был перебрать недоступные выдачи"


@pytest.mark.asyncio
async def test_reason_names_every_engine_when_all_fail(monkeypatch):
    async def fake_open(url, timeout_ms=0):
        return {"ok": True, "text": "captcha"}

    async def available(quick=False):
        return {"available": True, "why": ""}

    monkeypatch.setattr("core.browser_reader._open_text", fake_open)
    monkeypatch.setattr("core.hixiit.browser_available", available)

    with pytest.raises(RuntimeError) as e:
        await ws._search_browser("тема", 5)
    assert "google" in str(e.value) and "робот" in str(e.value)
