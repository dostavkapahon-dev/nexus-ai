"""
Самопроверка: она должна доказывать работу, а не показывать галочки.

Здесь проверяется главное свойство `/system_test`: успех означает настоящий
вызов с ожидаемым результатом. Отвечающая ерундой модель, пустая выдача поиска
и «ключ есть, но запрос не проходит» обязаны давать красный статус — иначе
проверка врёт ровно там, где её и открывают.
"""
import pytest

from core import system_test as st
from core import telegram_bot as tb


@pytest.mark.asyncio
async def test_ai_answering_nonsense_is_a_failure(monkeypatch):
    """Модель ответила — но не то. Связь есть, доверять содержимому нельзя."""
    async def wrong(model, system, prompt):
        return {"text": "семь", "model_used": model}

    monkeypatch.setattr("core.ai_router.ai_router.call", wrong)
    res = await st.check_ai()

    assert res["ok"] is False
    assert "не совпал" in res["detail"]


@pytest.mark.asyncio
async def test_ai_correct_answer_passes(monkeypatch):
    async def right(model, system, prompt):
        return {"text": "4", "model_used": "gemini-2.0-flash"}

    monkeypatch.setattr("core.ai_router.ai_router.call", right)
    res = await st.check_ai()

    assert res["ok"] is True
    assert "4" in res["evidence"], "без доказательства проверка ничем не лучше галочки"


@pytest.mark.asyncio
async def test_empty_search_is_a_failure(monkeypatch):
    async def nothing(query, n=5):
        return {"ok": False, "error": "поиск не дал результатов", "results": []}

    monkeypatch.setattr("core.websearch.search", nothing)
    res = await st.check_search()

    assert res["ok"] is False
    assert "результат" in res["detail"]


@pytest.mark.asyncio
async def test_hixiit_access_without_generation_is_honest(monkeypatch):
    """Доступ есть, генерацию не запускали — так и надо написать."""
    async def st_ok():
        return {"mcp_ok": True, "credits": 1200}

    monkeypatch.setattr("core.hixiit.status", st_ok)
    res = await st.check_hixiit(deep=False)

    assert res["ok"] is True
    assert "не запускалась" in res["evidence"], \
        "иначе отчёт утверждает то, чего не проверял"


@pytest.mark.asyncio
async def test_deep_mode_requires_a_real_file(monkeypatch):
    """В глубоком режиме успех — это ссылка на файл, а не ok: True."""
    async def st_ok():
        return {"mcp_ok": True, "credits": 1200}

    async def no_file(task, kind="auto", ratio=None, image_url=None,
                      allow_free=True, qc=True):
        return {"ok": True, "url": ""}

    monkeypatch.setattr("core.hixiit.status", st_ok)
    monkeypatch.setattr("core.hixiit.generate", no_file)
    res = await st.check_hixiit(deep=True)

    assert res["ok"] is False


@pytest.mark.asyncio
async def test_no_access_is_red_even_with_a_key(monkeypatch):
    async def st_key_only():
        return {"api_key": True, "api_ok": False, "api_error": "401 unauthorized"}

    monkeypatch.setattr("core.hixiit.status", st_key_only)
    res = await st.check_hixiit()

    assert res["ok"] is False
    assert "401" in res["detail"]


@pytest.mark.asyncio
async def test_routing_check_catches_one_model_for_everything(monkeypatch):
    """Если всё уходит в одну модель — экспертизы нет, и это должно быть видно."""
    monkeypatch.setattr("core.hixiit.pick_by_task", lambda *a, **kw: "z_image")
    res = await st.check_model_routing()

    assert res["ok"] is False
    assert "одну модель" in res["detail"]


@pytest.mark.asyncio
async def test_routing_check_passes_on_real_router():
    """Настоящий маршрутизатор обязан разводить товар и человека."""
    res = await st.check_model_routing()

    assert res["ok"] is True, res["detail"]


@pytest.mark.asyncio
async def test_queue_check_uses_a_real_task(client):
    res = await st.check_queue()

    assert res["ok"] is True, res["detail"]
    assert res["evidence"].startswith("TASK-"), "проверка должна назвать задачу"


@pytest.mark.asyncio
async def test_scheduler_not_running_is_a_failure(monkeypatch):
    monkeypatch.setattr("core.health.scheduler_jobs",
                        lambda: {"running": False, "jobs": []})
    res = await st.check_scheduler()

    assert res["ok"] is False


@pytest.mark.asyncio
async def test_report_counts_failures_and_stays_honest(monkeypatch):
    async def bad():
        return st._fail("Проверка", "не работает")

    async def good():
        return st._ok("Проверка", "работает")

    monkeypatch.setattr(st, "CHECKS", (good, bad))
    report = await st.run()
    text = st.as_text(report)

    assert report["ok"] is False
    assert report["passed"] == 1 and report["total"] == 2
    assert "1 из 2" in text
    assert "❌" in text


@pytest.mark.asyncio
async def test_one_broken_check_does_not_kill_the_report(monkeypatch):
    """Упавшая проверка — строка в отчёте, а не пустой ответ в чат."""
    async def explodes():
        raise RuntimeError("бум")

    monkeypatch.setattr(st, "CHECKS", (explodes,))
    report = await st.run()

    assert report["total"] == 1 and report["passed"] == 0
    assert "бум" in report["checks"][0]["detail"]


@pytest.mark.asyncio
async def test_default_run_does_not_generate(monkeypatch):
    """Обычный прогон не должен тратить кредиты."""
    called = []

    async def st_ok():
        return {"mcp_ok": True, "credits": 1200}

    async def generate(*a, **kw):
        called.append(a)
        return {"ok": True, "url": "https://x/i.png"}

    monkeypatch.setattr("core.hixiit.status", st_ok)
    monkeypatch.setattr("core.hixiit.generate", generate)
    await st.check_hixiit(deep=False)

    assert called == [], "самопроверка не должна жечь генерации без спроса"


@pytest.mark.asyncio
async def test_command_answers_in_chat(client, monkeypatch):
    sent = []

    async def fake_send(chat_id, text, **kw):
        sent.append(text)
        return {}

    async def fake_run(deep=False):
        assert deep is False
        return {"ok": True, "passed": 1, "total": 1, "sec": 1.0, "deep": deep,
                "checks": [{"name": "Память", "ok": True, "detail": "ок",
                            "evidence": "", "sec": 0.1}]}

    monkeypatch.setattr(tb, "send_message", fake_send)
    monkeypatch.setattr(st, "run", fake_run)
    await tb._handle_command("900", "/system_test")

    assert any("Самопроверка" in t for t in sent)


@pytest.mark.asyncio
async def test_deep_flag_reaches_the_run(client, monkeypatch):
    seen = {}

    async def fake_send(chat_id, text, **kw):
        return {}

    async def fake_run(deep=False):
        seen["deep"] = deep
        return {"ok": True, "passed": 0, "total": 0, "sec": 0.0, "deep": deep,
                "checks": []}

    monkeypatch.setattr(tb, "send_message", fake_send)
    monkeypatch.setattr(st, "run", fake_run)
    await tb._handle_command("901", "/system_test deep")

    assert seen["deep"] is True
