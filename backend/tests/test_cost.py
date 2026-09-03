"""Учёт расходов: единая касса, привязка к задаче, бюджет, реальный ai_mode."""
import pytest

from core import cost_tracker as ct
from core import task_manager as tm


@pytest.fixture
def with_key(monkeypatch):
    """Ключ провайдера. Без него система намеренно не идёт в сеть, а учёт
    расходов проверяется как раз на состоявшихся вызовах."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")


@pytest.mark.asyncio
async def test_record_writes_to_agent_log(client):
    before = (await ct.spend(24))["cost_usd"]
    await ct.record(model="deepseek-chat", tokens=1000, cost=0.0014, agent="copywriter")
    after = await ct.spend(24)
    assert after["cost_usd"] == pytest.approx(before + 0.0014)
    assert after["calls"] >= 1


@pytest.mark.asyncio
async def test_router_call_is_tracked_even_outside_base_agent(client, monkeypatch, with_key):
    """Ключевая дыра аудита: вызовы вне BaseAgent шли мимо учёта."""
    from core import ai_router as ar

    async def fake_free(self, model, system, prompt):
        return {"text": "ok", "tokens": 500, "cost": 0.0007, "model_used": model}

    monkeypatch.setattr(ar.AIRouter, "_call_deepseek", fake_free)
    before = (await ct.spend(24))["cost_usd"]

    await ar.ai_router.call("deepseek-chat", "sys", "prompt")

    after = (await ct.spend(24))["cost_usd"]
    assert after == pytest.approx(before + 0.0007)


@pytest.mark.asyncio
async def test_cost_attaches_to_running_task(client, monkeypatch, with_key):
    """Расход внутри задачи должен попасть именно в неё — через контекст."""
    from core import ai_router as ar

    async def fake(self, model, system, prompt):
        return {"text": "ok", "tokens": 200, "cost": 0.0003, "model_used": model}

    monkeypatch.setattr(ar.AIRouter, "_call_deepseek", fake)

    task_id = await tm.create("director", "с расходом")

    async def work():
        await ar.ai_router.call("deepseek-chat", "s", "p")
        return {"ok": True}

    await tm.run(task_id, work)

    t = await tm.get(task_id)
    assert t["cost_usd"] == pytest.approx(0.0003)
    assert t["tokens"] == 200
    assert any("deepseek" in m for m in t["models"])


@pytest.mark.asyncio
async def test_failed_call_is_recorded_as_error(client, monkeypatch, with_key):
    from core import ai_router as ar

    async def boom(self, model, system, prompt):
        raise RuntimeError("model not found")

    monkeypatch.setattr(ar.AIRouter, "_call_deepseek", boom)
    monkeypatch.setattr(ar, "FALLBACK_CHAIN", [])

    before = (await ct.spend(24))["calls"]
    with pytest.raises(RuntimeError):
        await ar.ai_router.call("deepseek-chat", "s", "p")
    after = (await ct.spend(24))["calls"]
    assert after > before          # ошибка тоже попала в журнал


@pytest.mark.asyncio
async def test_budget_status_flags_alert_and_exceeded(client, monkeypatch):
    monkeypatch.setenv("AI_BUDGET_USD_DAY", "0.01")
    await ct.record(model="gpt-4o", tokens=1000, cost=0.009, agent="test")
    st = await ct.budget_status()
    assert st["limit_usd"] == pytest.approx(0.01)
    assert st["alert"] is True

    await ct.record(model="gpt-4o", tokens=1000, cost=0.005, agent="test")
    st2 = await ct.budget_status()
    assert st2["exceeded"] is True


@pytest.mark.asyncio
async def test_breakdowns_by_model_and_agent(client):
    await ct.record(model="gpt-4o", tokens=100, cost=0.02, agent="copywriter")
    await ct.record(model="deepseek-chat", tokens=100, cost=0.001, agent="strategist")

    models = await ct.by_model(24)
    assert models[0]["cost_usd"] >= models[-1]["cost_usd"]      # отсортировано по убыванию
    assert any(m["model"] == "gpt-4o" for m in models)

    agents = await ct.by_agent(24)
    assert any(a["agent"] == "copywriter" for a in agents)


@pytest.mark.asyncio
async def test_ai_mode_selects_model_table(client):
    """economy/premium раньше был фикцией — теперь реально выбирает набор моделей."""
    from core.ai_router import pick_model, ECONOMY_MODELS, PREMIUM_MODELS

    eco = await pick_model("strategist", mode="economy")
    prem = await pick_model("strategist", mode="premium")
    assert eco == ECONOMY_MODELS["strategist"]
    assert prem == PREMIUM_MODELS["strategist"]
    assert eco != prem


@pytest.mark.asyncio
async def test_cost_api(auth_client):
    await ct.record(model="gpt-4o-mini", tokens=50, cost=0.0005, agent="adapter")

    r = await auth_client.get("/api/cost")
    assert r.status_code == 200
    data = r.json()
    assert "budget" in data and "by_model" in data and "by_agent" in data

    r2 = await auth_client.post("/api/cost/budget", json={"budget_usd_day": 3.5})
    assert r2.json()["budget_usd_day"] == 3.5
    assert (await ct.budget_limit()) == pytest.approx(3.5)
