"""
Один сценарий CREATE вместо россыпи команд.

По ТЗ человек говорит, ЧТО хочет получить, а система решает, КАК это сделать:
CREATE → вид → площадка → тема → план → запуск → живой статус. Здесь проверяется,
что цепочка не рвётся ни на одном шаге и что выбор кнопками не теряется, пока
человек печатает тему.
"""
import pytest

from core import dialog
from core import telegram_bot as tb


@pytest.fixture
def bot(monkeypatch):
    """Бот без сети: сообщения и запуски задач собираем списками."""
    sent, spawned = [], []

    async def fake_send(chat_id, text, reply_markup=None, **kw):
        sent.append({"text": text, "kb": reply_markup})
        return {}

    async def fake_spawn(kind, goal, fn, **kw):
        spawned.append({"kind": kind, "goal": goal, "fn": fn})
        return "task-1"

    async def fake_start(task_id, chat_id, title):
        spawned.append({"feed": title})

    monkeypatch.setattr(tb, "send_message", fake_send)
    monkeypatch.setattr("core.task_manager.spawn", fake_spawn)
    monkeypatch.setattr("core.task_feed.start", fake_start)
    return {"sent": sent, "spawned": spawned}


@pytest.mark.asyncio
async def test_create_asks_what_then_where_then_topic(client, bot):
    await dialog.clear("100")

    await tb._handle_command("100", "/create")
    kb = bot["sent"][-1]["kb"]["inline_keyboard"]
    labels = [b["callback_data"] for row in kb for b in row]
    assert "mk_video" in labels and "mk_carousel" in labels

    await tb._handle_command("100", "/mk_video")
    kb = bot["sent"][-1]["kb"]["inline_keyboard"]
    assert "pf_video_instagram" in [b["callback_data"] for row in kb for b in row]

    await tb._handle_command("100", "/pf_video_instagram")
    assert "О чём" in bot["sent"][-1]["text"]
    assert await dialog.awaiting("100") == dialog.AWAIT_TOPIC
    assert await dialog.pending("100") == {"kind": "video", "platform": "instagram"}


@pytest.mark.asyncio
async def test_topic_starts_the_right_kind_of_work(client, bot, monkeypatch):
    seen = {}

    async def fake_factory(topic=None, platforms=None, dry_run=True,
                           want_video=True, content_type="auto"):
        seen.update({"topic": topic, "platforms": platforms, "dry_run": dry_run,
                     "want_video": want_video, "content_type": content_type})
        return {"ok": True}

    monkeypatch.setattr("core.content_factory.run_factory", fake_factory)
    await dialog.clear("101")

    await tb._handle_command("101", "/pf_carousel_instagram")
    await tb._handle_plain_text("101", "шашлык на углях")

    job = [s for s in bot["spawned"] if s.get("fn")][0]
    await job["fn"]()

    assert seen["topic"] == "шашлык на углях"
    assert seen["platforms"] == ["instagram"]
    assert seen["content_type"] == "carousel"
    assert seen["want_video"] is False, "для карусели видео не генерируем"
    assert seen["dry_run"] is False, "иначе результат не дойдёт до согласования"


@pytest.mark.asyncio
async def test_by_trends_needs_no_topic(client, bot, monkeypatch):
    seen = {}

    async def fake_factory(topic=None, **kw):
        seen["topic"] = topic
        return {"ok": True}

    monkeypatch.setattr("core.content_factory.run_factory", fake_factory)
    await dialog.clear("102")

    await tb._handle_command("102", "/pf_video_tiktok")
    await tb._handle_plain_text("102", "по трендам")

    job = [s for s in bot["spawned"] if s.get("fn")][0]
    await job["fn"]()
    assert seen["topic"] is None, "«по трендам» — это отсутствие темы, а не тема"


@pytest.mark.asyncio
async def test_live_status_is_opened_for_the_task(client, bot):
    await dialog.clear("103")
    await tb._handle_command("103", "/pf_video_telegram")
    await tb._handle_plain_text("103", "кофейня утром")

    assert any("feed" in s for s in bot["spawned"]), \
        "без живого статуса человек снова остаётся в тишине"


@pytest.mark.asyncio
async def test_menu_is_short(client, bot):
    kb = tb._main_menu_kb()["inline_keyboard"]
    buttons = [b for row in kb for b in row]
    assert len(buttons) <= 8, "меню снова разрослось — по ТЗ так нельзя"
    assert buttons[0]["callback_data"] == "create", "главная кнопка — СОЗДАТЬ"


@pytest.mark.asyncio
async def test_plan_skips_platform_question(client, bot, monkeypatch):
    """Контент-план не привязан к одной площадке — лишний вопрос не задаём."""
    async def no_strategy():
        return {}

    monkeypatch.setattr("core.autopilot.get_state", no_strategy)
    await tb._handle_command("104", "/mk_plan")

    texts = [s["text"] for s in bot["sent"]]
    assert not any("площадк" in t.lower() for t in texts), "лишний вопрос про площадку"
    assert any("/auto" in t for t in texts), "команда плана не отработала"
