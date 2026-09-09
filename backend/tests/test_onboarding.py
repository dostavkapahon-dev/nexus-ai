"""
Онбординг: чек-лист должен опираться на факты, а не на намерения.

Главные свойства, которые здесь защищаются: шаг «сделан» только когда это
подтверждено данными; сломавшаяся проверка не выдаётся за успех; порядок
подсказки идёт от того, что раньше сломает работу; и настроенность не
выдаётся за работоспособность.
"""
import pytest

from core import onboarding as ob
from core import telegram_bot as tb


@pytest.fixture
def bare(monkeypatch):
    """Пустая система: ничего не подключено."""
    monkeypatch.setattr("core.ai_router.available_providers", lambda: [])
    monkeypatch.delenv("TELEGRAM_POST_CHAT_ID", raising=False)
    for k in ("IG_HANDLE", "TIKTOK_HANDLE", "YOUTUBE_HANDLE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr("core.hixiit.mcp_configured", lambda: False)
    monkeypatch.setattr("core.higgsfield.credentials", lambda: "")
    # Соседние тесты могли настроить площадку: «пустая система» должна быть
    # пустой на самом деле, иначе проверка обязательных шагов ничего не значит.
    monkeypatch.setattr("connectors.get_connector", lambda name: None)


@pytest.mark.asyncio
async def test_empty_system_is_not_ready(client, bare):
    st = await ob.state()

    assert st["ready"] is False
    assert st["complete"] is False
    assert st["next"]["key"] == "ai", "без модели ИИ остальное не имеет смысла"


@pytest.mark.asyncio
async def test_ai_alone_is_not_enough(client, bare, monkeypatch):
    """Модель есть, публиковать некуда — работа упрётся на последнем шаге."""
    monkeypatch.setattr("core.ai_router.available_providers", lambda: ["gemini"])
    st = await ob.state()

    assert st["ready"] is False
    assert st["next"]["key"] == "publish"


@pytest.mark.asyncio
async def test_required_done_means_ready_but_not_complete(client, bare, monkeypatch):
    """Ниша, аккаунты и Higgsfield улучшают результат, но не блокируют работу."""
    monkeypatch.setattr("core.ai_router.available_providers", lambda: ["gemini"])
    monkeypatch.setenv("TELEGRAM_POST_CHAT_ID", "-1001")
    st = await ob.state()

    assert st["ready"] is True
    assert st["complete"] is False
    assert st["next"] is not None, "остаток должен быть виден, а не спрятан"


@pytest.mark.asyncio
async def test_broken_check_is_never_counted_as_done(client, bare, monkeypatch):
    """Непроверенное — не настроенное."""
    def explodes():
        raise RuntimeError("бум")

    monkeypatch.setattr("core.ai_router.available_providers", explodes)
    st = await ob.state()

    ai = [s for s in st["steps"] if s["title"] in ("Модель ИИ", "Проверка")][0]
    assert ai["done"] is False
    assert "бум" in ai["detail"]


@pytest.mark.asyncio
async def test_text_names_one_next_step_and_points_at_system_test(client, bare):
    text = ob.as_text(await ob.state())

    assert "Сейчас:" in text, "человеку нужен один следующий шаг, а не список из шести"
    assert "/system_test" in text, \
        "чек-лист говорит о настройке; работоспособность проверяется отдельно"
    assert "⬜" in text


@pytest.mark.asyncio
async def test_start_shows_checklist_until_ready(client, bare, monkeypatch):
    sent = []

    async def fake_send(chat_id, text, reply_markup=None, **kw):
        sent.append(text)
        return {}

    monkeypatch.setattr(tb, "send_message", fake_send)
    await tb._handle_command("910", "/start")

    assert any("Настройка" in t for t in sent), \
        "новичку сетка кнопок ничего не объясняет"


@pytest.mark.asyncio
async def test_start_shows_menu_when_ready(client, bare, monkeypatch):
    sent = []

    async def fake_send(chat_id, text, reply_markup=None, **kw):
        sent.append(text)
        return {}

    monkeypatch.setattr(tb, "send_message", fake_send)
    monkeypatch.setattr("core.ai_router.available_providers", lambda: ["gemini"])
    monkeypatch.setenv("TELEGRAM_POST_CHAT_ID", "-1001")
    await tb._handle_command("911", "/start")

    assert any("Пульт управления" in t for t in sent), \
        "настроенного владельца нельзя каждый раз встречать чек-листом"


@pytest.mark.asyncio
async def test_setup_shows_checklist_even_when_ready(client, bare, monkeypatch):
    sent = []

    async def fake_send(chat_id, text, reply_markup=None, **kw):
        sent.append(text)
        return {}

    monkeypatch.setattr(tb, "send_message", fake_send)
    monkeypatch.setattr("core.ai_router.available_providers", lambda: ["gemini"])
    monkeypatch.setenv("TELEGRAM_POST_CHAT_ID", "-1001")
    await tb._handle_command("912", "/setup")

    assert any("⬜" in t or "Всё настроено" in t for t in sent)


@pytest.mark.asyncio
async def test_checklist_makes_no_network_calls(client, bare, monkeypatch):
    """Чек-лист открывают, когда что-то не работает: он обязан отвечать сразу."""
    import httpx

    def forbidden(*a, **kw):
        raise AssertionError("онбординг не должен ходить в сеть")

    monkeypatch.setattr(httpx.AsyncClient, "get", forbidden)
    monkeypatch.setattr(httpx.AsyncClient, "post", forbidden)

    st = await ob.state()
    assert st["total"] == len(ob.STEPS)
