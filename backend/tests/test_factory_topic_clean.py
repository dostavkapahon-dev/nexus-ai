"""Модель ответила не JSON — отчёт не должен выдавать заготовку за анализ.

Живой случай: «🎯 Тема» показывала всю служебную постановку вместе с блоком
[ПАМЯТЬ АГЕНТА], хук был заглушкой «Смотри до конца», а шаг анализа стоял ✅.
"""
import pytest

from core import content_factory as cf


@pytest.mark.asyncio
async def test_non_json_answer_is_marked_and_theme_is_clean(monkeypatch):
    async def fake_call(model, system, prompt):
        return {"text": "не json вовсе"}

    async def fake_system():
        return ""

    from core.ai_router import ai_router
    monkeypatch.setattr(ai_router, "call", fake_call)
    monkeypatch.setattr(cf, "system_prompt", fake_system)
    plan = await cf._analyze(f"Самса\n\n{cf.MEMORY_MARK}\n• [hook] цифра в кадре")
    assert plan["theme"] == "Самса"
    assert cf.MEMORY_MARK not in plan["youtube"]["title"]
    assert plan["_offline"] and plan["_error"]
