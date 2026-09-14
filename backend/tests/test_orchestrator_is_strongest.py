"""Дирижёр всегда самый мощный из доступных.

Дирижёр планирует и раздаёт задачи — это самая сложная работа в системе.
Дешёвая модель здесь портит весь конвейер, а не один ответ. Было: Claude
Sonnet 4.6 как основной и Gemini 2.0 Flash как запасной — то есть на главной
роли стояла быстрая дешёвая модель.

Отдельно закреплено совпадение имени и факта: статус объявлял gemini-2.5-flash,
а запускался gemini-2.0-flash — панель показывала не ту модель.
"""
import importlib

import pytest

from core import marketing_director as md


def _only(monkeypatch, *keys):
    for env in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        if env in keys:
            monkeypatch.setenv(env, "k")
        else:
            monkeypatch.delenv(env, raising=False)
    monkeypatch.delenv("NEXUS_DIRECTOR_GEMINI_MODEL", raising=False)


def test_order_is_strongest_first():
    assert md.ORCHESTRATORS[0]["provider"] == "anthropic"


def test_director_model_is_opus_not_sonnet():
    """Sonnet дешевле, но дирижёр — не то место, где экономят."""
    assert md.DIRECTOR_MODEL == "claude-opus-5"
    assert "sonnet" not in md.DIRECTOR_MODEL


def test_gemini_fallback_is_not_the_weakest(monkeypatch):
    """Запасной дирижёр не должен быть 2.0-flash — это слабее доступного."""
    assert md.GEMINI_DIRECTOR_MODEL != "gemini-2.0-flash"


def test_strongest_is_picked_when_both_keys_exist(monkeypatch):
    _only(monkeypatch, "ANTHROPIC_API_KEY", "GEMINI_API_KEY")
    assert md.current_orchestrator()["model"] == "claude-opus-5"


def test_fallback_used_when_strongest_has_no_key(monkeypatch):
    _only(monkeypatch, "GEMINI_API_KEY")
    who = md.current_orchestrator()
    assert who["provider"] == "google" and who["ok"]


def test_announced_model_is_the_one_that_runs(monkeypatch):
    """Главный дефект: панель называла модель, которая не запускается."""
    _only(monkeypatch, "GEMINI_API_KEY")
    importlib.reload(md)
    assert md.current_orchestrator()["model"] == md.GEMINI_DIRECTOR_MODEL


def test_override_is_named_honestly(monkeypatch):
    _only(monkeypatch, "GEMINI_API_KEY")
    monkeypatch.setenv("NEXUS_DIRECTOR_GEMINI_MODEL", "gemini-эксперимент")
    who = md.current_orchestrator()
    assert who["model"] == "gemini-эксперимент"
    assert "эксперимент" in who["human"]


def test_no_keys_is_honest(monkeypatch):
    _only(monkeypatch)
    who = md.current_orchestrator()
    assert not who["ok"] and "нет ключа" in who["human"]


def test_human_name_is_readable(monkeypatch):
    _only(monkeypatch, "ANTHROPIC_API_KEY")
    assert md.current_orchestrator()["human"] == "Claude Opus 5"
