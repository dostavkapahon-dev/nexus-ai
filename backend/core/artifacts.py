"""
Реестр артефактов: созданное не должно зависеть от доставки.

Порядок, который был: сгенерировали → отправили в Telegram. Если отправка не
удалась — файла нет нигде, и повторить нечего: ссылка провайдера живёт недолго,
а кредиты уже списаны. Правильный порядок иной:

    ГЕНЕРАЦИЯ → АРТЕФАКТ → ХРАНИЛИЩЕ → TELEGRAM

Артефакт создаётся первым и переживает любую неудачу дальше по цепочке. У него
есть свой идентификатор, по которому результат можно найти и переотправить.

Хранение — KV в таблице `Connection`, как и остальное состояние: схема БД не
меняется, миграции не нужны.
"""
import json
from datetime import datetime, timedelta

KEY_PREFIX = "artifact:"
INDEX_KEY = "artifact_index"
KEEP = 200          # сколько последних артефактов помнить


def _now() -> str:
    return datetime.utcnow().isoformat()


async def _kv_get(key: str) -> str:
    from sqlalchemy import select
    from database.db import AsyncSessionLocal
    from database.models import Connection
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Connection).where(Connection.key_name == key))
        row = r.scalar_one_or_none()
    return (row.key_value or "") if row else ""


async def _kv_set(key: str, value: str) -> None:
    from sqlalchemy import select
    from database.db import AsyncSessionLocal
    from database.models import Connection
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Connection).where(Connection.key_name == key))
        row = r.scalar_one_or_none()
        if row:
            row.key_value = value
        else:
            db.add(Connection(key_name=key, key_value=value))
        await db.commit()


def new_id() -> str:
    """Идентификатор артефакта: по времени, поэтому сортируется сам собой.

    К времени добавлен случайный хвост: два результата одной задачи создаются в
    одну и ту же миллисекунду, и без него второй затирал первый — ровно та
    потеря результата, от которой этот модуль и защищает.
    """
    import secrets
    return ("ART-" + datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")[:-3]
            + "-" + secrets.token_hex(2))


async def save(url: str, kind: str, task_id: str = "", provider: str = "",
               model: str = "", prompt: str = "", external_job: str = "",
               note: str = "") -> str:
    """Записать созданное СРАЗУ, до всякой доставки. Возвращает artifact_id.

    Ошибка записи не должна ронять генерацию: артефакт — учёт, а не сама
    работа. Но она честно попадает в журнал, чтобы пропажа не была тихой.
    """
    art_id = new_id()
    row = {
        "id": art_id, "url": url, "kind": kind, "task_id": task_id,
        "provider": provider, "model": model, "prompt": (prompt or "")[:500],
        "external_job": external_job, "note": note,
        "created_at": _now(), "telegram": "", "storage": "", "publish": "",
    }
    try:
        await _kv_set(KEY_PREFIX + art_id, json.dumps(row, ensure_ascii=False))
        raw = await _kv_get(INDEX_KEY)
        index = json.loads(raw) if raw else []
        index.append(art_id)
        await _kv_set(INDEX_KEY, json.dumps(index[-KEEP:], ensure_ascii=False))
    except Exception as e:
        print(f"[NEXUS] артефакт не сохранён: {type(e).__name__}: "
              f"{str(e)[:150]}", flush=True)
    return art_id


async def get(art_id: str) -> dict:
    try:
        raw = await _kv_get(KEY_PREFIX + art_id)
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


async def mark(art_id: str, **fields) -> None:
    """Отметить судьбу артефакта: доставлен, сохранён, опубликован."""
    if not art_id:
        return
    try:
        row = await get(art_id)
        if not row:
            return
        row.update({k: str(v)[:300] for k, v in fields.items()})
        row["updated_at"] = _now()
        await _kv_set(KEY_PREFIX + art_id, json.dumps(row, ensure_ascii=False))
    except Exception as e:
        print(f"[NEXUS] артефакт не обновлён: {type(e).__name__}: "
              f"{str(e)[:150]}", flush=True)


async def recent(limit: int = 10, hours: int = 0) -> list[dict]:
    """Последние артефакты, новые первыми."""
    try:
        raw = await _kv_get(INDEX_KEY)
        ids = json.loads(raw) if raw else []
    except Exception:
        return []
    out = []
    since = datetime.utcnow() - timedelta(hours=hours) if hours else None
    for art_id in reversed(ids[-(limit * 3 or 30):]):
        row = await get(art_id)
        if not row:
            continue
        if since:
            try:
                if datetime.fromisoformat(row.get("created_at", "")) < since:
                    continue
            except Exception:
                pass
        out.append(row)
        if len(out) >= limit:
            break
    return out


async def undelivered(hours: int = 24) -> list[dict]:
    """Созданное, но не дошедшее до человека — то, что иначе пропало бы молча."""
    return [r for r in await recent(limit=50, hours=hours) if not r.get("telegram")]


async def redeliver(art_id: str, chat_id: str) -> dict:
    """Отправить УЖЕ СОЗДАННЫЙ результат заново, ничего не генерируя.

    Требование §29. Сбой доставки не должен стоить новой генерации: файл есть,
    он сохранён, и повторять надо ровно доставку. Иначе неудачная отправка
    видео превращается в повторное списание кредитов и второй файл в ленте.
    """
    row = await get(art_id)
    if not row:
        return {"ok": False, "error": f"артефакт {art_id} не найден"}
    url = row.get("url") or ""
    if not url:
        return {"ok": False, "error": "у артефакта нет ссылки на файл"}

    from publishers.telegram_pub import send_photo, send_video
    caption = (f"{row.get('provider', '')} {row.get('model', '')}\n"
               f"{row.get('prompt', '')[:200]}").strip()
    try:
        if row.get("kind") == "video":
            await send_video(chat_id, url, caption)
        else:
            await send_photo(chat_id, url, caption)
    except Exception as e:
        await mark(art_id, telegram=f"не доставлено: {str(e)[:120]}")
        return {"ok": False, "error": str(e)[:200]}
    await mark(art_id, telegram="доставлено повторно")
    return {"ok": True, "kind": row.get("kind", ""), "url": url}


def as_text(rows: list[dict]) -> str:
    if not rows:
        return "📦 <b>Результаты</b>\nПока ничего не создано."
    lines = ["📦 <b>Последние результаты</b>"]
    for r in rows:
        mark_tg = "✅" if r.get("telegram") else "⚠️ не доставлен"
        when = (r.get("created_at") or "")[:16].replace("T", " ")
        lines.append(f"\n<b>{r['id']}</b> · {r.get('kind', '?')} · {when} UTC"
                     f"\n{r.get('provider', '')} {r.get('model', '')} · {mark_tg}"
                     f"\n{r.get('url', '')[:120]}")
    return "\n".join(lines)
