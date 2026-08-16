"""
Никаких «вечных» задач и никакой тишины после нажатия кнопки.

Две беды из ТЗ: задача может зависнуть навсегда (сторож её не видел, потому что
проверка была только при старте сервиса) и человек не понимает, идёт работа или
нет. Здесь проверяется, что зависшая задача закрывается с понятной причиной, а
идущая — видна в чате одним обновляющимся сообщением.
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from core import errors, task_feed
from core import task_manager as tm
from database.db import AsyncSessionLocal
from database.models import Task


async def _make_stale(task_id: str, minutes: int):
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Task).where(Task.id == task_id))
        t = r.scalar_one()
        t.status = tm.RUNNING
        t.started_at = datetime.utcnow() - timedelta(minutes=minutes)
        t.steps = [{"ts": (datetime.utcnow() - timedelta(minutes=minutes)).isoformat(),
                    "action": "Генерация", "ok": True, "error": ""}]
        await db.commit()


@pytest.mark.asyncio
async def test_stuck_task_is_closed_with_a_reason(client, monkeypatch):
    told = []

    async def fake_notify(text):
        told.append(text)
        return True

    monkeypatch.setattr("core.notify.notify_owner", fake_notify)

    task_id = await tm.create("factory", "Ролик про кофе", source="telegram")
    await _make_stale(task_id, tm.STUCK_AFTER_MIN + 5)

    res = await tm.watchdog()
    assert res["stuck"] == 1

    task = await tm.get(task_id)
    assert task["status"] == tm.FAILED
    assert "зависла" in task["error"]
    assert told and "остановлена" in told[0], "владелец не узнал о зависании"


@pytest.mark.asyncio
async def test_live_task_is_not_touched(client):
    task_id = await tm.create("factory", "Свежая задача")
    await _make_stale(task_id, 1)            # шаг был минуту назад — работа идёт

    assert (await tm.watchdog())["stuck"] == 0
    assert (await tm.get(task_id))["status"] == tm.RUNNING


@pytest.mark.asyncio
async def test_watchdog_runs_on_schedule():
    """Сторож в планировщике, а не только при старте сервиса."""
    import inspect
    from core import scheduler
    src = inspect.getsource(scheduler.start_scheduler)
    assert "watchdog" in src


# ─────────────────────────── живой статус ───────────────────────────

@pytest.mark.asyncio
async def test_progress_edits_one_message(client, monkeypatch):
    calls = []

    class FakeResp:
        def __init__(self, payload):
            self._p = payload

        def json(self):
            return self._p

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            calls.append((url.rsplit("/", 1)[-1], json))
            return FakeResp({"ok": True, "result": {"message_id": 7}})

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test:token")
    monkeypatch.setattr(task_feed.httpx, "AsyncClient", lambda *a, **kw: FakeClient())

    task_id = await tm.create("factory", "Ролик про кофе")
    await task_feed.start(task_id, "555", "Ролик про кофе")
    await tm.add_step(task_id, "Анализ задачи")
    await tm.add_step(task_id, "Исследование")

    methods = [m for m, _ in calls]
    assert methods[0] == "sendMessage", "первое сообщение задачи"
    assert methods[1:] == ["editMessageText", "editMessageText"], \
        "шаги должны обновлять то же сообщение, а не засыпать чат"

    last = calls[-1][1]["text"]
    assert "1/7 Анализ задачи" in last and "2/7 Исследование" in last
    assert "⏳ 3/7" in last, "видно, что делается прямо сейчас"


@pytest.mark.asyncio
async def test_failed_step_shows_human_reason(client, monkeypatch):
    texts = []

    class FakeResp:
        def json(self):
            return {"ok": True, "result": {"message_id": 1}}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            texts.append((json or {}).get("text", ""))
            return FakeResp()

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test:token")
    monkeypatch.setattr(task_feed.httpx, "AsyncClient", lambda *a, **kw: FakeClient())

    task_id = await tm.create("factory", "Ролик")
    await task_feed.start(task_id, "555", "Ролик")
    await tm.add_step(task_id, "Генерация", ok=False,
                      error="openai.RateLimitError: 429 insufficient_quota")

    assert "429" not in texts[-1], "технический мусор не должен попадать человеку"
    assert "лимит" in texts[-1].lower()


# ─────────────────────────── переводчик ошибок ───────────────────────────

@pytest.mark.parametrize("raw,expect", [
    ("Error 429 too many requests", "лимит"),
    ("httpx.ReadTimeout", "вовремя"),
    ("401 Unauthorized: invalid api key", "Ключ не принят"),
    ("Нет ни одного ключа ИИ", "Клоду"),
    (None, "логе задачи"),
    ("совершенно неизвестная беда", "логе задачи"),
])
def test_errors_speak_human(raw, expect):
    assert expect.lower() in errors.human(raw).lower()


def test_technical_detail_is_kept_for_logs():
    out = errors.explain("openai.RateLimitError: 429")
    assert "429" in out["detail"] and "429" not in out["message"]
