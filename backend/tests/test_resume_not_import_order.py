"""Восстановление задачи не должно зависеть от порядка импортов.

Живой случай: «image · TASK-2026-000077 — Задача потеряна при перезапуске
сервера». Рецепт у задачи был исправный (handler: factory), но обработчик
регистрируется при импорте `core.content_factory`, а восстановление идёт на
старте, до того как этот модуль кому-то понадобился. Реестр оказывался пустым,
и КАЖДАЯ задача с рецептом объявлялась потерянной.
"""
import pytest

from core import task_manager as tm


@pytest.fixture
def empty_registry(monkeypatch):
    """Состояние, в котором система оказывается при старте."""
    monkeypatch.setattr(tm, "_RESUMERS", {})
    return tm._RESUMERS


def test_registry_is_empty_at_startup(empty_registry):
    """Исходная точка дефекта: на старте регистрировать ещё некому."""
    assert not empty_registry


def test_handler_is_found_despite_empty_registry(empty_registry):
    assert tm.resumer_for("factory") is not None


def test_lazy_import_actually_registers(empty_registry):
    tm.resumer_for("factory")
    assert "factory" in tm._RESUMERS


def test_already_registered_handler_is_returned_as_is(empty_registry):
    marker = object()
    tm.register_resumer("свой", marker)
    assert tm.resumer_for("свой") is marker


def test_unknown_handler_is_none_not_error(empty_registry):
    assert tm.resumer_for("такого-нет") is None


def test_empty_name_is_none(empty_registry):
    assert tm.resumer_for("") is None
    assert tm.resumer_for(None) is None


def test_missing_function_does_not_raise(empty_registry, monkeypatch):
    """Функции нет в модуле — это не повод ронять запуск сервера."""
    monkeypatch.setitem(tm.RESUMER_MODULES, "без_функции",
                        ("core.content_factory", "такой_функции_нет"))
    assert tm.resumer_for("без_функции") is None


def test_broken_module_does_not_raise(empty_registry, monkeypatch):
    """Сломанный модуль не должен ронять запуск сервера."""
    monkeypatch.setitem(tm.RESUMER_MODULES, "битый",
                        ("core.такого_модуля_нет", "run"))
    assert tm.resumer_for("битый") is None
