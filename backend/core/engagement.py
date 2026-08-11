"""
Работа с комментариями: воронка из обсуждений в заявки.

`FunnelAgent` умел разбирать комментарий и писать ответ, но его никто не вызывал —
мёртвый код из аудита. Здесь он подключён к реальным комментариям площадок.

Принцип безопасности: ответ НИКОГДА не публикуется автоматически. Он уходит на
согласование в Telegram, и только после подтверждения отправляется. Автоответы
от лица бренда — слишком дорогая ошибка, чтобы доверять их модели без надзора.
"""
import json
from datetime import datetime

from sqlalchemy import select

from database.db import AsyncSessionLocal
from database.models import Connection

# Уже обработанные комментарии, чтобы не отвечать дважды.
SEEN_KEY = "engagement_seen"
PENDING_KEY = "engagement_pending"
MAX_SEEN = 500


async def _load(key: str, default):
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Connection).where(Connection.key_name == key))
        c = r.scalar_one_or_none()
    if c and c.key_value:
        try:
            return json.loads(c.key_value)
        except Exception:
            return default
    return default


async def _save(key: str, value):
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Connection).where(Connection.key_name == key))
        c = r.scalar_one_or_none()
        payload = json.dumps(value, ensure_ascii=False)
        if c:
            c.key_value = payload
        else:
            db.add(Connection(key_name=key, key_value=payload))
        await db.commit()


async def fetch_new_comments(platform: str = "instagram", limit: int = 20) -> list[dict]:
    """Комментарии, которые мы ещё не обрабатывали."""
    from connectors import get_connector

    c = get_connector(platform)
    if not c:
        return []
    res = await c.read_comments(limit)
    if not res.get("ok"):
        return []

    seen = set(await _load(SEEN_KEY, []))
    return [item for item in (res.get("comments") or []) if item.get("id") not in seen]


async def process_comments(platform: str = "instagram", limit: int = 10,
                           auto_send: bool = False) -> dict:
    """Разбирает новые комментарии и готовит ответы.

    auto_send оставлен выключенным намеренно: по умолчанию ответ идёт человеку
    на согласование. Включать стоит только для заведомо безопасных сценариев.
    """
    from agents.funnel_agent import FunnelAgent
    from core.contracts import AgentResult

    comments = await fetch_new_comments(platform, limit * 2)
    if not comments:
        return {"ok": True, "processed": 0, "note": "новых комментариев нет"}

    agent = FunnelAgent()
    niche_id, niche_name = await _active_niche()

    prepared, skipped, seen_ids = [], 0, []
    async with AsyncSessionLocal() as db:
        for item in comments[:limit]:
            seen_ids.append(item["id"])
            try:
                raw = await agent.generate_reply(db, niche_id, item.get("text", ""),
                                                 niche_name)
            except Exception as e:
                prepared.append({"comment": item, "error": str(e)[:200]})
                continue

            result = AgentResult.from_raw("funnel_agent", raw or {})
            if not result.get("should_reply"):
                skipped += 1
                continue

            prepared.append({
                "comment_id": item["id"], "platform": platform,
                "author": item.get("author", ""), "text": item.get("text", ""),
                "post_url": item.get("post_url", ""),
                "reply": result.get("reply", ""),
                "intent": result.get("intent", ""),
                "confidence": result.confidence,
                "warnings": result.warnings,
            })

    # Помечаем просмотренными даже те, на которые не отвечаем: иначе будем
    # разбирать их снова на каждом прогоне и жечь токены.
    seen = await _load(SEEN_KEY, [])
    await _save(SEEN_KEY, (seen + seen_ids)[-MAX_SEEN:])

    to_send = [p for p in prepared if p.get("reply")]
    if auto_send:
        sent = [await send_reply(p["platform"], p["comment_id"], p["reply"])
                for p in to_send]
        return {"ok": True, "processed": len(prepared), "skipped": skipped,
                "sent": sum(1 for s in sent if s.get("ok")), "auto": True}

    if to_send:
        await _save(PENDING_KEY, to_send)
        await _ask_approval(to_send)

    return {"ok": True, "processed": len(prepared), "skipped": skipped,
            "pending_approval": len(to_send), "auto": False}


async def _active_niche() -> tuple[str, str]:
    from database.models import Niche
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Niche).where(Niche.status == "active").limit(1))
        n = r.scalar_one_or_none()
    return (n.id, n.name) if n else ("", "")


async def _ask_approval(items: list[dict]):
    """Отправляет подготовленные ответы на согласование в Telegram."""
    import os
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not (os.getenv("TELEGRAM_BOT_TOKEN") and chat_id):
        return
    from core.telegram_bot import send_message

    lines = [f"💬 <b>Комментарии: подготовлено {len(items)} ответов</b>", ""]
    for i, p in enumerate(items[:5], 1):
        lines.append(f"<b>{i}. @{p['author']}</b> ({p['intent'] or 'вопрос'})")
        lines.append(f"   «{p['text'][:120]}»")
        lines.append(f"   → {p['reply'][:200]}")
        if p.get("warnings"):
            lines.append(f"   ⚠️ {'; '.join(p['warnings'])}")
        lines.append("")
    lines.append("Отправить все: /reply_all · Посмотреть: /comments")
    await send_message(chat_id, "\n".join(lines)[:4000])


async def pending() -> list[dict]:
    """Ответы, ждущие согласования."""
    return await _load(PENDING_KEY, [])


async def send_reply(platform: str, comment_id: str, text: str) -> dict:
    """Публикует один ответ на комментарий."""
    from connectors import get_connector
    c = get_connector(platform)
    if not c:
        return {"ok": False, "error": f"неизвестная площадка: {platform}"}
    return await c.reply_comment(comment_id, text)


async def approve_all() -> dict:
    """Отправляет все согласованные ответы и очищает очередь."""
    items = await pending()
    if not items:
        return {"ok": True, "sent": 0, "note": "нет ответов на согласовании"}

    sent, failed = 0, []
    for p in items:
        res = await send_reply(p["platform"], p["comment_id"], p["reply"])
        if res.get("ok"):
            sent += 1
        else:
            failed.append(f"@{p.get('author', '')}: {res.get('error', '')[:80]}")

    await _save(PENDING_KEY, [])
    return {"ok": True, "sent": sent, "failed": failed, "total": len(items)}


async def discard_pending() -> int:
    """Отклонить подготовленные ответы."""
    items = await pending()
    await _save(PENDING_KEY, [])
    return len(items)


async def stats() -> dict:
    """Сколько комментариев обработано и что ждёт согласования."""
    seen = await _load(SEEN_KEY, [])
    return {"processed_total": len(seen), "pending_approval": len(await pending()),
            "checked_at": datetime.utcnow().isoformat()}
