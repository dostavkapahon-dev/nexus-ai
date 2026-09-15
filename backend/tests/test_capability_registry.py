"""Реестр возможностей: «умею» только при доказательстве настоящего результата.

Требование v3.0 §79–§80: никаких ложных capabilities. Заявленная в коде функция,
заданный ключ и зелёный `/diag` не дают права обещать пользователю результат —
его даёт только сам результат.
"""
import json
from datetime import datetime, timedelta

import pytest

from core import capabilities


class _Store(dict):
    """Подмена KV: реестр хранит записи в таблице Connection."""


@pytest.fixture
def store(monkeypatch):
    data = _Store()

    async def fake_record(cap, ok, why="", evidence=""):
        data[cap] = {"ok": bool(ok), "why": why, "evidence": evidence,
                     "when": datetime.utcnow().isoformat()}

    async def fake_stored(cap):
        return data.get(cap, {})

    monkeypatch.setattr(capabilities, "record", fake_record)
    monkeypatch.setattr(capabilities, "_stored", fake_stored)
    return data


@pytest.mark.asyncio
async def test_without_proof_state_is_unknown_not_yes(store):
    st = await capabilities.state("image")
    assert st["state"] == "unknown"
    assert not await capabilities.can("image")


@pytest.mark.asyncio
async def test_real_result_makes_it_yes(store):
    await capabilities.record("image", True, "", "https://cdn/x.png")
    assert await capabilities.can("image")
    assert (await capabilities.state("image"))["state"] == "yes"


@pytest.mark.asyncio
async def test_failure_is_red_with_reason(store):
    await capabilities.record("video", False, "400 Unavailable model")
    st = await capabilities.state("video")
    assert st["state"] == "no"
    assert "Unavailable model" in st["why"]
    assert not await capabilities.can("video")


@pytest.mark.asyncio
async def test_stale_proof_stops_counting(store):
    store["image"] = {"ok": True, "why": "", "evidence": "",
                      "when": (datetime.utcnow()
                               - timedelta(hours=capabilities.PROOF_HOURS + 1)).isoformat()}
    st = await capabilities.state("image")
    assert st["state"] == "unknown"
    assert not await capabilities.can("image")


@pytest.mark.asyncio
async def test_unknown_key_is_not_promised(store):
    assert not await capabilities.can("teleportation")


@pytest.mark.asyncio
async def test_text_never_says_umeyu_without_proof(store):
    text = capabilities.as_text(await capabilities.registry())
    assert "умею" not in text.replace("не проверено", "")
    assert "не проверено" in text


@pytest.mark.asyncio
async def test_text_marks_confirmed_capability(store):
    await capabilities.record("search", True, "", "duckduckgo: 5 результатов")
    text = capabilities.as_text(await capabilities.registry())
    assert "✅ <b>Поиск в интернете</b> — умею" in text


@pytest.mark.asyncio
async def test_generation_writes_to_registry(monkeypatch):
    """Запись делает рабочий путь генерации, а не отдельная проверка."""
    from core import hixiit
    seen = {}

    async def fake_raw(task, kind="auto", ratio=None, image_url=None, allow_free=True, force=False):
        return {"ok": True, "url": "https://cdn/a.png", "kind": "image"}

    async def fake_record(cap, ok, why="", evidence=""):
        seen.update(cap=cap, ok=ok)

    monkeypatch.setattr(hixiit, "_generate_once_raw", fake_raw)
    monkeypatch.setattr(capabilities, "record", fake_record)
    res = await hixiit._generate_once("кадр")
    assert res["url"] == "https://cdn/a.png"
    assert seen == {"cap": "image", "ok": True}


@pytest.mark.asyncio
async def test_failed_generation_recorded_as_failure(monkeypatch):
    from core import hixiit
    seen = {}

    async def fake_raw(task, kind="auto", ratio=None, image_url=None, allow_free=True, force=False):
        return {"ok": False, "error": "все пути отказали"}

    async def fake_record(cap, ok, why="", evidence=""):
        seen.update(cap=cap, ok=ok, why=why)

    monkeypatch.setattr(hixiit, "_generate_once_raw", fake_raw)
    monkeypatch.setattr(capabilities, "record", fake_record)
    await hixiit._generate_once("ролик про шашлык")
    assert seen["ok"] is False
    assert "отказали" in seen["why"]


@pytest.mark.asyncio
async def test_registry_never_raises_into_the_work(monkeypatch):
    """Наблюдатель не имеет права уронить саму генерацию."""
    from core import hixiit

    async def fake_raw(task, kind="auto", ratio=None, image_url=None, allow_free=True, force=False):
        return {"ok": True, "url": "https://cdn/a.png", "kind": "image"}

    async def boom(*a, **k):
        raise RuntimeError("БД недоступна")

    monkeypatch.setattr(hixiit, "_generate_once_raw", fake_raw)
    monkeypatch.setattr(capabilities, "record", boom)
    res = await hixiit._generate_once("кадр")
    assert res["ok"] and res["url"]


@pytest.mark.asyncio
async def test_search_records_its_outcome(monkeypatch):
    from core import websearch
    seen = {}

    async def fake_record(cap, ok, why="", evidence=""):
        seen.update(cap=cap, ok=ok)

    monkeypatch.setattr(capabilities, "record", fake_record)

    async def nothing(q, n):
        return []

    monkeypatch.setattr(websearch, "_search_perplexity", nothing)
    monkeypatch.setattr(websearch, "_search_ddg", nothing)
    monkeypatch.setattr(websearch, "_search_browser", nothing)
    res = await websearch.search("тест", budget=1.0)
    assert res["ok"] is False
    assert seen == {"cap": "search", "ok": False}


@pytest.mark.asyncio
async def test_director_prompt_carries_real_capabilities(monkeypatch):
    """Дирижёр планирует по фактам, а не по списку существующих инструментов."""
    from core import marketing_director as md

    async def fake_registry():
        return [{"id": "video", "human": "Видео", "state": "no",
                 "why": "все пути отказали", "when": "", "evidence": ""},
                {"id": "image", "human": "Картинка", "state": "yes",
                 "why": "", "when": "15.09", "evidence": ""}]

    monkeypatch.setattr(capabilities, "registry", fake_registry)
    prompt = await md._full_system()
    assert "ЧТО ПОДТВЕРЖДЕНО РЕЗУЛЬТАТОМ" in prompt
    assert "не работает: Видео" in prompt
    assert "умею: Картинка" in prompt


@pytest.mark.asyncio
async def test_director_prompt_survives_broken_registry(monkeypatch):
    """Реестр — наблюдатель: его поломка не должна лишать дирижёра промпта."""
    from core import marketing_director as md

    async def boom():
        raise RuntimeError("БД недоступна")

    monkeypatch.setattr(capabilities, "registry", boom)
    assert await md._full_system()
