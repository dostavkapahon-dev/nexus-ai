"""Выбор модели должен доходить до настоящего вызова, а не оставаться настройкой.

Главное требование ТЗ: выбрал Gemini — должен работать Gemini; выбрал модель
HIXIIT — должна уйти именно она. Раньше выбор записывался в профиль и никем не
читался: человек менял модель, а работала прежняя.
"""
import pytest
from sqlalchemy import select

from core import ai_router, hixiit, telegram_bot as tg
from database.db import AsyncSessionLocal
from database.models import UserProfile


async def _set_active_ai(value: str):
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(UserProfile).limit(1))
        prof = r.scalar_one_or_none()
        if not prof:
            prof = UserProfile()
            db.add(prof)
        prof.active_ai = value
        await db.commit()


@pytest.mark.asyncio
async def test_manual_ai_model_is_actually_used(client, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    await _set_active_ai("groq-free")

    assert await ai_router.pick_model("copywriter") == "groq-free"


@pytest.mark.asyncio
async def test_auto_falls_back_to_task_based_choice(client, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    await _set_active_ai("auto")

    picked = await ai_router.pick_model("copywriter")

    assert picked != "groq-free"
    assert picked, "в режиме AUTO модель всё равно должна выбираться"


@pytest.mark.asyncio
async def test_model_without_a_key_is_not_forced(client, monkeypatch):
    """Выбранная модель без ключа не заработает — лучше взять рабочую."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    await _set_active_ai("claude-sonnet-4-6")

    assert await ai_router.pick_model("copywriter") != "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_legacy_provider_name_means_auto(client):
    """Старое значение «claude» — название провайдера, а не модели."""
    await _set_active_ai("claude")

    assert await ai_router.chosen_model() == ""


@pytest.mark.asyncio
async def test_hixiit_uses_the_chosen_image_model(client, monkeypatch):
    await hixiit.set_preferred_model("image", "nano-banana")

    picked = await hixiit.pick_model("любая задача", "image")

    assert picked["id"] == "nano-banana"


@pytest.mark.asyncio
async def test_chosen_model_survives_a_restart(client):
    """Настройка живёт в постоянном хранилище, а не в памяти процесса."""
    await hixiit.set_preferred_model("video", "seedance")

    # Эмуляция перезапуска: кэши модуля сбрасываются, база остаётся.
    hixiit._models_cache.clear()

    assert await hixiit.preferred_model("video") == "seedance"


@pytest.mark.asyncio
async def test_auto_returns_to_automatic_choice(client, monkeypatch):
    await hixiit.set_preferred_model("image", "nano-banana")
    await hixiit.set_preferred_model("image", "")

    async def fake_mcp(tool, args, timeout=600.0):
        return {"items": [{"id": "auto-picked",
                           "parameters": [{"name": "prompt", "required": "required"}]}]}

    monkeypatch.setattr(hixiit, "_mcp_call", fake_mcp)
    monkeypatch.setenv("HIGGSFIELD_MCP_URL", "https://mcp.example/x")
    hixiit._models_cache.clear()

    picked = await hixiit.pick_model("портрет", "image")

    assert picked["id"] == "auto-picked"


@pytest.mark.asyncio
async def test_menu_hides_models_without_access(client, monkeypatch):
    """Модель без ключа в меню — обещание, которое система не выполнит."""
    models = [
        {"value": "works", "label": "Рабочая", "group": "g", "connected": True},
        {"value": "nokey", "label": "Без ключа", "group": "g", "connected": False},
    ]

    rows = tg._model_rows(models, "setai_", "")
    shown = [b["callback_data"] for row in rows for b in row]

    assert "setai_works" in shown
    assert "setai_nokey" not in shown
    assert "setai_auto" in shown, "AUTO доступен всегда"


@pytest.mark.asyncio
async def test_saving_from_telegram_reaches_the_router(client, monkeypatch):
    """Кнопка в Telegram → профиль → роутер. Вся цепочка, а не только запись."""
    monkeypatch.setattr(tg, "send_message", _swallow)
    monkeypatch.setenv("GROQ_API_KEY", "test")

    await tg._dispatch_command("55", "/setai_groq-free")

    assert await ai_router.chosen_model() == "groq-free"
    assert await ai_router.pick_model("reviewer") == "groq-free"


async def _swallow(chat_id, text, parse_mode="HTML", reply_markup=None, feed=False):
    return {}
