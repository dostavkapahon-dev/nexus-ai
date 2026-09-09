"""Дирижёр должен опираться на свои результаты, а не только на общие рассуждения.

Цепочка обучения (ТЗ §29) уже была: метрики публикаций → уроки с реальными
цифрами → память навыков → фабрика контента. Но задача из Telegram идёт через
дирижёра, а он этой памяти не получал — то есть планировал, не зная, что у
аккаунта сработало, а что провалилось.
"""
import pytest

from core import marketing_director as md
from core import skills_store


@pytest.mark.asyncio
async def test_director_system_prompt_carries_account_experience(client, monkeypatch):
    monkeypatch.setattr(skills_store, "context_for",
                        lambda *a, **k: "ЧТО УЖЕ РАБОТАЛО (используй):\n"
                                        "• [hook] Короткий хук до 3 сек → 40k просмотров")

    system = await md._full_system()

    assert "ОПЫТ ЭТОГО АККАУНТА" in system
    assert "Короткий хук до 3 сек" in system


@pytest.mark.asyncio
async def test_empty_memory_does_not_litter_the_prompt(client, monkeypatch):
    """Пустой раздел в промпте — потраченные токены на каждой задаче."""
    monkeypatch.setattr(skills_store, "context_for", lambda *a, **k: "")

    system = await md._full_system()

    assert "ОПЫТ ЭТОГО АККАУНТА" not in system


@pytest.mark.asyncio
async def test_broken_memory_does_not_break_the_director(client, monkeypatch):
    """Сбой памяти не должен отменять задачу — дирижёр обязан работать и без неё."""
    def boom(*a, **k):
        raise RuntimeError("база недоступна")

    monkeypatch.setattr(skills_store, "context_for", boom)

    system = await md._full_system()

    assert system, "системный промпт должен остаться рабочим"


@pytest.mark.asyncio
async def test_failures_are_carried_too_not_only_wins(client):
    """Модели важно видеть, чего НЕ делать: иначе ошибка повторяется."""
    from core.skills_store import context_for, add_skill

    add_skill(kind="mistake", title="Длинное вступление", body="ER упал вдвое")
    memory = context_for()

    assert "НЕ СРАБОТАЛО" in memory and "Длинное вступление" in memory
