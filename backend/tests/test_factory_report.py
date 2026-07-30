"""Конвейер контент-фабрики не должен рапортовать об успехе, когда генерация упала."""
import pytest

from core import content_factory as cf
from core import self_critique


async def test_pre_check_marks_unchecked_when_ai_unavailable(monkeypatch):
    """Без ключей ИИ самопроверка не блокирует конвейер, но и не врёт, что проверила."""
    async def boom(*a, **k):
        raise RuntimeError("All AI providers failed. gpt-4o → no key")

    monkeypatch.setattr(self_critique.ai_router, "call", boom)
    chk = await self_critique.pre_check("content_factory", "тема")
    assert chk["checked"] is False
    assert chk["ready"] is True          # конвейер не блокируем
    assert "All AI providers failed" in chk["error"]
    assert chk["improved_task"] == "тема"


async def test_pre_check_marks_checked_on_success(monkeypatch):
    async def ok(*a, **k):
        return {"text": '{"ready": false, "missing": ["ниша"], "improved_task": "лучше"}'}

    monkeypatch.setattr(self_critique.ai_router, "call", ok)
    chk = await self_critique.pre_check("content_factory", "тема")
    assert chk["checked"] is True
    assert chk["ready"] is False
    assert chk["missing"] == ["ниша"]


@pytest.fixture
def dead_ai(monkeypatch):
    """Полностью недоступный ИИ — состояние свежей установки без ключей."""
    async def boom(*a, **k):
        raise RuntimeError("All AI providers failed. no keys")

    monkeypatch.setattr("core.ai_router.ai_router.call", boom)
    monkeypatch.setattr(cf, "_send_report", _noop)
    return boom


async def _noop(*a, **k):
    return None


async def test_factory_reports_failure_without_keys(dead_ai):
    report = await cf.run_factory(topic="тест", platforms=["telegram"],
                                  dry_run=True, want_video=False)
    assert report["ok"] is False, report["steps"]
    assert "analysis" in report["failed_steps"]
    assert "brief" in report["failed_steps"]
    assert "GEMINI_API_KEY" in report["hint"]


async def test_self_check_step_not_ok_without_keys(dead_ai):
    report = await cf.run_factory(topic="тест", platforms=["telegram"],
                                  dry_run=True, want_video=False)
    step = next(s for s in report["steps"] if s["step"] == "self_check")
    assert step["ok"] is False


async def test_empty_storyboard_is_not_a_success(dead_ai):
    report = await cf.run_factory(topic="тест", platforms=["telegram"],
                                  dry_run=True, want_video=False)
    frames = next(s for s in report["steps"] if s["step"] == "storyboard_frames")
    assert frames["count"] == 0
    assert frames["ok"] is False


async def test_factory_ok_when_critical_steps_pass(monkeypatch):
    """Провал только видео — результат (текст + обложка) всё равно годный."""
    monkeypatch.setattr(cf, "_send_report", _noop)

    async def analyze(topic):
        return {"theme": "тема", "hook_text": "хук", "_format": "auto",
                "image_prompt": "poster", "instagram": {"caption": "c", "hashtags": []},
                "telegram": {"post": "p"}}

    async def brief(plan):
        return {"cover_prompt": "poster", "avatar_script": "s",
                "storyboard": [{"t": "0-3", "overlay": "o", "image_prompt": "frame"}],
                "video_motion_prompt": "m", "tone": "bold"}

    async def wow(_brief):
        return {"score": 9}

    monkeypatch.setattr(cf, "_analyze", analyze)
    monkeypatch.setattr("core.creative_director.build_brief", brief)
    monkeypatch.setattr("core.creative_director.wow_review", wow)

    report = await cf.run_factory(topic="тест", platforms=["telegram"],
                                  dry_run=True, want_video=False)
    assert report["ok"] is True
    assert report["failed_steps"] == [] or "analysis" not in report["failed_steps"]
