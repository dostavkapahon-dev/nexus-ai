"""Claude — главный мозг, подзадачи уходят Gemini/DeepSeek/OpenAI/Perplexity."""
import pytest

from core import dispatch
from core import marketing_director as md


@pytest.fixture
def no_keys(monkeypatch):
    for env in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY",
                "PERPLEXITY_API_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(env, raising=False)


@pytest.fixture
def calls(monkeypatch):
    """Перехватывает обращения к ai_router: что за модель и с каким промптом."""
    seen = []

    async def fake(model, system, prompt):
        seen.append({"model": model, "system": system, "prompt": prompt})
        return {"text": "готово", "tokens": 42, "cost": 0.001, "model_used": model}

    monkeypatch.setattr(dispatch.ai_router, "call", fake)
    return seen


def test_no_executors_without_keys(no_keys):
    assert dispatch.available_executors() == []
    assert dispatch.cheapest_available() is None


def test_available_follows_keys(no_keys, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    assert set(dispatch.available_executors()) == {"deepseek", "openai"}


def test_cheapest_available_is_picked(no_keys, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")      # gpt-4o — дорогой
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")    # deepseek-chat — дешёвый
    assert dispatch.cheapest_available() == "deepseek"


def test_executors_doc_hides_unavailable(no_keys, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    doc = dispatch.executors_doc()
    assert "gemini" in doc
    assert "openai" not in doc and "deepseek" not in doc


def test_executors_doc_without_keys_tells_what_to_do(no_keys):
    assert "GEMINI_API_KEY" in dispatch.executors_doc()


async def test_delegate_routes_to_requested_model(no_keys, monkeypatch, calls):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    r = await dispatch.delegate("deepseek", "напиши хук")
    assert r["ok"] is True
    assert r["executor"] == "deepseek"
    assert calls[0]["model"] == "deepseek-chat"
    assert "напиши хук" in calls[0]["prompt"]


async def test_delegate_passes_context(no_keys, monkeypatch, calls):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    await dispatch.delegate("gemini", "перепиши", context="исходный пост")
    assert "исходный пост" in calls[0]["prompt"]


async def test_delegate_substitutes_unknown_executor(no_keys, monkeypatch, calls):
    """Опечатка в имени не должна съедать шаг дирижёра."""
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    r = await dispatch.delegate("gpt5-turbo-max", "задача")
    assert r["ok"] is True
    assert r["executor"] == "gemini"
    assert r["substituted_for"] == "gpt5-turbo-max"


async def test_delegate_substitutes_executor_without_key(no_keys, monkeypatch, calls):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    r = await dispatch.delegate("openai", "задача")   # ключа OpenAI нет
    assert r["executor"] == "deepseek"
    assert r["substituted_for"] == "openai"


async def test_delegate_without_any_key_explains(no_keys):
    r = await dispatch.delegate("gemini", "задача")
    assert r["ok"] is False
    assert "GEMINI_API_KEY" in r["error"]


async def test_delegate_reports_router_fallback(no_keys, monkeypatch):
    """ai_router мог уйти на другого провайдера — дирижёр обязан это видеть."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")

    async def fallback(model, system, prompt):
        return {"text": "ok", "tokens": 1, "cost": 0, "model_used": "gemini-2.0-flash-lite"}

    monkeypatch.setattr(dispatch.ai_router, "call", fallback)
    r = await dispatch.delegate("deepseek", "задача")
    assert "фолбэком" in r["note"]
    assert r["model_used"] == "gemini-2.0-flash-lite"


async def test_delegate_surfaces_error(no_keys, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")

    async def boom(*a, **k):
        raise RuntimeError("All AI providers failed. quota")

    monkeypatch.setattr(dispatch.ai_router, "call", boom)
    r = await dispatch.delegate("gemini", "задача")
    assert r["ok"] is False
    assert "quota" in r["error"]


def test_all_executor_models_are_known_to_router():
    from core.ai_router import AI_ROUTING, COST_PER_1K
    for name, spec in dispatch.EXECUTORS.items():
        assert spec["model"] in AI_ROUTING, name
        assert spec["model"] in COST_PER_1K, name
        assert AI_ROUTING[spec["model"]] == spec["provider"], name


def test_routing_table_shape(no_keys, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    t = dispatch.routing_table()
    assert "claude" in t["director"]
    assert t["default_executor"] == "gemini"
    avail = {e["name"]: e["available"] for e in t["executors"]}
    assert avail == {"gemini": True, "deepseek": False, "openai": False,
                     "perplexity": False, "claude": True}


# ── дирижёр действительно умеет звать delegate ────────────────────────────────

def test_director_exposes_delegate_tool():
    names = [t["name"] for t in md.TOOLS]
    assert names[0] == "delegate", "delegate должен быть первым — основной инструмент"
    assert {"run_browser", "make_video", "publish", "done"} <= set(names)


def test_director_system_lists_only_available_executors(no_keys, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    sysprompt = md._full_system()
    assert "deepseek" in sysprompt
    assert "perplexity" not in sysprompt


async def test_director_delegate_tool_calls_dispatch(no_keys, monkeypatch, calls):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    r = await md._exec_tool("delegate", {"executor": "gemini", "task": "напиши пост"})
    assert r["ok"] is True and r["text"] == "готово"
    assert calls[0]["model"] == "gemini-2.0-flash"


async def test_unknown_tool_still_reported(no_keys):
    r = await md._exec_tool("teleport", {})
    assert r["ok"] is False
