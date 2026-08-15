"""
Реестр агентов.

Проверяется то, ради чего он появился: роли из ТЗ существуют явно, роль без
доступов честно считается нерабочей и не предлагается дирижёру, а `delegate`
различает роль агента и модель-исполнителя.
"""
import pytest

from agents import registry as reg


ROLES_FROM_SPEC = {"director", "research", "instagram", "tiktok", "telegram",
                   "content_strategist", "script", "video", "copywriter",
                   "analytics", "publisher"}


def test_all_roles_from_spec_exist():
    assert ROLES_FROM_SPEC <= set(reg.REGISTRY)
    for spec in reg.REGISTRY.values():
        assert spec.title and spec.role
        # Роль без реализации — это обещание, которое некому выполнить.
        assert spec.backed_by or spec.system


def test_role_without_keys_is_not_offered(monkeypatch):
    monkeypatch.delenv("INSTAGRAM_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")

    assert "instagram" not in reg.available()
    assert "telegram" in reg.available()

    doc = reg.agents_doc()
    assert "instagram" not in doc and "telegram" in doc
    # Дирижёр не роль-исполнитель для delegate, он сам вызывающий.
    assert "director" not in doc


def test_describe_shows_what_is_missing(monkeypatch):
    monkeypatch.delenv("TIKTOK_ACCESS_TOKEN", raising=False)
    item = next(i for i in reg.describe() if i["key"] == "tiktok")
    assert item["ready"] is False and "TIKTOK_ACCESS_TOKEN" in item["missing"]


@pytest.mark.asyncio
async def test_run_refuses_role_without_access(monkeypatch):
    monkeypatch.delenv("INSTAGRAM_ACCESS_TOKEN", raising=False)
    res = await reg.run("instagram", "собери метрики")
    assert res["ok"] is False and "не хватает доступов" in res["error"]


@pytest.mark.asyncio
async def test_run_unknown_role():
    res = await reg.run("несуществующий", "сделай что-нибудь")
    assert res["ok"] is False


@pytest.mark.asyncio
async def test_research_role_uses_websearch(monkeypatch):
    from core import websearch as ws

    async def fake_deep(topic, pages=3, niche_id=""):
        return {"ok": True, "summary": "итог", "sources": [{"url": "https://x.y"}]}

    monkeypatch.setattr(ws, "deep_research", fake_deep)
    res = await reg.run("research", "что происходит в нише")
    assert res["ok"] and res["text"] == "итог" and res["agent"] == "research"


@pytest.mark.asyncio
async def test_director_delegate_routes_to_agent_role(monkeypatch):
    """`delegate` должен различать роль агента и имя модели."""
    from core import marketing_director as md

    called = {}

    async def fake_run(key, task, context=""):
        called["key"] = key
        return {"ok": True, "agent": key, "text": "готово"}

    monkeypatch.setattr(reg, "run", fake_run)
    res = await md._exec_tool("delegate", {"executor": "copywriter", "task": "напиши пост"})
    assert res["ok"] and called["key"] == "copywriter"


@pytest.mark.asyncio
async def test_director_delegate_still_routes_to_models(monkeypatch):
    """Имя модели по-прежнему уходит в dispatch, а не в реестр ролей."""
    from core import marketing_director as md
    from core import dispatch

    seen = {}

    async def fake_delegate(executor, task, system="", context=""):
        seen["executor"] = executor
        return {"ok": True, "text": "ответ"}

    monkeypatch.setattr(dispatch, "delegate", fake_delegate)
    res = await md._exec_tool("delegate", {"executor": "gemini", "task": "напиши пост"})
    assert res["ok"] and seen["executor"] == "gemini"


@pytest.mark.asyncio
async def test_agents_are_not_publishing_on_their_own():
    """Принцип ТЗ: агенты выполняют работу, но не управляют системой сами."""
    import pathlib

    agents_dir = pathlib.Path(__file__).resolve().parents[1] / "agents"
    for path in agents_dir.glob("*.py"):
        if path.name == "registry.py":
            continue        # реестр лишь описывает, где живёт публикация, и не вызывает её
        code = path.read_text(encoding="utf-8")
        assert "publish_queue" not in code, f"{path.name} публикует в обход дирижёра"
        assert "from publishers" not in code, f"{path.name} публикует в обход дирижёра"


@pytest.mark.asyncio
async def test_api_lists_agents(auth_client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    body = (await auth_client.get("/api/agents")).json()
    keys = {a["key"] for a in body["agents"]}
    assert ROLES_FROM_SPEC <= keys
    telegram = next(a for a in body["agents"] if a["key"] == "telegram")
    assert telegram["ready"] is True


@pytest.mark.asyncio
async def test_api_run_creates_task(auth_client, monkeypatch):
    async def fake_run(key, task, context=""):
        return {"ok": True, "agent": key, "text": "сделано"}

    monkeypatch.setattr(reg, "run", fake_run)
    r = await auth_client.post("/api/agents/copywriter/run", json={"task": "пост про доставку"})
    body = r.json()
    assert body["ok"] and body["task_id"]

    # Запуск виден в общем журнале задач, а не исчезает бесследно.
    tasks = (await auth_client.get("/api/tasks")).json()["tasks"]
    assert any(t["id"] == body["task_id"] for t in tasks)


@pytest.mark.asyncio
async def test_api_run_unknown_agent(auth_client):
    r = await auth_client.post("/api/agents/нет-такого/run", json={"task": "х"})
    assert r.json()["ok"] is False
