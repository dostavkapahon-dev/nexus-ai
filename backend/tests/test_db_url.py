"""Строка подключения к БД: то, на чём деплой ложится первым.

Supabase выдаёт `postgres://…?sslmode=require`, а пулер добавляет `pgbouncer=true`.
SQLAlchemy передаёт эти параметры прямо в `asyncpg.connect()`, который таких
аргументов не знает и падает с TypeError — то есть сервис не поднимается вообще.
Проверяем не текст строки, а результат: какие именно kwargs уйдут в asyncpg.
"""
import inspect

import asyncpg
import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url

from database.db import normalize_db_url

_ASYNCPG_PARAMS = set(inspect.signature(asyncpg.connect).parameters)


def _connect_kwargs(url: str) -> dict:
    """Что реально уйдёт в asyncpg.connect() для этой строки."""
    _, kw = postgresql.asyncpg.dialect().create_connect_args(make_url(url))
    return kw


@pytest.mark.parametrize("raw", [
    "postgres://u:p@db.supabase.co:5432/postgres?sslmode=require",
    "postgresql://u:p@aws-0.pooler.supabase.com:6543/postgres?pgbouncer=true&sslmode=require",
    "postgresql://u:p@h:5432/postgres?sslmode=verify-full",
    "postgresql://u:p@h:5432/postgres",
])
def test_no_argument_asyncpg_cannot_accept(raw):
    """Главная проверка: ни одного аргумента, которого asyncpg не знает."""
    kw = _connect_kwargs(normalize_db_url(raw))
    unknown = [k for k in kw if k not in _ASYNCPG_PARAMS]
    assert unknown == [], f"asyncpg не примет: {unknown}"


def test_sslmode_becomes_ssl():
    """Шифрование не теряем — переводим в понятный asyncpg параметр."""
    out = normalize_db_url("postgres://u:p@h:5432/db?sslmode=require")
    assert _connect_kwargs(out)["ssl"] == "require"


def test_sslmode_disable_does_not_force_ssl():
    """`disable` — это осознанный отказ от шифрования, не молчаливое включение."""
    out = normalize_db_url("postgresql://u:p@h:5432/db?sslmode=disable")
    assert "ssl" not in _connect_kwargs(out)


@pytest.mark.parametrize("raw,scheme", [
    ("postgres://u:p@h/db", "postgresql+asyncpg"),
    ("postgresql://u:p@h/db", "postgresql+asyncpg"),
])
def test_driver_is_async(raw, scheme):
    assert normalize_db_url(raw).startswith(scheme + "://")


def test_credentials_and_host_survive():
    """Пароль и хост не должны пострадать при чистке параметров."""
    out = normalize_db_url("postgres://user:p%40ss@db.supabase.co:5432/postgres?sslmode=require")
    u = make_url(out)
    assert u.host == "db.supabase.co" and u.port == 5432
    assert u.username == "user" and u.database == "postgres"


def test_sqlite_is_untouched():
    """Локаль и тесты продолжают работать на SQLite без изменений."""
    assert normalize_db_url("sqlite+aiosqlite:///./nexus.db") == "sqlite+aiosqlite:///./nexus.db"


def test_empty_falls_back_to_sqlite_default():
    """Пустой DATABASE_URL не должен давать битую строку."""
    assert normalize_db_url("") == ""
