"""
Безлимит: «нет» должно быть сказано вслух.

Живая проверка аккаунта (план ultimate) показала `unlim.available: false` —
модели заявляют `supports_unlim`, но право аккаунта выдаётся отдельно и через
API не действует. Раньше именно этот случай выпадал из отчёта: строка про
безлимит не печаталась вовсе, и генерации выглядели бесплатными, пока молча
списывали кредиты.
"""
import pytest

from core import hixiit
from core import telegram_bot as tb


@pytest.mark.asyncio
async def test_reason_is_set_when_unlim_is_absent(monkeypatch):
    """Платформа ответила, безлимита нет — причина обязана быть."""
    async def fake_call(tool, args, timeout=60):
        return {"items": [{"id": "soul_2", "supports_unlim": True}],
                "unlim": {"available": False, "remaining": None}}

    monkeypatch.setattr(hixiit, "mcp_configured", lambda: True)
    monkeypatch.setattr(hixiit, "_mcp_call", fake_call)
    res = await hixiit.unlim_status()

    assert res["available"] is False
    assert res["reason"], "без причины «нет» неотличимо от «не проверяли»"
    assert "кредит" in res["reason"]


@pytest.mark.asyncio
async def test_supports_unlim_does_not_mean_available(monkeypatch):
    """Модель может поддерживать безлимит, а аккаунт — не иметь права на него."""
    async def fake_call(tool, args, timeout=60):
        return {"items": [{"id": "nano_banana", "supports_unlim": True},
                          {"id": "gpt_image_2", "supports_unlim": True}],
                "unlim": {"available": False}}

    monkeypatch.setattr(hixiit, "mcp_configured", lambda: True)
    monkeypatch.setattr(hixiit, "_mcp_call", fake_call)
    res = await hixiit.unlim_status()

    assert res["available"] is False, \
        "право решает аккаунт, а не флаг у модели"


@pytest.mark.asyncio
async def test_available_unlim_keeps_its_details(monkeypatch):
    async def fake_call(tool, args, timeout=60):
        return {"items": [{"id": "soul_2"}],
                "unlim": {"available": True, "remaining": 50,
                          "expires_at": "2027-01-01"}}

    monkeypatch.setattr(hixiit, "mcp_configured", lambda: True)
    monkeypatch.setattr(hixiit, "_mcp_call", fake_call)
    res = await hixiit.unlim_status()

    assert res["available"] is True
    assert res["remaining"] == 50
    assert "reason" not in res, "причина нужна только для отказа"


@pytest.mark.asyncio
async def test_hixiit_command_says_it_out_loud(client, monkeypatch):
    sent = []

    async def fake_send(chat_id, text, **kw):
        sent.append(text)
        return {}

    async def fake_status():
        return {"mcp_configured": True, "mcp_ok": True, "credits": 1199.85,
                "plan": "ultimate", "api_key": False, "key_sources": [],
                "default_model": "auto", "browser_agent": False,
                "unlim": {"available": False, "models": ["soul_2"],
                          "reason": "платформа не выдала безлимит этому "
                                    "аккаунту — генерации спишут кредиты"}}

    monkeypatch.setattr(tb, "send_message", fake_send)
    monkeypatch.setattr("core.hixiit.status", fake_status)
    await tb._handle_command("920", "/hixiit")

    text = "\n".join(sent)
    assert "Безлимит: нет" in text, "самая дорогая строка не должна исчезать"
    assert "кредит" in text


@pytest.mark.asyncio
async def test_generation_does_not_ask_for_unlim_it_does_not_have(monkeypatch):
    """Просить безлимит, которого нет, — получить отказ вместо картинки."""
    sent = {}

    async def fake_call(tool, args, timeout=600.0):
        if tool == "models_explore":
            return {"items": [{"id": "soul_2"}], "unlim": {"available": False}}
        sent.update(args.get("params") or {})
        return {"results": [{"id": "job-1", "status": "completed",
                             "url": "https://x/i.png"}]}

    async def done(job_id, attempts=40):
        return "https://x/i.png"

    monkeypatch.setattr(hixiit, "mcp_configured", lambda: True)
    monkeypatch.setattr(hixiit, "_mcp_call", fake_call)
    monkeypatch.setattr(hixiit, "_wait_job", done)
    monkeypatch.setattr(hixiit, "pick_model",
                        lambda *a, **kw: _model())

    await hixiit._generate_via_mcp("кофейня", "image", "9:16", None)

    assert sent.get("use_unlim") is False


async def _model(*a, **kw):
    return {"id": "soul_2"}
