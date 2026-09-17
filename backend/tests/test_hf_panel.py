"""Пульт Higgsfield: выбранное человеком должно доезжать до генерации.

Раньше управление было размазано — модели в /model, канал в /hixiit, качество
текстовой командой, а формат вообще не выбирался. Сам по себе экран бесполезен,
если выбор не влияет на кадр, поэтому проверяем именно влияние.
"""
import pytest
import pytest_asyncio

from core import hixiit


@pytest.fixture(autouse=True)
async def clean(monkeypatch):
    """Каждый тест начинает с умолчаний.

    Настройки живут в базе — и это правильно в работе, но между тестами
    протекает: выбор одного теста молча менял поведение следующего.
    """
    for var in ("NEXUS_FRAME_FORMAT", "NEXUS_FRAME_QUALITY", "NEXUS_USE_UNLIM"):
        monkeypatch.delenv(var, raising=False)
    await _forget()
    yield
    await _forget()


async def _forget():
    # Таблицы создаём здесь же: порядок автоиспользуемых фикстур в асинхронных
    # тестах не гарантирован, и чистка может прийти раньше, чем поднимется база.
    from database.db import init_db
    await init_db()
    from sqlalchemy import delete
    from database.db import AsyncSessionLocal
    from database.models import Connection
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Connection).where(Connection.key_name.in_(
            (hixiit.FORMAT_KEY, hixiit.FRAME_QUALITY_KEY, hixiit.UNLIM_KEY))))
        await db.commit()


@pytest.mark.asyncio
async def test_defaults_are_auto_and_unlim_on():
    assert await hixiit.frame_format() == "auto"
    assert await hixiit.frame_quality() == "auto"
    # Не тратить выданный безлимит — значит зря списывать кредиты.
    assert await hixiit.use_unlim() is True


@pytest.mark.asyncio
async def test_settings_survive_a_read_after_write():
    assert await hixiit.set_frame_format("16:9") is True
    assert await hixiit.frame_format() == "16:9"
    assert await hixiit.set_frame_quality("1080p") is True
    assert await hixiit.frame_quality() == "1080p"
    await hixiit.set_use_unlim(False)
    assert await hixiit.use_unlim() is False


@pytest.mark.asyncio
async def test_foreign_values_are_refused():
    assert await hixiit.set_frame_format("огромный") is False
    assert await hixiit.set_frame_quality("8k") is False
    assert await hixiit.frame_format() == "auto"


@pytest.mark.asyncio
async def test_format_list_comes_from_one_place():
    from core.formats import PIXELS
    assert set(hixiit.frame_formats()) == {"auto", *PIXELS.keys()}


def _mcp(monkeypatch, sent):
    async def fake_call(tool, args, timeout=600.0):
        if tool == "models_explore":
            return {"items": [{"id": "soul_2", "name": "Soul"}],
                    "unlim": {"available": True}}
        sent.update(tool=tool, params=args["params"])
        return {"results": [{"id": "job-1"}]}

    async def done(job_id, attempts=40):
        return "https://cdn/hf.png"

    monkeypatch.setattr(hixiit, "_mcp_call", fake_call)
    monkeypatch.setattr(hixiit, "_wait_job", done)
    monkeypatch.setattr(hixiit, "mcp_configured", lambda: True)

    async def pick(task, kind, has_reference=False):
        return {"id": "soul_2"}
    monkeypatch.setattr(hixiit, "pick_model", pick)


@pytest.mark.asyncio
async def test_chosen_quality_reaches_the_platform(monkeypatch):
    sent = {}
    _mcp(monkeypatch, sent)
    await hixiit.set_frame_quality("1080p")
    await hixiit._generate_via_mcp("кадр", "image", "9:16")
    assert sent["params"]["quality"] == "1080p"


@pytest.mark.asyncio
async def test_auto_quality_is_not_sent_at_all(monkeypatch):
    """У моделей разные шкалы — навязанное значение это отказ вместо кадра."""
    sent = {}
    _mcp(monkeypatch, sent)
    await hixiit._generate_via_mcp("кадр", "image", "9:16")
    assert "quality" not in sent["params"]


@pytest.mark.asyncio
async def test_unlim_switched_off_is_respected(monkeypatch):
    sent = {}
    _mcp(monkeypatch, sent)
    await hixiit.set_use_unlim(False)
    await hixiit._generate_via_mcp("кадр", "image", "9:16")
    assert sent["params"]["use_unlim"] is False


@pytest.mark.asyncio
async def test_unlim_on_is_used_when_the_platform_gave_it(monkeypatch):
    sent = {}
    _mcp(monkeypatch, sent)
    await hixiit._generate_via_mcp("кадр", "image", "9:16")
    assert sent["params"]["use_unlim"] is True
