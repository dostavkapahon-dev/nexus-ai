"""NVIDIA NIM — бесплатные открытые модели через OpenAI-совместимый эндпоинт."""
import httpx
import pytest

from core import ai_router as ar
from core import dispatch


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(ar, "_NVIDIA_RESOLVED", None)
    for env in ar.PROVIDER_KEY_ENV.values():
        monkeypatch.delenv(env, raising=False)


def _catalog(monkeypatch, ids, status=200):
    class Resp:
        status_code = status

        def json(self):
            return {"data": [{"id": i} for i in ids]}

    monkeypatch.setattr(httpx, "get", lambda *a, **k: Resp())


def test_nvidia_registered_as_provider():
    assert ar.AI_ROUTING["nvidia-free"] == "nvidia"
    assert ar.PROVIDER_KEY_ENV["nvidia"] == "NVIDIA_API_KEY"
    assert ar.COST_PER_1K["nvidia-free"] == 0.0


def test_nvidia_is_first_in_fallback_chain():
    """Бесплатный провайдер должен пробоваться раньше платных."""
    assert ar.FALLBACK_CHAIN[0] == "nvidia-free"


def test_resolve_without_key():
    assert ar.resolve_nvidia_model() is None


def test_resolve_prefers_llama_70b(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-x")
    _catalog(monkeypatch, ["nvidia/nv-embed-v1", "meta/llama-3.3-70b-instruct",
                           "qwen/qwen2.5-72b-instruct"])
    assert ar.resolve_nvidia_model() == "meta/llama-3.3-70b-instruct"


def test_resolve_skips_embedding_and_rerank_models(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-x")
    _catalog(monkeypatch, ["nvidia/nv-embedqa-e5-v5", "nvidia/rerank-qa-mistral-4b",
                           "google/gemma-2-9b-it"])
    assert ar.resolve_nvidia_model() == "google/gemma-2-9b-it"


def test_resolve_falls_back_to_any_model(monkeypatch):
    """Каталог NVIDIA меняется — незнакомые имена не должны ронять подбор."""
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-x")
    _catalog(monkeypatch, ["some-vendor/brand-new-model-2027"])
    assert ar.resolve_nvidia_model() == "some-vendor/brand-new-model-2027"


def test_resolve_caches(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-x")
    calls = {"n": 0}

    class Resp:
        def json(self):
            calls["n"] += 1
            return {"data": [{"id": "meta/llama-3.3-70b-instruct"}]}

    monkeypatch.setattr(httpx, "get", lambda *a, **k: Resp())
    ar.resolve_nvidia_model()
    ar.resolve_nvidia_model()
    assert calls["n"] == 1


def test_resolve_survives_network_error(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-x")

    def boom(*a, **k):
        raise OSError("dns fail")

    monkeypatch.setattr(httpx, "get", boom)
    assert ar.resolve_nvidia_model() is None


async def test_call_nvidia_uses_resolved_id_and_base_url(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-x")
    monkeypatch.setattr(ar, "resolve_nvidia_model", lambda: "meta/llama-3.3-70b-instruct")
    seen = {}

    class FakeClient:
        def __init__(self, api_key, base_url):
            seen["base_url"] = base_url
            seen["api_key"] = api_key
            self.chat = self

        @property
        def completions(self):
            return self

        async def create(self, model, max_tokens, messages):
            seen["model"] = model
            seen["system"] = messages[0]["content"]

            class U:
                total_tokens = 123

            class M:
                content = "ответ Llama"

            class C:
                message = M()

            class R:
                choices = [C()]
                usage = U()

            return R()

    monkeypatch.setattr(ar.openai, "AsyncOpenAI", FakeClient)
    res = await ar.AIRouter()._call_nvidia("nvidia-free", "ты редактор", "напиши хук")

    assert seen["base_url"] == "https://integrate.api.nvidia.com/v1"
    assert seen["api_key"] == "nvapi-x"
    assert seen["model"] == "meta/llama-3.3-70b-instruct"  # псевдоним развернулся
    assert res["text"] == "ответ Llama"
    assert res["tokens"] == 123
    assert res["cost"] == 0.0                              # платим кредитами, не деньгами
    assert res["model_used"] == "nvidia:meta/llama-3.3-70b-instruct"


async def test_call_nvidia_without_catalog_raises(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-x")
    monkeypatch.setattr(ar, "resolve_nvidia_model", lambda: None)
    with pytest.raises(RuntimeError, match="NVIDIA_API_KEY"):
        await ar.AIRouter()._call_nvidia("nvidia-free", "sys", "hi")


async def test_router_dispatches_nvidia_provider(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-x")
    called = {}

    async def fake(self, model, system, prompt):
        called["model"] = model
        return {"text": "ok", "tokens": 1, "cost": 0.0, "model_used": "nvidia:meta/llama"}

    monkeypatch.setattr(ar.AIRouter, "_call_nvidia", fake)
    r = await ar.AIRouter().call("nvidia-free", "sys", "hi")
    assert called["model"] == "nvidia-free"
    assert r["cost"] == 0.0


# ── исполнитель у дирижёра ────────────────────────────────────────────────────

def test_nvidia_is_an_executor():
    assert dispatch.EXECUTORS["nvidia"]["model"] == "nvidia-free"
    assert dispatch.EXECUTORS["nvidia"]["provider"] == "nvidia"


def test_nvidia_is_default_executor_when_available(monkeypatch):
    """Бесплатный NVIDIA должен обходить платных по цене."""
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-x")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert dispatch.cheapest_available() == "nvidia"


def test_director_sees_nvidia(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-x")
    doc = dispatch.executors_doc()
    assert "nvidia" in doc and "Llama" in doc


async def test_delegate_to_nvidia_is_not_reported_as_fallback(monkeypatch):
    """`nvidia-free` всегда разворачивается в конкретный id — это не фолбэк."""
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-x")

    async def fake(model, system, prompt):
        return {"text": "готово", "tokens": 5, "cost": 0.0,
                "model_used": "nvidia:meta/llama-3.3-70b-instruct"}

    monkeypatch.setattr(dispatch.ai_router, "call", fake)
    r = await dispatch.delegate("nvidia", "напиши пост")
    assert r["ok"] is True
    assert "note" not in r
    assert r["cost"] == 0.0
