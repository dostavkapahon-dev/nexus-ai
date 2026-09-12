"""Какая сборка отвечает на /hixiit.

Дважды подряд вывод команды приходил побайтово одинаковым после выката
исправления, и отличить «фикс не помог» от «Render крутит старый код» было
нечем — каждая догадка стоила круга переписки. Теперь сборка названа прямо.

Заодно проверяется, что причина отказа MCP не обрезается на 150 символах:
код и ответ сервера начинаются как раз за этой границей.
"""
import pytest

from core import telegram_bot as tb


async def _hixiit(monkeypatch, st):
    sent = []

    async def fake_send(chat_id, text, **kw):
        sent.append(text)
        return {}

    async def fake_status():
        return st

    monkeypatch.setattr(tb, "send_message", fake_send)
    monkeypatch.setattr("core.hixiit.status", fake_status)
    async def fake_failures(**kw):
        return []

    monkeypatch.setattr("core.hixiit.recent_failures", fake_failures)
    await tb._handle_command("951", "/hixiit")
    return "\n".join(sent)


def _state(**over):
    st = {
        "api_ok": True, "key_sources": [], "mcp_configured": True,
        "mcp_ok": False, "browser_agent": False, "default_model": "auto",
        "unlim": {"available": False, "reason": "нет"},
    }
    st.update(over)
    return st


@pytest.mark.asyncio
async def test_build_commit_is_shown(monkeypatch):
    monkeypatch.setattr("core.version.build_info",
                        lambda: {"commit": "abc123def456", "branch": "master",
                                 "started_at": "2026-09-12T18:00:00"})
    text = await _hixiit(monkeypatch, _state())
    assert "abc123def456" in text


@pytest.mark.asyncio
async def test_start_time_is_shown(monkeypatch):
    """Коммита мало: после ручного рестарта он тот же, а процесс уже другой."""
    monkeypatch.setattr("core.version.build_info",
                        lambda: {"commit": "abc123def456", "branch": "master",
                                 "started_at": "2026-09-12T18:00:00"})
    text = await _hixiit(monkeypatch, _state())
    assert "2026-09-12T18:00:00" in text


@pytest.mark.asyncio
async def test_unknown_build_does_not_break_command(monkeypatch):
    def boom():
        raise RuntimeError("нет git")

    monkeypatch.setattr("core.version.build_info", boom)
    text = await _hixiit(monkeypatch, _state())
    assert "HIXIIT" in text          # команда всё равно ответила


@pytest.mark.asyncio
async def test_mcp_reason_is_not_cut_at_150(monkeypatch):
    reason = ("MCPError: Server returned an error response "
              + "x" * 100 + " (code=-32603; data={'status': 401})")
    text = await _hixiit(monkeypatch, _state(mcp_error=reason))
    assert "code=-32603" in text
    assert "401" in text
