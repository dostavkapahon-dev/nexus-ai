"""
Непроверенный результат нельзя выдавать за проверенный.

ТЗ §16 и §33: «Не показывать PASS, если реальный тест не выполнялся» и
«Создай шашлык — должен быть шашлык, не горы». Три места нарушали это молча:

  * проверка не смогла выполниться (нет зрения) → возвращалось ok, как будто
    кадр годный;
  * результат ПЕРЕгенерации помечался `checked: True` вообще без проверки;
  * кадр от запасного бесплатного генератора доходил без пометки, хотя по
    короткому запросу он выдаёт что угодно.
"""
import pytest

from core import hixiit


@pytest.fixture
def no_prompt_check(monkeypatch):
    async def passthrough(prompt, task, model, kind):
        return {"ok": True, "prompt": prompt, "checked": False, "reason": ""}

    monkeypatch.setattr(hixiit, "check_prompt", passthrough)


@pytest.mark.asyncio
async def test_unverifiable_result_carries_a_warning(monkeypatch, no_prompt_check):
    """Зрение недоступно — это «неизвестно», а не «годно»."""
    async def once(*a, **kw):
        return {"ok": True, "url": "https://x/i.png", "provider": "higgsfield_api",
                "kind": "image", "model": "soul_2"}

    async def unverifiable(url, task, kind):
        return {"ok": True, "checked": False, "reason": "нет ключа зрения"}

    monkeypatch.setattr(hixiit, "_generate_once", once)
    monkeypatch.setattr(hixiit, "check_result", unverifiable)

    res = await hixiit.generate("шашлык на углях", kind="image")

    assert res["warning"], "непроверенный результат обязан нести предупреждение"
    assert "не проверен" in res["warning"]


@pytest.mark.asyncio
async def test_free_substitute_is_always_flagged(monkeypatch, no_prompt_check):
    """Бесплатный генератор по короткому запросу рисует что угодно."""
    async def once(*a, **kw):
        return {"ok": True, "url": "https://x/free.png",
                "provider": "pollinations_free", "kind": "image", "model": "free"}

    async def good(url, task, kind):
        return {"ok": True, "checked": True, "reason": "ГОДНО"}

    monkeypatch.setattr(hixiit, "_generate_once", once)
    monkeypatch.setattr(hixiit, "check_result", good)

    res = await hixiit.generate("шашлык на углях", kind="image")

    assert "бесплатный" in res["warning"]
    assert "не гарантировано" in res["warning"]


@pytest.mark.asyncio
async def test_regenerated_result_is_actually_checked(monkeypatch, no_prompt_check):
    """Раньше перегенерация объявлялась проверенной без единой проверки."""
    calls = []

    async def once(*a, **kw):
        return {"ok": True, "url": f"https://x/{len(calls)}.png",
                "provider": "higgsfield_api", "kind": "image", "model": "soul_2"}

    async def verdicts(url, task, kind):
        calls.append(url)
        if len(calls) == 1:
            return {"ok": False, "checked": True, "reason": "БРАК: это горы, а не шашлык"}
        return {"ok": False, "checked": True, "reason": "БРАК: снова не шашлык"}

    monkeypatch.setattr(hixiit, "_generate_once", once)
    monkeypatch.setattr(hixiit, "check_result", verdicts)

    res = await hixiit.generate("шашлык на углях", kind="image")

    assert len(calls) == 2, "результат перегенерации обязан проверяться"
    assert res["regenerated"] is True
    assert res["qc"]["ok"] is False, "плохой повтор нельзя объявлять годным"
    assert "не прошёл проверку" in res["warning"]


@pytest.mark.asyncio
async def test_good_result_has_no_warning(monkeypatch, no_prompt_check):
    """Лишние предупреждения обесценивают настоящие."""
    async def once(*a, **kw):
        return {"ok": True, "url": "https://x/i.png", "provider": "higgsfield_api",
                "kind": "image", "model": "soul_2"}

    async def good(url, task, kind):
        return {"ok": True, "checked": True, "reason": "ГОДНО"}

    monkeypatch.setattr(hixiit, "_generate_once", once)
    monkeypatch.setattr(hixiit, "check_result", good)

    res = await hixiit.generate("шашлык на углях", kind="image")

    assert "warning" not in res


@pytest.mark.asyncio
async def test_successful_regeneration_is_marked_verified(monkeypatch, no_prompt_check):
    """Если повтор действительно годный — так и должно быть сказано."""
    calls = []

    async def once(*a, **kw):
        return {"ok": True, "url": f"https://x/{len(calls)}.png",
                "provider": "higgsfield_api", "kind": "image", "model": "soul_2"}

    async def verdicts(url, task, kind):
        calls.append(url)
        if len(calls) == 1:
            return {"ok": False, "checked": True, "reason": "БРАК: горы"}
        return {"ok": True, "checked": True, "reason": "ГОДНО: шашлык на мангале"}

    monkeypatch.setattr(hixiit, "_generate_once", once)
    monkeypatch.setattr(hixiit, "check_result", verdicts)

    res = await hixiit.generate("шашлык на углях", kind="image")

    assert res["qc"]["ok"] is True
    assert "warning" not in res


# ── предупреждение должно доходить до человека ────────────────────────────────
#
# ТЗ §20: человек должен видеть не только «готово», но и причину, когда кадр
# сделан запасным генератором или не проверен. Раньше `warning` оседал в поле
# результата и до чата не доходил — получался молчаливый «успех» с чужой
# картинкой.

@pytest.mark.asyncio
async def test_warning_reaches_the_chat():
    from core import marketing_director as md
    said = []

    async def on_step(text):
        said.append(text)

    await md._notify_warning(on_step, {"ok": True, "url": "https://x/i.png",
                                       "warning": "кадр нарисовал бесплатный генератор"})

    assert said and "бесплатный" in said[0]
    assert said[0].startswith("⚠️")


@pytest.mark.asyncio
async def test_clean_result_says_nothing_extra():
    from core import marketing_director as md
    said = []

    async def on_step(text):
        said.append(text)

    await md._notify_warning(on_step, {"ok": True, "url": "https://x/i.png"})

    assert said == []


@pytest.mark.asyncio
async def test_broken_notification_does_not_kill_the_task():
    """Уведомление — не повод потерять уже готовый результат."""
    from core import marketing_director as md

    async def boom(text):
        raise RuntimeError("чат недоступен")

    await md._notify_warning(boom, {"warning": "что-то не так"})
