"""Долгая задача должна подавать признаки жизни (ТЗ §36).

Раньше человек получал «взял задачу» и тишину на несколько минут: зависшая
система выглядит ровно так же, как работающая.
"""
import pytest

from core import marketing_director as md


@pytest.mark.asyncio
async def test_step_is_reported_in_human_words():
    seen = []

    await md._notify(seen.append, "make_video")

    assert seen == ["🎬 Генерирую видео"], "человеку нужен шаг, а не имя инструмента"


@pytest.mark.asyncio
async def test_internal_steps_are_not_shown():
    """`done` — служебный шаг конвейера, показывать его незачем."""
    seen = []
    await md._notify(seen.append, "done")
    assert seen == []


@pytest.mark.asyncio
async def test_broken_notifier_does_not_kill_the_task():
    """Сбой уведомления не должен ронять саму работу."""
    def boom(label):
        raise RuntimeError("telegram недоступен")

    await md._notify(boom, "make_image")   # не должно бросить


@pytest.mark.asyncio
async def test_async_notifier_is_awaited():
    seen = []

    async def notify(label):
        seen.append(label)

    await md._notify(notify, "web_search")
    assert seen == ["🔎 Ищу в интернете"]


@pytest.mark.asyncio
async def test_every_user_facing_tool_has_a_label():
    """Инструмент без подписи — это снова тишина на его время."""
    from core.marketing_director import TOOLS

    names = {t["name"] for t in TOOLS} - {"done"}
    assert names <= set(md.STEP_LABELS), f"без подписи: {names - set(md.STEP_LABELS)}"


@pytest.mark.asyncio
async def test_director_reports_steps_it_runs(monkeypatch):
    """Сквозная проверка: шаг реально доходит до получателя."""
    seen = []

    async def fake_exec(name, inp):
        return {"ok": True}

    monkeypatch.setattr(md, "_exec_tool", fake_exec)

    class _Block:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    class _Resp:
        content = [_Block(type="tool_use", name="make_image", input={"prompt": "x"},
                          id="t1")]

    class _Messages:
        async def create(self, **kw):
            # второй раз завершаем, иначе цикл пойдёт по кругу
            if seen:
                return _Block(content=[_Block(type="tool_use", name="done",
                                              input={"summary": "готово"}, id="t2")])
            return _Resp()

    class _Client:
        messages = _Messages()

    monkeypatch.setattr(md.anthropic, "AsyncAnthropic", lambda api_key=None: _Client())
    monkeypatch.setattr(md, "_full_system", _system)

    res = await md._run_director_anthropic("сделай картинку", on_step=seen.append)

    assert "🎨 Генерирую изображение" in seen
    assert res["status"] == "done"


async def _system():
    return "system"
