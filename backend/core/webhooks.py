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


async def _remember(events: list[dict]) -> list[dict]:
    """Складывает события в KV и отсеивает повторы.

    Meta штатно повторяет доставку одного и того же события: без проверки по id
    каждый повтор заново запускал разбор комментариев и плодил задачи.
    Возвращает только новые события.
    """
    from core import kv
    try:
        # Проверка «видели ли уже» и запись — одной операцией под замком.
        # Meta шлёт повторы пачками, и раздельные чтение и запись означали, что
        # два параллельных вызова признавали одно событие новым: разбор
        # комментариев запускался дважды на одно и то же.
        fresh: list[dict] = []
        async with kv.update(EVENTS_KEY, []) as stored:
            known = {e.get("id") for e in stored if e.get("id")}
            fresh = [e for e in events if not (e.get("id") and e["id"] in known)]
            if fresh:
                now = datetime.utcnow().isoformat()
                stored += [{**e, "received_at": now} for e in fresh]
                del stored[:-MAX_EVENTS]
        return fresh
    except Exception as e:
        # Потеря событий не должна быть незаметной: раньше здесь стоял голый pass.
        print(f"[NEXUS] вебхук: не удалось сохранить события — {str(e)[:150]}", flush=True)
        return events


async def recent_events(limit: int = 20) -> list[dict]:
    from core import kv
    return list(reversed(await kv.get(EVENTS_KEY, [])))[:limit]


async def handle_events(payload: dict) -> dict:
    """Обрабатывает пачку событий. Никогда не бросает наружу.

    Meta считает ошибкой любой ответ, кроме 200, и начинает повторять доставку,
    а после серии неудач отключает подписку. Поэтому внутренний сбой не должен
    превращаться в отказ: логируем и отвечаем 200.
    """
    events = parse_events(payload)
    if not events:
        return {"ok": True, "events": 0}

    fresh = await _remember(events)
    if not fresh:
        # Повторная доставка того же события — работа уже сделана.
        return {"ok": True, "events": len(events), "duplicates": len(events)}

    comments = [e for e in fresh if e["kind"] == "comment" and e.get("text")]
    mentions = [e for e in fresh if e["kind"] == "mention"]

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
            return {"ok": True, "events": len(fresh), "error": str(e)[:200]}

    if mentions:
        # Упоминания раньше просто складывались в хранилище и не приводили ни к
        # чему: о них никто не узнавал.
        try:
            from core.notify import notify_owner
            await notify_owner("📣 Вас упомянули в Instagram: "
                               + ", ".join(m.get("media_id", "") for m in mentions[:5]))
        except Exception:
            pass

    return {"ok": True, "events": len(fresh), "comments": len(comments),
            "mentions": len(mentions)}
