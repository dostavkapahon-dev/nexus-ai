"""
Очередь производства: ТЗ уходит исполнителю, готовое медиа возвращается.

Смысл проверок: одно ТЗ не должно уйти двум исполнителям (иначе ролик сделают
дважды и заплатят дважды), а принятый ролик обязан пойти дальше по конвейеру —
на монтаж и согласование, а не просто поменять статус в базе.
"""
import pytest
import pytest_asyncio
from sqlalchemy import delete

from core import production_queue as pq
from database.db import AsyncSessionLocal
from database.models import ProductionJob

BRIEF = {
    "theme": "доставка за 15 минут",
    "hook_text": "Вы платите за ожидание",
    "video_motion_prompt": "slow push-in, neon light",
    "avatar_script": "Мы возим еду за 15 минут",
    "storyboard": [{"t": "0-3", "overlay": "15 минут", "image_prompt": "курьер в городе"}],
    "platforms": ["telegram"],
    "caption": "Доставка за 15 минут",
}


@pytest_asyncio.fixture(autouse=True)
async def _clean(client):
    async def wipe():
        async with AsyncSessionLocal() as db:
            await db.execute(delete(ProductionJob))
            await db.commit()
    await wipe()
    await pq.set_producer(pq.SERVER)
    yield
    await wipe()


@pytest.mark.asyncio
async def test_job_goes_to_one_executor_only(client):
    """Второй запрос не должен получить то же задание."""
    job = await pq.enqueue(BRIEF)
    assert job["status"] == pq.QUEUED

    first = await pq.claim()
    assert first["id"] == job["id"] and first["status"] == pq.TAKEN

    second = await pq.claim()
    assert second is None, "одно ТЗ ушло дважды — ролик сделают и оплатят дважды"


@pytest.mark.asyncio
async def test_result_without_files_is_refused(client):
    job = await pq.enqueue(BRIEF)
    res = await pq.submit(job["id"], {})
    assert res["ok"] is False and "ссылки" in res["error"]


@pytest.mark.asyncio
async def test_failed_job_keeps_reason_and_can_return_to_queue(client):
    job = await pq.enqueue(BRIEF)
    await pq.claim()

    res = await pq.fail(job["id"], "Higgsfield отказал: нет кредитов")
    assert res["ok"] and res["job"]["status"] == pq.FAILED
    assert "кредитов" in res["job"]["error"]

    back = await pq.retry(job["id"])
    assert back["ok"] and back["job"]["status"] == pq.QUEUED
    assert (await pq.claim())["id"] == job["id"]


@pytest.mark.asyncio
async def test_done_job_cannot_be_cancelled_or_resubmitted(client):
    job = await pq.enqueue(BRIEF)
    await pq.submit(job["id"], {"video_url": "https://cdn/1.mp4"})

    assert (await pq.cancel(job["id"]))["ok"] is False
    assert (await pq.submit(job["id"], {"video_url": "https://cdn/2.mp4"}))["ok"] is False


@pytest.mark.asyncio
async def test_brief_is_readable_for_the_executor(client):
    text = pq.brief_as_text(BRIEF)
    assert "доставка за 15 минут" in text
    assert "Раскадровка:" in text and "0-3" in text
    assert "курьер в городе" in text


# ─────────────────────────── кто делает видео ───────────────────────────

@pytest.mark.asyncio
async def test_producer_switch(client):
    assert await pq.producer() == pq.SERVER          # по умолчанию как раньше
    assert (await pq.set_producer(pq.CLAUDE))["ok"] is True
    assert await pq.producer() == pq.CLAUDE
    assert (await pq.set_producer("кто-то ещё"))["ok"] is False


@pytest.mark.asyncio
async def test_factory_hands_brief_over_instead_of_generating(client, monkeypatch):
    """При внешнем производстве конвейер обязан остановиться на ТЗ, а не звать
    генератор видео сам."""
    from core import content_factory as cf

    await pq.set_producer(pq.CLAUDE)

    called = {"video": False}

    async def fake_analyze(topic):
        return {"theme": "тема", "hook_text": "хук", "image_prompt": "кадр",
                "instagram": {"caption": "текст"}}

    async def fake_brief(plan):
        return {"storyboard": BRIEF["storyboard"], "cover_prompt": "обложка",
                "video_motion_prompt": "движение", "avatar_script": "сценарий"}

    async def fake_wow(brief):
        return {"score": 9}

    async def fake_image(prompt, platform="instagram"):
        return "https://img/cover.png"

    async def fake_clip(*a, **kw):
        called["video"] = True
        return {"ok": True, "url": "https://cdn/x.mp4"}

    monkeypatch.setattr(cf, "_analyze", fake_analyze)
    monkeypatch.setattr("core.creative_director.build_brief", fake_brief)
    monkeypatch.setattr("core.creative_director.wow_review", fake_wow)
    monkeypatch.setattr("core.media_generator.generate_image", fake_image)
    monkeypatch.setattr("core.media_generator.generate_clip", fake_clip)

    report = await cf.run_factory(topic="тест", platforms=["telegram"], dry_run=True)

    assert report.get("awaiting_producer") is True
    assert report.get("production_job")
    assert called["video"] is False, "видео не должно генерироваться сервером"

    jobs = await pq.jobs(status=pq.QUEUED)
    assert len(jobs) == 1
    assert jobs[0]["brief"]["video_motion_prompt"] == "движение"


@pytest.mark.asyncio
async def test_finalize_sends_to_approval_not_publishes(client, monkeypatch):
    """Готовый ролик идёт владельцу на согласование, а не сразу в канал."""
    from core import content_factory as cf

    sent = {}

    async def fake_approval(text, media_url=None, platforms=None, kind="plan", ref=None):
        sent.update({"text": text, "media": media_url, "platforms": platforms})
        return "pid123"

    async def fake_local(vid):
        return None                     # монтаж пропускаем, сеть не трогаем

    monkeypatch.setattr("core.moderation.send_for_approval", fake_approval)
    monkeypatch.setattr("core.video_editor.ensure_local_video", fake_local)

    job = await pq.enqueue(BRIEF)
    await pq.submit(job["id"], {"video_url": "https://cdn/ready.mp4"})
    done = await pq.get(job["id"])

    out = await cf.finalize_from_assets(done)
    assert out["status"] == "awaiting_approval" and out["pid"] == "pid123"
    assert sent["media"] == "https://cdn/ready.mp4"
    assert sent["platforms"] == ["telegram"]


@pytest.mark.asyncio
async def test_finalize_says_when_there_is_nobody_to_approve(client, monkeypatch):
    from core import content_factory as cf

    async def no_telegram(*a, **kw):
        return None

    async def fake_local(vid):
        return None

    monkeypatch.setattr("core.moderation.send_for_approval", no_telegram)
    monkeypatch.setattr("core.video_editor.ensure_local_video", fake_local)

    job = await pq.enqueue(BRIEF)
    await pq.submit(job["id"], {"video_url": "https://cdn/ready.mp4"})
    out = await cf.finalize_from_assets(await pq.get(job["id"]))

    assert out["status"] == "no_telegram" and "некому" in out["note"]


# ─────────────────────────── API ───────────────────────────

@pytest.mark.asyncio
async def test_api_full_round_trip(auth_client, monkeypatch):
    approved = {}

    async def fake_approval(text, media_url=None, platforms=None, kind="plan", ref=None):
        approved["media"] = media_url
        return "pid777"

    async def fake_local(vid):
        return None

    monkeypatch.setattr("core.moderation.send_for_approval", fake_approval)
    monkeypatch.setattr("core.video_editor.ensure_local_video", fake_local)

    r = await auth_client.post("/api/production/jobs", json={"brief": BRIEF})
    job_id = r.json()["job"]["id"]

    got = (await auth_client.get("/api/production/next")).json()
    assert got["job"]["id"] == job_id
    assert "Раскадровка" in got["brief_text"]        # исполнителю видно ТЗ словами

    empty = (await auth_client.get("/api/production/next")).json()
    assert empty["job"] is None                       # очередь пуста, это не ошибка

    res = await auth_client.post(f"/api/production/{job_id}/result",
                                 json={"video_url": "https://cdn/ready.mp4"})
    body = res.json()
    assert body["ok"] and body["next"]["status"] == "awaiting_approval"
    assert approved["media"] == "https://cdn/ready.mp4"


@pytest.mark.asyncio
async def test_api_fail_tells_the_owner(auth_client, monkeypatch):
    told = []

    async def fake_notify(text):
        told.append(text)
        return True

    monkeypatch.setattr("core.notify.notify_owner", fake_notify)

    r = await auth_client.post("/api/production/jobs", json={"brief": BRIEF})
    job_id = r.json()["job"]["id"]

    res = await auth_client.post(f"/api/production/{job_id}/fail",
                                 json={"error": "нет кредитов Higgsfield"})
    assert res.json()["ok"] is True
    assert told and "не удалось" in told[0]


@pytest.mark.asyncio
async def test_api_producer_mode(auth_client):
    r = await auth_client.post("/api/production/producer", json={"producer": "claude"})
    assert r.json() == {"ok": True, "producer": "claude"}
    assert (await auth_client.get("/api/production/jobs")).json()["producer"] == "claude"
