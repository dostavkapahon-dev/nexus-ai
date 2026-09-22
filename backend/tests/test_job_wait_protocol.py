"""Ожидание результата должно укладываться в протокол платформы.

Инструмент `jobs_wait` официального MCP Higgsfield объявляет `timeout_seconds`
как «default 15, max 15». Код просил 45: заявка при этом отправлялась и кредиты
списывались, а каждый опрос отклонялся проверкой аргументов — задача сообщала
«Higgsfield не отдал результат вовремя», хотя кадр был готов.

Прежние тесты этого не поймали: их поддельный MCP принимал любые аргументы. Так
что здесь проверяется именно отправляемый запрос, а поддельная платформа ведёт
себя как настоящая — отклоняет значение выше максимума.
"""
import pytest

from core import hixiit


def test_one_wait_never_exceeds_protocol_maximum():
    assert hixiit.MCP_WAIT_MAX_SECONDS == 15, (
        "максимум задан платформой, а не нами")
    assert hixiit.JOB_POLL_SECONDS <= hixiit.MCP_WAIT_MAX_SECONDS


def test_budget_survives_the_short_poll():
    """Опрос короче — значит опросов больше, а общий запас тот же."""
    assert hixiit.JOB_POLL_ATTEMPTS * hixiit.JOB_POLL_SECONDS >= 600
    assert hixiit.VIDEO_BUDGET_SECONDS > hixiit.JOB_BUDGET_SECONDS, (
        "видео делается дольше кадра")


@pytest.mark.asyncio
async def test_wait_job_sends_accepted_timeout(monkeypatch):
    seen = []

    async def fake_call(tool, args, timeout=600.0):
        if tool != "jobs_wait":
            raise AssertionError(f"неожиданный вызов {tool}")
        seen.append(args)
        wait = args.get("timeout_seconds")
        # Ровно так отвечает платформа на значение выше максимума.
        if not isinstance(wait, int) or wait > hixiit.MCP_WAIT_MAX_SECONDS:
            raise RuntimeError(
                "Input validation error: timeout_seconds must be <= 15")
        return {"jobs": [{"index": 0, "job_id": "j-1", "status": "completed",
                          "result_url": "https://cdn.example/a.png"}],
                "all_terminal": True}

    monkeypatch.setattr(hixiit, "_mcp_call", fake_call)
    url = await hixiit._wait_job("j-1")
    assert url == "https://cdn.example/a.png"
    assert seen and seen[0]["timeout_seconds"] <= hixiit.MCP_WAIT_MAX_SECONDS
    assert seen[0]["jobs"] == [{"index": 0, "job_id": "j-1"}]
