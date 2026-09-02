"""Контракты между агентами и работа с комментариями (воронка)."""
import pytest
from sqlalchemy import delete

from core import engagement as eng
from core import kv
from core.contracts import AgentResult, handoff, weakest
from database.db import AsyncSessionLocal
from database.models import Connection


@pytest.fixture(autouse=True)
async def _clean(client):
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Connection).where(
            Connection.key_name.in_([eng.SEEN_KEY, eng.PENDING_KEY])))
        await db.commit()
    yield


# ─────────────────────────── контракты ───────────────────────────

def test_result_flags_missing_required_fields():
    """Пустые поля больше не проскакивают молча — падает уверенность."""
    full = AgentResult.from_raw("copywriter", {"text": "готовый пост"})
    assert full.ok is True
    assert full.confidence == 1.0
    assert full.reliable is True

    empty = AgentResult.from_raw("copywriter", {"text": ""})
    assert empty.ok is False
    assert empty.confidence < 1.0
    assert "text" in empty.warnings[0]


def test_confidence_drops_with_more_gaps():
    one_gap = AgentResult.from_raw("reviewer", {"text_reviewed": "ok", "score": 0})
    both_gaps = AgentResult.from_raw("reviewer", {})
    assert both_gaps.confidence < one_gap.confidence
    assert both_gaps.reliable is False


def test_failed_result_is_explicit():
    """Провал должен быть виден следующему агенту, а не выглядеть пустым словарём."""
    r = AgentResult.failed("niche_analyst", "нет ключа AI")
    assert r.ok is False
    assert r.confidence == 0.0
    assert "нет ключа" in r.for_prompt()
    assert "ОШИБКА" in r.for_prompt()


def test_non_dict_input_is_rejected():
    r = AgentResult.from_raw("copywriter", "просто строка")
    assert r.ok is False
    assert "ожидался словарь" in r.error


def test_for_prompt_carries_warnings():
    """Модель не должна принимать неполный вход за полный."""
    r = AgentResult.from_raw("viral_hunter", {"viral_topics": ["a"]})
    text = r.for_prompt()
    assert "viral_hunter" in text
    assert "ВНИМАНИЕ" in text
    assert "hooks" in text


def test_handoff_keeps_failures_visible():
    good = AgentResult.from_raw("copywriter", {"text": "пост"})
    bad = AgentResult.failed("visual_creator", "нет ключа картинок")
    combined = handoff(good, bad)
    assert "пост" in combined
    assert "нет ключа картинок" in combined


def test_weakest_finds_shaky_link():
    strong = AgentResult.from_raw("copywriter", {"text": "пост"})
    weak = AgentResult.from_raw("reviewer", {})
    assert weakest(strong, weak).agent == "reviewer"


# ─────────────────────────── комментарии ───────────────────────────

def _comments(*ids):
    return {"ok": True, "comments": [
        {"id": i, "text": f"текст {i}", "author": f"user{i}",
         "post_url": "https://insta/1"} for i in ids]}


@pytest.mark.asyncio
async def test_fetch_skips_already_seen(client, monkeypatch):
    from connectors import get_connector

    async def fake_read(limit=20):
        return _comments("c1", "c2", "c3")

    monkeypatch.setattr(get_connector("instagram"), "read_comments", fake_read)
    await kv.set(eng.SEEN_KEY, ["c1"])

    fresh = await eng.fetch_new_comments("instagram")
    assert [c["id"] for c in fresh] == ["c2", "c3"]


@pytest.mark.asyncio
async def test_replies_go_to_approval_not_straight_out(client, monkeypatch):
    """Ключевое правило: ответ от лица бренда не публикуется без подтверждения."""
    from connectors import get_connector
    from agents.funnel_agent import FunnelAgent

    async def fake_read(limit=20):
        return _comments("c1")

    async def fake_reply(self, db, niche_id, comment, niche, **kw):
        return {"reply": "Ответим в личке!", "intent": "buy", "should_reply": True}

    sent = []

    async def fake_send(self, comment_id, text):
        sent.append(comment_id)
        return {"ok": True}

    ig = get_connector("instagram")
    monkeypatch.setattr(ig, "read_comments", fake_read)
    monkeypatch.setattr(FunnelAgent, "generate_reply", fake_reply)
    monkeypatch.setattr(type(ig), "reply_comment", fake_send)

    res = await eng.process_comments("instagram", limit=5, auto_send=False)
    assert res["pending_approval"] == 1
    assert sent == []                      # ничего не ушло само

    items = await eng.pending()
    assert items[0]["reply"] == "Ответим в личке!"
    assert items[0]["intent"] == "buy"


@pytest.mark.asyncio
async def test_approve_sends_and_clears_queue(client, monkeypatch):
    from connectors import get_connector

    sent = []

    async def fake_send(self, comment_id, text):
        sent.append((comment_id, text))
        return {"ok": True}

    monkeypatch.setattr(type(get_connector("instagram")), "reply_comment", fake_send)
    await kv.set(eng.PENDING_KEY, [
        {"platform": "instagram", "comment_id": "c1", "reply": "ответ", "author": "u"}])

    res = await eng.approve_all()
    assert res["sent"] == 1
    assert sent[0][0] == "c1"
    assert await eng.pending() == []       # очередь очищена


@pytest.mark.asyncio
async def test_approve_reports_failures_honestly(client, monkeypatch):
    from connectors import get_connector

    async def fake_send(self, comment_id, text):
        return {"ok": False, "error": "нет права instagram_manage_comments"}

    monkeypatch.setattr(type(get_connector("instagram")), "reply_comment", fake_send)
    await kv.set(eng.PENDING_KEY, [
        {"platform": "instagram", "comment_id": "c1", "reply": "ответ", "author": "u"}])

    res = await eng.approve_all()
    assert res["sent"] == 0
    assert "instagram_manage_comments" in res["failed"][0]


@pytest.mark.asyncio
async def test_irrelevant_comments_are_skipped_but_marked_seen(client, monkeypatch):
    """Пропущенные тоже помечаем — иначе разбираем их снова и жжём токены."""
    from connectors import get_connector
    from agents.funnel_agent import FunnelAgent

    async def fake_read(limit=20):
        return _comments("c1")

    async def fake_reply(self, db, niche_id, comment, niche, **kw):
        return {"reply": "", "intent": "general", "should_reply": False}

    monkeypatch.setattr(get_connector("instagram"), "read_comments", fake_read)
    monkeypatch.setattr(FunnelAgent, "generate_reply", fake_reply)

    res = await eng.process_comments("instagram", limit=5)
    assert res["skipped"] == 1
    assert res["pending_approval"] == 0
    assert "c1" in await kv.get(eng.SEEN_KEY, [])


@pytest.mark.asyncio
async def test_unsupported_platform_does_not_crash(client):
    """Отсутствие поддержки комментариев — не ошибка, а честный отказ."""
    from connectors import get_connector
    res = await get_connector("vk").read_comments()
    assert res["ok"] is False
    assert res["supported"] is False


@pytest.mark.asyncio
async def test_discard_clears_queue(client):
    await kv.set(eng.PENDING_KEY, [{"platform": "instagram", "comment_id": "c1",
                                       "reply": "r", "author": "u"}])
    assert await eng.discard_pending() == 1
    assert await eng.pending() == []


@pytest.mark.asyncio
async def test_engagement_api(auth_client):
    r = await auth_client.get("/api/engagement")
    assert r.status_code == 200
    assert "pending_approval" in r.json()

    r2 = await auth_client.get("/api/engagement/pending")
    assert r2.json()["pending"] == []

    r3 = await auth_client.post("/api/engagement/discard")
    assert r3.json()["discarded"] == 0
