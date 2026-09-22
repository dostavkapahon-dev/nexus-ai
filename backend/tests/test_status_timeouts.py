"""Ни одна часть статуса не имеет права съесть весь ответ.

Симптом из самопроверки: «check_hixiit — не ответила за 60 секунд». Причина —
живой запрос к платформе шёл по двум адресам по 20 секунд, а сверху ложились
база, браузер и MCP. Проверяем: зависшая часть заменяется honest-ответом, а
статус приходит целиком.
"""
import asyncio

import pytest

from core import hixiit

# Настоящие сроки снимаем на импорте: ниже автофикстура подменяет их на
# миллисекунды, чтобы тесты не ждали по-настоящему.
REAL = {"api": hixiit.API_STATUS_TIMEOUT, "browser": hixiit.BROWSER_STATUS_TIMEOUT,
        "store": hixiit.STORE_STATUS_TIMEOUT, "mcp": hixiit.MCP_STATUS_TIMEOUT,
        "poll_sec": hixiit.JOB_POLL_SECONDS, "poll_n": hixiit.JOB_POLL_ATTEMPTS}


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(hixiit, "API_STATUS_TIMEOUT", 0.05)
    monkeypatch.setattr(hixiit, "BROWSER_STATUS_TIMEOUT", 0.05)
    monkeypatch.setattr(hixiit, "STORE_STATUS_TIMEOUT", 0.05)
    monkeypatch.setattr(hixiit, "MCP_STATUS_TIMEOUT", 0.05)


async def _hangs():
    await asyncio.sleep(30)


@pytest.mark.asyncio
async def test_within_returns_fallback_instead_of_hanging():
    got = await hixiit._within(_hangs(), 0.05, {"ok": False})
    assert got == {"ok": False}


@pytest.mark.asyncio
async def test_within_passes_the_real_answer_through():
    async def quick():
        return "готово"
    assert await hixiit._within(quick(), 1, "запас") == "готово"


@pytest.mark.asyncio
async def test_status_answers_even_when_every_part_hangs(monkeypatch):
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "3f8c1a2b-4d5e-6f70-8192-a3b4c5d6e7f8")
    monkeypatch.setenv("HIGGSFIELD_SECRET", "8f" * 32)
    monkeypatch.setattr(hixiit, "_key_sources", lambda: _hangs())
    monkeypatch.setattr(hixiit, "browser_available", lambda quick=False: _hangs())
    monkeypatch.setattr(hixiit, "execution_mode", lambda: _hangs())
    monkeypatch.setattr("core.higgsfield.check", lambda: _hangs())

    out = await asyncio.wait_for(hixiit.status(), timeout=5)

    assert out["api_ok"] is False
    assert "не ответила" in out["api_error"]
    assert out["browser_agent"] is False
    assert out["key_sources"] == []


def test_status_budget_fits_the_selftest_limit():
    """Сумма сроков должна укладываться в минуту, которую даёт самопроверка.

    «check_hixiit — не ответила за 60 секунд» — это не поломка платформы, а
    наш собственный бюджет, вылезший за отведённое время.
    """
    worst = (REAL["api"] + REAL["browser"] + REAL["mcp"] + 2 * REAL["store"])
    assert worst <= 55, f"худший случай {worst:.0f} с — не влезет в минуту"


def test_mcp_budget_covers_a_handshake():
    """Каждый вызов MCP заново соединяется и здоровается.

    С восемью секундами статус объявлял MCP сломанным («нужен OAuth-вход»),
    а подробная проверка тут же отвечала «MCP работает» — при выполненном входе.
    """
    assert REAL["mcp"] >= 15


def test_job_polling_fits_the_platform_and_keeps_its_budget():
    """Длина одного опроса задана платформой, а не нами.

    Здесь стояло `poll_sec >= 30`, и это было требование к чужому протоколу:
    `jobs_wait` объявляет `timeout_seconds` как «default 15, max 15», то есть
    прежние 45 отклонялись проверкой аргументов — заявка уходила, кредиты
    списывались, а результат не забирался никогда.

    Забота, ради которой писался прежний тест (не платить рукопожатием за
    каждый опрос), решается не длиной шага: задача держит одну общую сессию
    MCP (`mcp_scope`), и опросы идут по ней. Поэтому осталось проверяемое —
    шаг в рамках протокола и неизменный общий запас времени.
    """
    assert REAL["poll_sec"] <= hixiit.MCP_WAIT_MAX_SECONDS
    assert REAL["poll_n"] * REAL["poll_sec"] >= 600


@pytest.mark.asyncio
async def test_slow_mcp_with_a_token_is_not_called_a_login_problem(monkeypatch):
    """Ложная причина хуже отсутствия причины: человек идёт перевходить зря."""
    monkeypatch.setenv("HIGGSFIELD_MCP_TOKEN", "token-value")
    monkeypatch.setattr(hixiit, "mcp_configured", lambda: True)
    monkeypatch.setattr(hixiit, "_mcp_call",
                        lambda *a, **k: _hangs())
    out = await asyncio.wait_for(hixiit.status(), timeout=5)
    assert out["mcp_ok"] is False
    assert "OAuth" not in out["mcp_error"]
    assert "медленнее" in out["mcp_error"]
