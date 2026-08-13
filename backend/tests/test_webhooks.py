"""Вебхуки Instagram: публичный эндпоинт, поэтому проверки — не формальность.

Адрес вызывает Meta из своей инфраструктуры, без нашей авторизации. Значит,
запрос может прислать кто угодно, и единственная защита — совпадение токена
на подписке и HMAC-подпись на каждом событии.
"""
import hmac
import json
import hashlib

import pytest

from core import webhooks as wh

SECRET = "app-secret-999"
TOKEN = "my-verify-token"

COMMENT_PAYLOAD = {
    "object": "instagram",
    "entry": [{
        "id": "17841400000000000",
        "changes": [{
            "field": "comments",
            "value": {"id": "cmt_1", "text": "сколько стоит доставка?",
                      "from": {"username": "client_1"}, "media": {"id": "media_9"}},
        }],
    }],
}


def _sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ─────────────────────────── подтверждение подписки ───────────────────────────

def test_subscription_ok_returns_challenge(monkeypatch):
    monkeypatch.setenv(wh.VERIFY_TOKEN_ENV, TOKEN)
    ok, payload = wh.check_subscription("subscribe", TOKEN, "12345")
    assert ok is True and payload == "12345"


def test_wrong_token_is_rejected(monkeypatch):
    """Иначе подписаться на наш эндпоинт смог бы кто угодно."""
    monkeypatch.setenv(wh.VERIFY_TOKEN_ENV, TOKEN)
    ok, _ = wh.check_subscription("subscribe", "подобранный-токен", "12345")
    assert ok is False


def test_missing_token_setting_explains_what_to_do(monkeypatch):
    monkeypatch.delenv(wh.VERIFY_TOKEN_ENV, raising=False)
    ok, msg = wh.check_subscription("subscribe", TOKEN, "12345")
    assert ok is False and "Ключи API" in msg


# ───────────────────────────── подпись событий ─────────────────────────────

def test_valid_signature_passes(monkeypatch):
    monkeypatch.setenv("FACEBOOK_APP_SECRET", SECRET)
    body = json.dumps(COMMENT_PAYLOAD).encode()
    assert wh.check_signature(body, _sign(body)) is True


def test_tampered_body_is_rejected(monkeypatch):
    """Подпись считается от тела: изменили тело — подпись обязана не совпасть."""
    monkeypatch.setenv("FACEBOOK_APP_SECRET", SECRET)
    body = json.dumps(COMMENT_PAYLOAD).encode()
    signature = _sign(body)
    assert wh.check_signature(body + b" ", signature) is False


def test_signature_from_other_secret_is_rejected(monkeypatch):
    monkeypatch.setenv("FACEBOOK_APP_SECRET", SECRET)
    body = b"{}"
    assert wh.check_signature(body, _sign(body, "чужой-секрет")) is False


@pytest.mark.parametrize("header", ["", "sha1=abc", "sha256=", "мусор", "sha256"])
def test_bad_headers_are_rejected(monkeypatch, header):
    monkeypatch.setenv("FACEBOOK_APP_SECRET", SECRET)
    assert wh.check_signature(b"{}", header) is False


def test_no_secret_means_no_trust(monkeypatch):
    """Без секрета проверить подлинность нечем — значит, не доверяем."""
    monkeypatch.delenv("FACEBOOK_APP_SECRET", raising=False)
    monkeypatch.delenv("INSTAGRAM_APP_SECRET", raising=False)
    assert wh.check_signature(b"{}", "sha256=" + "0" * 64) is False


# Приложение может быть чисто Instagram — Facebook в нём нет вовсе, и секрет
# называется Instagram app secret. Пока источником был только FACEBOOK_APP_SECRET,
# вебхуки в таком приложении молча не проходили подпись.

def test_instagram_app_secret_is_accepted(monkeypatch):
    monkeypatch.delenv("FACEBOOK_APP_SECRET", raising=False)
    monkeypatch.setenv("INSTAGRAM_APP_SECRET", SECRET)
    body = json.dumps(COMMENT_PAYLOAD).encode()
    assert wh.check_signature(body, _sign(body)) is True


def test_wrong_instagram_secret_still_rejected(monkeypatch):
    monkeypatch.delenv("FACEBOOK_APP_SECRET", raising=False)
    monkeypatch.setenv("INSTAGRAM_APP_SECRET", SECRET)
    assert wh.check_signature(b"{}", _sign(b"{}", "чужой-секрет")) is False


# ───────────────────────────── разбор событий ─────────────────────────────

def test_comment_event_is_parsed():
    events = wh.parse_events(COMMENT_PAYLOAD)
    assert len(events) == 1
    e = events[0]
    assert e["kind"] == "comment" and e["id"] == "cmt_1"
    assert e["text"] == "сколько стоит доставка?" and e["author"] == "client_1"


def test_unknown_field_is_kept_not_dropped():
    """Незнакомое событие лучше сохранить: иначе не понять, что присылает Meta."""
    events = wh.parse_events({"entry": [{"id": "1", "changes": [
        {"field": "story_insights", "value": {"x": 1}}]}]})
    assert events[0]["kind"] == "story_insights"


def test_empty_payload_is_not_an_error():
    assert wh.parse_events({}) == []


# ───────────────────────────── эндпоинты ─────────────────────────────

@pytest.mark.asyncio
async def test_verify_endpoint_returns_plain_challenge(client, monkeypatch):
    """Meta ждёт ровно challenge текстом — JSON-обёртка ломает подтверждение."""
    monkeypatch.setenv(wh.VERIFY_TOKEN_ENV, TOKEN)
    r = await client.get("/api/social/webhook/instagram", params={
        "hub.mode": "subscribe", "hub.verify_token": TOKEN, "hub.challenge": "778899"})
    assert r.status_code == 200
    assert r.text == "778899"


@pytest.mark.asyncio
async def test_verify_endpoint_rejects_wrong_token(client, monkeypatch):
    monkeypatch.setenv(wh.VERIFY_TOKEN_ENV, TOKEN)
    r = await client.get("/api/social/webhook/instagram", params={
        "hub.mode": "subscribe", "hub.verify_token": "не тот", "hub.challenge": "1"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_event_without_signature_is_rejected(client, monkeypatch):
    monkeypatch.setenv("FACEBOOK_APP_SECRET", SECRET)
    r = await client.post("/api/social/webhook/instagram", json=COMMENT_PAYLOAD)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_signed_event_is_accepted_and_stored(client, monkeypatch):
    monkeypatch.setenv("FACEBOOK_APP_SECRET", SECRET)

    async def fake_process(platform="instagram", limit=10, auto_send=False):
        return {"ok": True, "processed": limit}

    import core.engagement as eng
    monkeypatch.setattr(eng, "process_comments", fake_process)

    body = json.dumps(COMMENT_PAYLOAD).encode()
    r = await client.post("/api/social/webhook/instagram", content=body,
                          headers={"X-Hub-Signature-256": _sign(body),
                                   "Content-Type": "application/json"})
    assert r.status_code == 200
    assert r.json()["comments"] == 1

    events = await wh.recent_events(5)
    assert any(e["id"] == "cmt_1" for e in events)


@pytest.mark.asyncio
async def test_internal_failure_still_answers_200(client, monkeypatch):
    """Meta повторяет доставку при любом не-200 и отключает подписку после серии
    неудач — внутренний сбой не должен стоить нам подписки."""
    monkeypatch.setenv("FACEBOOK_APP_SECRET", SECRET)

    async def boom(*a, **kw):
        raise RuntimeError("внутренний сбой")

    import core.task_manager as tm
    monkeypatch.setattr(tm, "create", boom)

    body = json.dumps(COMMENT_PAYLOAD).encode()
    r = await client.post("/api/social/webhook/instagram", content=body,
                          headers={"X-Hub-Signature-256": _sign(body),
                                   "Content-Type": "application/json"})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_events_list_requires_auth(client):
    r = await client.get("/api/social/webhook/events")
    assert r.status_code in (401, 403)


def test_non_ascii_token_is_rejected_not_crashed(monkeypatch):
    """compare_digest на строках с кириллицей бросает TypeError — подобранный
    токен вернул бы 500 вместо честного отказа."""
    monkeypatch.setenv(wh.VERIFY_TOKEN_ENV, TOKEN)
    ok, _ = wh.check_subscription("subscribe", "токен-по-русски", "1")
    assert ok is False


def test_non_ascii_signature_is_rejected_not_crashed(monkeypatch):
    monkeypatch.setenv("FACEBOOK_APP_SECRET", SECRET)
    assert wh.check_signature(b"{}", "sha256=подпись") is False


# ── готовые значения для панели Meta ──────────────────────────────────────────
# Оба значения раньше составлялись руками: адрес угадывался, токен придумывался
# и вписывался в двух местах. Расхождение в один символ Meta объясняет безликим
# «The callback URL or verify token couldn't be validated».

@pytest.mark.asyncio
async def test_webhook_config_gives_ready_values(auth_client, monkeypatch):
    monkeypatch.setenv("NEXUS_PUBLIC_URL", "https://nexus-ai.onrender.com/")
    monkeypatch.delenv(wh.VERIFY_TOKEN_ENV, raising=False)

    d = (await auth_client.get("/api/social/webhook/config")).json()

    assert d["ok"] is True
    assert d["callback_url"] == "https://nexus-ai.onrender.com/api/social/webhook/instagram"
    assert d["verify_token"] and d["verify_token_generated"] is True


@pytest.mark.asyncio
async def test_generated_token_actually_confirms_subscription(auth_client, monkeypatch):
    """Сгенерированное значение обязано проходить собственную же проверку."""
    monkeypatch.setenv("NEXUS_PUBLIC_URL", "https://nexus-ai.onrender.com")
    monkeypatch.delenv(wh.VERIFY_TOKEN_ENV, raising=False)

    token = (await auth_client.get("/api/social/webhook/config")).json()["verify_token"]
    ok, payload = wh.check_subscription("subscribe", token, "12345")

    assert ok is True and payload == "12345"


@pytest.mark.asyncio
async def test_existing_token_is_not_regenerated(auth_client, monkeypatch):
    """Перевыпуск сломал бы уже настроенную в панели Meta подписку."""
    monkeypatch.setenv("NEXUS_PUBLIC_URL", "https://nexus-ai.onrender.com")
    monkeypatch.setenv(wh.VERIFY_TOKEN_ENV, "уже-настроенный")

    d = (await auth_client.get("/api/social/webhook/config")).json()

    assert d["verify_token"] == "уже-настроенный"
    assert d["verify_token_generated"] is False


@pytest.mark.asyncio
async def test_no_public_url_says_what_to_do(auth_client, monkeypatch):
    monkeypatch.delenv("NEXUS_PUBLIC_URL", raising=False)
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)

    d = (await auth_client.get("/api/social/webhook/config")).json()

    assert d["ok"] is False and "публичный адрес" in d["error"]
