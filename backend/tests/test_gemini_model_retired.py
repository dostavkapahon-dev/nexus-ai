"""Снятую модель надо переживать, а не падать.

Живой отказ: «404 This model models/gemini-2.5-flash-lite is no longer
available to new users. Please update your code to use
models/gemini-3.5-flash-lite». Он приходил на всех дешёвых агентах — отсюда
«пустой ответ провайдера» и плохой контент.

Запасной путь при этом был мёртвым: при отказе звался `resolve_gemini_model()`,
но его результат кэширован, возвращалась ТА ЖЕ снятая модель, `alt == model`,
и вызов падал.
"""
import pytest

from core import ai_router as r

RETIRED = ("404 This model models/gemini-2.5-flash-lite is no longer available "
           "to new users. Please update your code to use "
           "models/gemini-3.5-flash-lite for the latest features.")


def test_replacement_is_taken_from_the_provider():
    """Провайдер сам называет замену — это надёжнее нашего списка."""
    assert r._replacement_from_error(RETIRED) == "gemini-3.5-flash-lite"


def test_retired_model_itself_is_not_returned():
    assert r._replacement_from_error(RETIRED) != "gemini-2.5-flash-lite"


def test_unrelated_error_gives_no_replacement():
    assert r._replacement_from_error("429 quota exceeded") == ""
    assert r._replacement_from_error("timeout") == ""


def test_single_model_mention_is_not_a_replacement():
    """Одно упоминание — это снятая модель, а не замена."""
    assert r._replacement_from_error("model models/gemini-x not found") == ""


def test_empty_error_is_safe():
    assert r._replacement_from_error(None) == ""


def test_resolver_drops_the_failed_model(monkeypatch):
    """Главный дефект: кэш возвращал ту же снятую модель."""
    r._GEMINI_RESOLVED = "gemini-2.5-flash-lite"
    monkeypatch.setenv("GEMINI_API_KEY", "k")

    class _Resp:
        @staticmethod
        def json():
            return {"models": [
                {"name": "models/gemini-2.5-flash-lite",
                 "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-3.5-flash-lite",
                 "supportedGenerationMethods": ["generateContent"]},
            ]}

    monkeypatch.setattr("httpx.get", lambda *a, **kw: _Resp())
    got = r.resolve_gemini_model(avoid="gemini-2.5-flash-lite")
    assert got == "gemini-3.5-flash-lite"


def test_resolver_without_avoid_still_works(monkeypatch):
    r._GEMINI_RESOLVED = None
    monkeypatch.setenv("GEMINI_API_KEY", "k")

    class _Resp:
        @staticmethod
        def json():
            return {"models": [{"name": "models/gemini-3.5-flash-lite",
                                "supportedGenerationMethods": ["generateContent"]}]}

    monkeypatch.setattr("httpx.get", lambda *a, **kw: _Resp())
    assert r.resolve_gemini_model() == "gemini-3.5-flash-lite"


def test_no_models_left_after_avoid(monkeypatch):
    """Если кроме снятой ничего нет — честный None, а не та же модель."""
    r._GEMINI_RESOLVED = None
    monkeypatch.setenv("GEMINI_API_KEY", "k")

    class _Resp:
        @staticmethod
        def json():
            return {"models": [{"name": "models/gemini-2.5-flash-lite",
                                "supportedGenerationMethods": ["generateContent"]}]}

    monkeypatch.setattr("httpx.get", lambda *a, **kw: _Resp())
    assert r.resolve_gemini_model(avoid="gemini-2.5-flash-lite") is None


@pytest.mark.asyncio
async def test_search_follows_the_replacement_hint(monkeypatch):
    """Поиск не должен умирать вместе с очередной снятой моделью.

    С живого сервера: «google: 404 models/gemini-2.5-flash-lite is no longer
    available… use models/gemini-3.5-flash-lite». Замена названа самим Google —
    её и берём.
    """
    from core import websearch
    tried = []

    class _Web:
        uri = "https://example.test/a"
        title = "Статья"

    class _Chunk:
        web = _Web()

    class _Meta:
        grounding_chunks = [_Chunk()]

    class _Cand:
        grounding_metadata = _Meta()

    class _Resp:
        candidates = [_Cand()]

    class _Model:
        def __init__(self, name, **kw):
            self.name = name

        def generate_content(self, prompt):
            tried.append(self.name)
            if self.name == "gemini-2.5-flash-lite":
                raise RuntimeError(
                    "404 This model models/gemini-2.5-flash-lite is no longer "
                    "available to new users. Please update your code to use "
                    "models/gemini-3.5-flash-lite for the latest features")
            return _Resp()

    import google.generativeai as genai
    monkeypatch.setattr(genai, "configure", lambda **k: None)
    monkeypatch.setattr(genai, "GenerativeModel", _Model)
    monkeypatch.setattr("core.ai_router.resolve_gemini_model",
                        lambda avoid="": "gemini-2.5-flash-lite")
    monkeypatch.setenv("GEMINI_API_KEY", "k")

    items = await websearch._search_gemini("тренды", 3)
    assert tried == ["gemini-2.5-flash-lite", "gemini-3.5-flash-lite"]
    assert items[0]["url"] == "https://example.test/a"
