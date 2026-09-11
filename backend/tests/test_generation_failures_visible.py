"""
Почему «Higgsfield не работает», а картинка всё-таки приходит.

Для изображений цепочка на последнем шаге подменяет результат бесплатным
генератором и возвращает ok — снаружи «получилось», просто картинка не та.
Причина падения записывалась в журнал, но не показывалась нигде: человек видел
итог и не мог сказать, почему генератор не сработал.

Здесь проверяется, что причины доходят до /hixiit — туда, куда и идут, когда
«не работает».
"""
import pytest

from core import hixiit
from core import telegram_bot as tb
from core.cost_tracker import record


@pytest.mark.asyncio
async def test_failed_generation_is_remembered_with_its_reason(client):
    await record(model="hixiit:image", tokens=0, cost=0.0, status="error",
                 duration=1.0, error="Higgsfield не принял ключ (401)",
                 agent="media")

    fails = await hixiit.recent_failures()

    assert fails, "причина падения обязана сохраняться"
    assert "401" in fails[0]["error"]
    assert fails[0]["what"] == "image", "видно, что именно не получилось"


@pytest.mark.asyncio
async def test_successful_generations_are_not_reported_as_failures(client):
    await record(model="hixiit:image", tokens=0, cost=0.01, status="success",
                 duration=1.0, agent="media")

    assert all(f["error"] != "" and "success" not in f["error"]
               for f in await hixiit.recent_failures())


@pytest.mark.asyncio
async def test_hixiit_shows_the_reasons(client, monkeypatch):
    sent = []

    async def fake_send(chat_id, text, **kw):
        sent.append(text)
        return {}

    async def fake_status():
        return {"mcp_configured": False, "api_key": True, "api_ok": True,
                "default_model": "auto", "browser_agent": False,
                "key_sources": [], "credits": 1200, "plan": "ultimate"}

    async def fake_fails(limit=3, hours=24):
        return [{"when": "11.09 10:00", "what": "image",
                 "error": "Higgsfield отверг параметры (422)"}]

    monkeypatch.setattr(tb, "send_message", fake_send)
    monkeypatch.setattr("core.hixiit.status", fake_status)
    monkeypatch.setattr("core.hixiit.recent_failures", fake_fails)
    await tb._handle_command("960", "/hixiit")

    text = "\n".join(sent)
    assert "неудачные генерации" in text
    assert "422" in text, "без причины человеку снова нечего сказать"


@pytest.mark.asyncio
async def test_no_failures_means_no_noise(client, monkeypatch):
    sent = []

    async def fake_send(chat_id, text, **kw):
        sent.append(text)
        return {}

    async def fake_status():
        return {"mcp_configured": False, "api_key": True, "api_ok": True,
                "default_model": "auto", "browser_agent": False,
                "key_sources": [], "credits": 1200, "plan": "ultimate"}

    async def no_fails(limit=3, hours=24):
        return []

    monkeypatch.setattr(tb, "send_message", fake_send)
    monkeypatch.setattr("core.hixiit.status", fake_status)
    monkeypatch.setattr("core.hixiit.recent_failures", no_fails)
    await tb._handle_command("961", "/hixiit")

    assert "неудачные генерации" not in "\n".join(sent)


@pytest.mark.asyncio
async def test_broken_journal_does_not_break_the_command(client, monkeypatch):
    """Диагностика не имеет права падать сама."""
    def boom(*a, **kw):
        raise RuntimeError("база недоступна")

    monkeypatch.setattr("database.db.AsyncSessionLocal", boom)

    assert await hixiit.recent_failures() == []
