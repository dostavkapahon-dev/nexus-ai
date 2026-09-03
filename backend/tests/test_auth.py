import time

import pytest

from core.auth import make_token, verify_token, check_rate, RATE_LIMIT
from fastapi import HTTPException

from conftest import TEST_PASSWORD


async def test_health(client):
    """Проверяем по существу, а не точным равенством: эндпоинт задуман растущим
    (в него добавлена версия сборки), и сравнение целиком ломалось бы на каждом
    полезном дополнении."""
    r = await client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["service"] == "nexus-ai"


async def test_login_wrong_password(client):
    r = await client.post("/api/auth/login", json={"password": "nope"})
    assert r.status_code == 401


async def test_login_ok_and_token_shape(client):
    r = await client.post("/api/auth/login", json={"password": TEST_PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["method"] == "password"
    assert verify_token(body["token"])


async def test_login_tolerates_whitespace(client):
    r = await client.post("/api/auth/login", json={"password": f"  {TEST_PASSWORD}\n"})
    assert r.status_code == 200


async def test_protected_route_requires_token(client):
    r = await client.get("/api/niches")
    assert r.status_code == 401


async def test_protected_route_rejects_garbage_token(client):
    r = await client.get("/api/niches", headers={"Authorization": "Bearer nexus:1.deadbeef"})
    assert r.status_code == 401


async def test_protected_route_with_token(auth_client):
    r = await auth_client.get("/api/niches")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


async def test_google_client_id_endpoint(client):
    r = await client.get("/api/auth/google-client-id")
    assert r.status_code == 200
    assert set(r.json()) == {"client_id", "enabled"}


async def test_security_headers(client):
    r = await client.get("/api/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"


def test_token_previous_hour_still_valid(monkeypatch):
    """Токен привязан к часу и должен приниматься ещё час после выпуска."""
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() - 3600)
    old = make_token()
    monkeypatch.setattr(time, "time", real)
    assert verify_token(old)


def test_token_two_hours_old_rejected(monkeypatch):
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() - 3 * 3600)
    old = make_token()
    monkeypatch.setattr(time, "time", real)
    assert not verify_token(old)


def test_token_signed_with_other_password(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "other-password")
    foreign = make_token()
    monkeypatch.setenv("ADMIN_PASSWORD", TEST_PASSWORD)
    assert not verify_token(foreign)


def test_verify_token_malformed():
    assert not verify_token("")
    assert not verify_token("no-dot")


def test_rate_limit_trips():
    ip = "1.2.3.4"
    for _ in range(RATE_LIMIT):
        check_rate(ip)
    with pytest.raises(HTTPException) as e:
        check_rate(ip)
    assert e.value.status_code == 429
