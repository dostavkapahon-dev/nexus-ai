"""Вход не должен истекать посреди работы.

Раньше метка считалась по часу и принималась только текущая и предыдущая:
через час-два дашборд выкидывал на экран пароля. Снаружи это неотличимо от
«панель не грузится».
"""
import time

from core import auth


def test_token_is_valid_right_away(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "secret-1")
    assert auth.verify_token(auth.make_token())


def test_token_survives_a_few_days(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "secret-1")
    token = auth.make_token()
    real = time.time
    try:
        time.time = lambda: real() + 3 * 86400
        assert auth.verify_token(token), "вход не должен слетать через сутки"
    finally:
        time.time = real


def test_token_expires_eventually(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "secret-1")
    token = auth.make_token()
    real = time.time
    try:
        time.time = lambda: real() + 30 * 86400
        assert not auth.verify_token(token), "вечный вход — это не сессия"
    finally:
        time.time = real


def test_changing_password_kills_old_sessions(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "secret-1")
    token = auth.make_token()
    monkeypatch.setenv("ADMIN_PASSWORD", "secret-2")
    assert not auth.verify_token(token)


def test_garbage_is_rejected():
    assert not auth.verify_token("")
    assert not auth.verify_token("nexus:1.deadbeef")
