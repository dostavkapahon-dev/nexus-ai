"""Модели берутся из каталога провайдера и проверяются результатом.

Список моделей в коде трижды разошёлся с действительностью: платформа отвечала
«Unavailable model», а имена менялись наугад. Код не может знать, что доступно
аккаунту сегодня, — это знает только провайдер. Поэтому каталог приходит от
него, а «работает» подтверждается настоящей генерацией, а не записью в списке.
"""
import pytest

from core import model_registry as mr


@pytest.fixture(autouse=True)
def store(monkeypatch):
    data = {}

    async def fake_load(provider):
        return data.get(provider, {})

    async def fake_save(provider, payload):
        data[provider] = payload

    monkeypatch.setattr(mr, "_load", fake_load)
    monkeypatch.setattr(mr, "_save", fake_save)
    return data


@pytest.mark.asyncio
async def test_discovered_model_is_not_ready():
    await mr.remember_catalog("higgsfield", [{"id": "soul_2", "kind": "image"}],
                              source="MCP")
    rows = await mr.catalog("higgsfield")
    assert rows[0]["status"] == mr.DISCOVERED
    assert "не проверена" in mr.as_text(rows, "Картинки")


@pytest.mark.asyncio
async def test_real_result_makes_it_ready():
    await mr.remember_catalog("higgsfield", [{"id": "soul_2", "kind": "image"}], "MCP")
    await mr.mark_result("higgsfield", "soul_2", True)
    assert (await mr.catalog("higgsfield"))[0]["status"] == mr.READY


@pytest.mark.asyncio
async def test_failure_keeps_the_reason():
    await mr.remember_catalog("higgsfield", [{"id": "z_image", "kind": "image"}], "MCP")
    await mr.mark_result("higgsfield", "z_image", False, "400 Unavailable model")
    row = (await mr.catalog("higgsfield"))[0]
    assert row["status"] == mr.FAILED
    assert "Unavailable model" in row["last_error"]


@pytest.mark.asyncio
async def test_rediscovery_does_not_forget_what_worked():
    """Переобнаружение не должно разжаловать модель, уже доказавшую работу."""
    await mr.remember_catalog("higgsfield", [{"id": "soul_2", "kind": "image"}], "MCP")
    await mr.mark_result("higgsfield", "soul_2", True)
    await mr.remember_catalog("higgsfield", [{"id": "soul_2", "kind": "image"},
                                             {"id": "z_image", "kind": "image"}], "MCP")
    rows = {r["id"]: r for r in await mr.catalog("higgsfield")}
    assert rows["soul_2"]["status"] == mr.READY
    assert rows["z_image"]["status"] == mr.DISCOVERED


@pytest.mark.asyncio
async def test_model_that_left_the_catalog_disappears():
    await mr.remember_catalog("higgsfield", [{"id": "old_model", "kind": "image"}], "MCP")
    await mr.remember_catalog("higgsfield", [{"id": "new_model", "kind": "image"}], "MCP")
    assert [r["id"] for r in await mr.catalog("higgsfield")] == ["new_model"]


@pytest.mark.asyncio
async def test_proven_models_are_tried_first():
    await mr.remember_catalog("higgsfield", [
        {"id": "a", "kind": "image"}, {"id": "b", "kind": "image"},
        {"id": "c", "kind": "image"}], "MCP")
    await mr.mark_result("higgsfield", "c", True)
    await mr.mark_result("higgsfield", "a", False, "отказ")
    order = await mr.usable("higgsfield", "image")
    assert order[0] == "c" and order[-1] == "a", "провалившаяся — в конец, не в бан"


@pytest.mark.asyncio
async def test_kinds_are_not_mixed():
    await mr.remember_catalog("higgsfield", [
        {"id": "soul_2", "kind": "image"}, {"id": "kling", "kind": "video"}], "MCP")
    assert [r["id"] for r in await mr.catalog("higgsfield", "video")] == ["kling"]


@pytest.mark.asyncio
async def test_freshness_reports_source_and_age():
    await mr.remember_catalog("higgsfield", [{"id": "x", "kind": "image"}],
                              source="MCP models_explore")
    fresh = await mr.freshness("higgsfield")
    assert fresh["source"] == "MCP models_explore"
    assert fresh["count"] == 1 and fresh["stale"] is False


@pytest.mark.asyncio
async def test_empty_catalog_says_so_instead_of_lying():
    assert "Каталог пуст" in mr.as_text(await mr.catalog("higgsfield"), "Картинки")


@pytest.mark.asyncio
async def test_generation_writes_the_model_result(monkeypatch):
    """Рабочий путь обязан записывать, какая модель сработала."""
    from core import hixiit, capabilities
    seen = {}

    async def fake_raw(task, kind="auto", ratio=None, image_url=None, allow_free=True):
        return {"ok": True, "url": "https://cdn/x.png", "kind": "image",
                "model": "soul_2"}

    async def fake_mark(provider, model, ok, error=""):
        seen.update(provider=provider, model=model, ok=ok)

    async def noop(*a, **k):
        return None

    monkeypatch.setattr(hixiit, "_generate_once_raw", fake_raw)
    monkeypatch.setattr(capabilities, "record", noop)
    monkeypatch.setattr(mr, "mark_result", fake_mark)
    await hixiit._generate_once("кадр")
    assert seen == {"provider": "higgsfield", "model": "soul_2", "ok": True}


@pytest.mark.asyncio
async def test_placeholder_models_are_not_recorded(monkeypatch):
    """«free», «account», «auto» — не модели, в реестре им не место."""
    from core import hixiit, capabilities

    async def fake_raw(task, kind="auto", ratio=None, image_url=None, allow_free=True):
        return {"ok": True, "url": "https://free/x.png", "kind": "image",
                "model": "free"}

    async def must_not_run(*a, **k):
        raise AssertionError("это не имя модели")

    async def noop(*a, **k):
        return None

    monkeypatch.setattr(hixiit, "_generate_once_raw", fake_raw)
    monkeypatch.setattr(capabilities, "record", noop)
    monkeypatch.setattr(mr, "mark_result", must_not_run)
    await hixiit._generate_once("кадр")
