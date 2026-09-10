"""
Видимость агентов из Telegram.

Состав агентов был виден только на сайте, а в задаче — строкой «Агенты: …».
Из Telegram нельзя было понять ни кто занят сейчас, ни кто молчит вторые сутки,
хотя молчащий агент — это и есть типичный симптом сломанного джоба.

Здесь проверяется, что команда честно разделяет три разных состояния: агент без
доступов, агент со сбоями и агент, которого просто не звали.
"""
import pytest

from core import telegram_bot as tb


async def _say(monkeypatch, specs, stats, running):
    sent = []

    async def fake_send(chat_id, text, **kw):
        sent.append(text)
        return {}

    async def fake_stats(hours=24):
        return stats

    async def fake_tasks(status="", kind="", limit=50):
        return running

    monkeypatch.setattr(tb, "send_message", fake_send)
    monkeypatch.setattr("agents.registry.describe", lambda: specs)
    monkeypatch.setattr("core.health.agents", fake_stats)
    monkeypatch.setattr("core.task_manager.list_tasks", fake_tasks)
    await tb._handle_command("950", "/agents")
    return "\n".join(sent)


def _spec(key, title, ready=True, missing=()):
    return {"key": key, "title": title, "role": "роль " + key, "does": [],
            "requires": [], "backed_by": [], "missing": list(missing),
            "ready": ready}


@pytest.mark.asyncio
async def test_agent_without_access_is_not_called_broken(client, monkeypatch):
    """«Нет доступов» и «сбоит» — разные вещи, и лечатся по-разному."""
    text = await _say(monkeypatch,
                      [_spec("instagram", "Инстаграм", ready=False,
                             missing=["INSTAGRAM_ACCESS_TOKEN"])],
                      [], [])

    assert "🔒" in text
    assert "INSTAGRAM_ACCESS_TOKEN" in text, "надо назвать, чего не хватает"


@pytest.mark.asyncio
async def test_degraded_agent_shows_its_success_rate(client, monkeypatch):
    text = await _say(monkeypatch, [_spec("research", "Исследователь")],
                      [{"agent": "research", "status": "degraded", "calls": 10,
                        "success_rate": 40.0}], [])

    assert "⚠️" in text and "40" in text


@pytest.mark.asyncio
async def test_never_called_is_not_an_error(client, monkeypatch):
    """У агента может просто не быть задач — красным это помечать нельзя."""
    text = await _say(monkeypatch, [_spec("funnel", "Воронки")], [], [])

    assert "⏸" in text
    assert "не вызывался" in text


@pytest.mark.asyncio
async def test_running_work_is_shown_with_its_agents(client, monkeypatch):
    text = await _say(monkeypatch, [_spec("director", "Дирижёр")], [],
                      [{"goal": "ролик про шашлык", "kind": "factory",
                        "agents": ["director", "copywriter"]}])

    assert "ролик про шашлык" in text
    assert "copywriter" in text, "иначе непонятно, кто именно занят"


@pytest.mark.asyncio
async def test_idle_system_says_so_plainly(client, monkeypatch):
    text = await _say(monkeypatch, [_spec("director", "Дирижёр")], [], [])

    assert "задач в работе нет" in text
