"""
Приём вебхуков Meta (Instagram): комментарии и упоминания в реальном времени.

Зачем: сейчас комментарии разбираются джобом раз в 4 часа — человек успевает
уйти, а разговор остыть. Вебхук приносит событие сразу.

Безопасность здесь не формальность: эндпоинт публичный (Meta вызывает его без
нашей авторизации), поэтому подделать запрос может кто угодно. Отсюда два
барьера — verify_token на подписке и HMAC-подпись `X-Hub-Signature-256` на
каждом событии. Без валидной подписи запрос отбрасывается.
"""
import os
import hmac
import json
import hashlib
from datetime import datetime

VERIFY_TOKEN_ENV = "INSTAGRAM_VERIFY_TOKEN"
EVENTS_KEY = "webhook_events"
MAX_EVENTS = 100


def verify_token() -> str:
    return os.getenv(VERIFY_TOKEN_ENV, "").strip()


def check_subscription(mode: str, token: str, challenge: str) -> tuple[bool, str]:
    """Подтверждение подписки: Meta присылает GET с нашим же токеном.

    Отвечаем challenge только при точном совпадении токена — иначе подписаться
    на наш эндпоинт смог бы кто угодно.
    """
    expected = verify_token()
    if not expected:
        return False, ("не задан токен подтверждения: впишите его в Ключи API → "
                       "Instagram Webhooks и сохраните")
    if mode != "subscribe":
        return False, f"неизвестный режим: {mode or '—'}"
    # Сравниваем байты: compare_digest на строках с не-ASCII бросает TypeError,
    # и подобранный токен с кириллицей вернул бы 500 вместо честного отказа.
    if not hmac.compare_digest((token or "").encode("utf-8"), expected.encode("utf-8")):
        return False, "токен подтверждения не совпал"
    return True, challenge or ""


def check_signature(body: bytes, header: str) -> bool:
    """Проверяет `X-Hub-Signature-256`: подпись тела ключом приложения.

    Сравнение — постоянного времени: обычное `==` подсказывает атакующему,
    сколько первых байт он угадал.
    """
    if not header:
        return False
    algo, _, sent = (header or "").partition("=")
    if algo != "sha256" or not sent:
        return False
    # Приложение может быть чисто Instagram — тогда Facebook в нём нет вообще,
    # а секрет называется Instagram app secret. Раньше единственным источником
    # был FACEBOOK_APP_SECRET, и без Facebook вебхуки молча не проходили подпись.
    # Пробуем оба: подпись валидна, если сходится хотя бы с одним.
    for secret in (os.getenv("INSTAGRAM_APP_SECRET", "").strip(),
                   os.getenv("FACEBOOK_APP_SECRET", "").strip()):
        if not secret:
            continue
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if hmac.compare_digest(sent.encode("utf-8", "ignore"), expected.encode()):
            return True
    return False


def parse_events(payload: dict) -> list[dict]:
    """Достаёт из конверта Meta понятные события: комментарии и упоминания."""
    out = []
    for entry in (payload or {}).get("entry", []) or []:
        entry_id = entry.get("id", "")
        for change in entry.get("changes", []) or []:
            field = change.get("field", "")
            value = change.get("value", {}) or {}
            if field == "comments":
                out.append({
                    "kind": "comment", "id": value.get("id", ""),
                    "text": value.get("text", ""),
                    "author": (value.get("from") or {}).get("username", ""),
                    "media_id": (value.get("media") or {}).get("id", ""),
                    "account_id": entry_id,
                })
            elif field == "mentions":
                out.append({"kind": "mention", "id": value.get("comment_id")
                            or value.get("media_id", ""),
                            "media_id": value.get("media_id", ""),
                            "account_id": entry_id})
            else:
                out.append({"kind": field or "unknown", "raw": value, "account_id": entry_id})
    return out


async def _remember(events: list[dict]):
    """Складывает события в KV — чтобы их было видно в дашборде и после рестарта."""
    from core.engagement import _load, _save
    try:
        stored = await _load(EVENTS_KEY, [])
        now = datetime.utcnow().isoformat()
        stored += [{**e, "received_at": now} for e in events]
        await _save(EVENTS_KEY, stored[-MAX_EVENTS:])
    except Exception:
        pass


async def recent_events(limit: int = 20) -> list[dict]:
    from core.engagement import _load
    return list(reversed(await _load(EVENTS_KEY, [])))[:limit]


async def handle_events(payload: dict) -> dict:
    """Обрабатывает пачку событий. Никогда не бросает наружу.

    Meta считает ошибкой любой ответ, кроме 200, и начинает повторять доставку,
    а после серии неудач отключает подписку. Поэтому внутренний сбой не должен
    превращаться в отказ: логируем и отвечаем 200.
    """
    events = parse_events(payload)
    if not events:
        return {"ok": True, "events": 0}
    await _remember(events)

    comments = [e for e in events if e["kind"] == "comment" and e.get("text")]
    if comments:
        try:
            # Разбор идёт под задачей: у события появляется id, статус и журнал,
            # как у любой другой фоновой работы.
            from core.task_manager import create, run
            from core.engagement import process_comments
            task_id = await create("comments", f"Вебхук: {len(comments)} комментариев",
                                   source="webhook")
            await run(task_id, lambda: process_comments("instagram", limit=len(comments)))
        except Exception as e:
            return {"ok": True, "events": len(events), "error": str(e)[:200]}

    return {"ok": True, "events": len(events), "comments": len(comments)}
