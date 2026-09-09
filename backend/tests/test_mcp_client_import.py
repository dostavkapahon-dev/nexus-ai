"""
MCP отваливался из-за переименованной функции в пакете `mcp`.

С сервера пришло: `ImportError: cannot import name 'streamablehttp_client' from
'mcp.client.streamable_http'`. Пакет переименовал функцию между версиями
(`streamablehttp_client` → `streamable_http_client`), а requirements допускает
диапазон версий, то есть на сервере может оказаться любая. Код знал только
старое имя — и MCP молча выключался вместе с каталогом моделей и безлимитом.
"""
import sys
import types

import pytest

from core import hixiit


def _fake_module(monkeypatch, **attrs):
    mod = types.ModuleType("mcp.client.streamable_http")
    for k, v in attrs.items():
        setattr(mod, k, v)
    monkeypatch.setitem(sys.modules, "mcp.client.streamable_http", mod)
    return mod


def test_old_name_is_accepted(monkeypatch):
    def old(): ...
    _fake_module(monkeypatch, streamablehttp_client=old)

    assert hixiit._http_client_factory() is old


def test_new_name_is_accepted(monkeypatch):
    """Именно эта версия стоит на сервере."""
    def new(): ...
    _fake_module(monkeypatch, streamable_http_client=new)

    assert hixiit._http_client_factory() is new


def test_old_name_wins_when_both_exist(monkeypatch):
    """Переходная версия: берём то, под что писан остальной код."""
    def old(): ...
    def new(): ...
    _fake_module(monkeypatch, streamablehttp_client=old, streamable_http_client=new)

    assert hixiit._http_client_factory() is old


def test_unknown_naming_says_what_is_actually_there(monkeypatch):
    """Если переименуют снова — сообщение должно называть найденное."""
    def other(): ...
    _fake_module(monkeypatch, some_other_client=other)

    with pytest.raises(ImportError) as e:
        hixiit._http_client_factory()

    assert "some_other_client" in str(e.value), \
        "без списка того, что есть, следующий раз снова придётся гадать"


def test_real_installed_package_is_usable():
    """Тот же пакет, что поедет на сервер: имя должно находиться."""
    assert callable(hixiit._http_client_factory())
