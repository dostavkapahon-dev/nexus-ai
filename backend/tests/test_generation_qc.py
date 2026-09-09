"""Генерация не идёт вслепую: промпт проверяется до, результат — после.

Это самый дорогой шаг конвейера. Раньше промпт уходил в модель как есть, а на
результат никто не смотрел: брак доезжал до пользователя, а кредиты списывались.
"""
import pytest

from core import hixiit


@pytest.fixture
def generated(monkeypatch):
    """Успешная генерация без обращения к платформе."""
    calls = []

    async def once(task, kind="auto", ratio=None, image_url=None, allow_free=True):
        calls.append(task)
        return {"ok": True, "url": f"https://cdn/{len(calls)}.png", "kind": "image",
                "provider": "higgsfield_mcp", "model": "z_image"}

    monkeypatch.setattr(hixiit, "_generate_once", once)
    return calls


@pytest.mark.asyncio
async def test_prompt_is_repaired_before_generation(generated, monkeypatch):
    """Кривой промпт чинится до отправки, а не после списания кредитов."""
    async def check(prompt, task, model, kind):
        return {"ok": False, "prompt": "исправленный промпт", "checked": True,
                "reason": "не описана композиция"}

    monkeypatch.setattr(hixiit, "check_prompt", check)
    monkeypatch.setattr(hixiit, "check_result",
                        lambda *a, **k: _ok({"ok": True, "checked": True, "reason": ""}))

    res = await hixiit.generate("кадр", kind="image")

    assert generated[0] == "исправленный промпт"
    assert res["prompt_check"] == "не описана композиция"


@pytest.mark.asyncio
async def test_bad_result_triggers_exactly_one_retry(generated, monkeypatch):
    """Брак перегенерируется — но один раз: бесконечный цикл сжёг бы кредиты."""
    monkeypatch.setattr(hixiit, "check_prompt",
                        lambda p, t, m, k: _ok({"ok": True, "prompt": p, "checked": True,
                                                "reason": ""}))
    verdicts = iter([{"ok": False, "checked": True, "reason": "БРАК: лицо поплыло"}])

    async def check_result(url, task, kind):
        return next(verdicts, {"ok": True, "checked": True, "reason": ""})

    monkeypatch.setattr(hixiit, "check_result", check_result)

    res = await hixiit.generate("портрет", kind="image")

    assert len(generated) == 2, "ровно одна повторная попытка"
    assert res["regenerated"] is True
    assert "лицо поплыло" in res["qc"]["reason"]


@pytest.mark.asyncio
async def test_good_result_is_not_regenerated(generated, monkeypatch):
    monkeypatch.setattr(hixiit, "check_prompt",
                        lambda p, t, m, k: _ok({"ok": True, "prompt": p, "checked": True,
                                                "reason": ""}))
    monkeypatch.setattr(hixiit, "check_result",
                        lambda *a, **k: _ok({"ok": True, "checked": True, "reason": "ГОДНО"}))

    res = await hixiit.generate("кадр", kind="image")

    assert len(generated) == 1
    assert res["qc"]["ok"] is True


@pytest.mark.asyncio
async def test_qc_without_models_does_not_block_generation(generated, monkeypatch):
    """Нет ключей — проверок нет, но генерация обязана работать как раньше."""
    monkeypatch.setattr(hixiit, "check_prompt",
                        lambda p, t, m, k: _ok({"ok": True, "prompt": p, "checked": False,
                                                "reason": "нет модели для проверки"}))
    monkeypatch.setattr(hixiit, "check_result",
                        lambda *a, **k: _ok({"ok": True, "checked": False, "reason": ""}))

    res = await hixiit.generate("кадр", kind="image")

    assert res["ok"] and len(generated) == 1
    assert "prompt_check" not in res, "непроведённую проверку не выдаём за проведённую"


@pytest.mark.asyncio
async def test_qc_can_be_switched_off(generated, monkeypatch):
    """Внутренние шаги конвейера не должны платить за проверку дважды."""
    def boom(*a, **k):
        raise AssertionError("проверка не должна вызываться при qc=False")

    monkeypatch.setattr(hixiit, "check_prompt", boom)
    monkeypatch.setattr(hixiit, "check_result", boom)

    res = await hixiit.generate("кадр", kind="image", qc=False)
    assert res["ok"]


@pytest.mark.asyncio
async def test_prompt_check_failure_is_not_fatal(client, monkeypatch):
    """Отказ проверки — служебная неурядица, а не причина отменить задачу."""
    from core import ai_router

    monkeypatch.setattr(ai_router, "ai_available", lambda: True)

    async def broken(*a, **k):
        raise RuntimeError("модель недоступна")

    monkeypatch.setattr(ai_router.ai_router, "call", broken)

    res = await hixiit.check_prompt("промпт", "задача", "z_image", "image")
    assert res["ok"] is True and res["prompt"] == "промпт" and res["checked"] is False


@pytest.mark.asyncio
async def test_result_check_reads_the_verdict(client, monkeypatch):
    async def vision(url, question=None):
        return {"ok": True, "analysis": "БРАК: текст на картинке нечитаемый"}

    monkeypatch.setattr("core.vision.analyze_image", vision)

    res = await hixiit.check_result("https://cdn/x.png", "обложка", "image")
    assert res["ok"] is False and res["checked"] is True


def _ok(value):
    async def _inner(*a, **k):
        return value
    return _inner()


# Подмена async-функций синхронной лямбдой требует корутины — фикстуры выше
# возвращают её через _ok(), поэтому monkeypatch.setattr получает вызываемое,
# отдающее awaitable.
