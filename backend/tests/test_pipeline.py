"""Конвейер фабрики: шаги попадают в журнал задачи, согласование не выдаётся за успех."""
import pytest

from core import content_factory as cf
from core import task_manager as tm


@pytest.mark.asyncio
async def test_steps_land_in_task_journal(client, monkeypatch):
    """Раньше report["steps"] жил только в ответе и пропадал вместе с ним."""
    async def fake_analyze(topic):
        return {"theme": "тест", "hook_text": "хук", "instagram": {"caption": "c"}}

    async def fake_brief(plan):
        return {"storyboard": [{"t": "0-3", "image_prompt": "кадр", "overlay": "текст"}],
                "cover_prompt": "обложка"}

    async def fake_wow(brief):
        return {"score": 9}

    async def fake_image(prompt, platform="telegram"):
        return "https://img/cover.png"

    monkeypatch.setattr(cf, "_analyze", fake_analyze)
    import core.creative_director as cd
    monkeypatch.setattr(cd, "build_brief", fake_brief)
    monkeypatch.setattr(cd, "wow_review", fake_wow)
    import core.media_generator as mg
    monkeypatch.setattr(mg, "generate_image", fake_image)

    task_id = await tm.create(kind="factory", goal="тест конвейера")
    res = await tm.run(task_id, lambda: cf.run_factory(topic="тест", dry_run=True,
                                                       want_video=False))
    assert res["ok"] is True

    task = await tm.get(task_id)
    names = [s.get("action") for s in (task["steps"] or [])]
    assert "analysis" in names
    assert "brief" in names
    assert "storyboard_frames" in names


@pytest.mark.asyncio
async def test_journal_has_no_duplicates(client, monkeypatch):
    """Журналируем пачками — шаг не должен попасть в журнал дважды."""
    report = {"steps": [{"step": "a", "ok": True}]}
    task_id = await tm.create(kind="factory", goal="дубликаты")

    from core.cost_tracker import current_task_id
    token = current_task_id.set(task_id)
    try:
        await cf._flush_steps(report)
        await cf._flush_steps(report)                      # повтор без новых шагов
        report["steps"].append({"step": "b", "ok": False, "error": "сломалось"})
        await cf._flush_steps(report)
    finally:
        current_task_id.reset(token)

    task = await tm.get(task_id)
    names = [s.get("action") for s in (task["steps"] or [])]
    assert names.count("a") == 1
    assert names.count("b") == 1
    assert any(s.get("error") == "сломалось" for s in task["steps"])


@pytest.mark.asyncio
async def test_awaiting_approval_is_not_completed(client):
    """Контент, ждущий аппрува человека, — это WAITING, а не «готово»."""
    task_id = await tm.create(kind="factory", goal="согласование")
    await tm.run(task_id, lambda: _awaiting())

    task = await tm.get(task_id)
    assert task["status"] == tm.WAITING


async def _awaiting():
    return {"ok": True, "awaiting_approval": True}


@pytest.mark.asyncio
async def test_plain_success_still_completes(client):
    task_id = await tm.create(kind="factory", goal="обычный успех")
    await tm.run(task_id, lambda: _done())
    task = await tm.get(task_id)
    assert task["status"] == tm.COMPLETED


async def _done():
    return {"ok": True}
