"""
Реестр моделей: что провайдер РЕАЛЬНО предлагает и что из этого проверено.

Зачем отдельный слой. До сих пор списки моделей жили в коде — и трижды
разошлись с действительностью: платформа отвечала «Unavailable model», а мы
меняли имена наугад. Список в коде не может знать, что доступно аккаунту
сегодня; это знает только сам провайдер.

Три состояния модели, и они не синонимы:

  ``discovered`` — провайдер назвал её в каталоге. Это ещё не «работает»;
  ``ready``      — по ней получен настоящий результат;
  ``failed``     — последняя настоящая попытка не удалась, причина сохранена.

Модель, о которой известно только из документации, в реестр не попадает вовсе:
догадка — не обнаружение.

Хранение — KV в таблице `Connection`, как и остальное состояние системы: схема
БД не меняется, миграции не нужны.
"""
import json
from datetime import datetime

KEY_PREFIX = "models:"
DISCOVERED, READY, FAILED = "discovered", "ready", "failed"

# Каталог живёт недолго: у провайдера модели появляются и исчезают.
FRESH_HOURS = 24


def _key(provider: str) -> str:
    return f"{KEY_PREFIX}{provider}"


async def _load(provider: str) -> dict:
    try:
        from sqlalchemy import select
        from database.db import AsyncSessionLocal
        from database.models import Connection
        async with AsyncSessionLocal() as db:
            r = await db.execute(
                select(Connection).where(Connection.key_name == _key(provider)))
            row = r.scalar_one_or_none()
        if not row or not row.key_value:
            return {}
        data = json.loads(row.key_value)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"[NEXUS] реестр моделей не прочитан: {type(e).__name__}: "
              f"{str(e)[:120]}", flush=True)
        return {}


async def _save(provider: str, data: dict) -> None:
    try:
        from sqlalchemy import select
        from database.db import AsyncSessionLocal
        from database.models import Connection
        payload = json.dumps(data, ensure_ascii=False)
        async with AsyncSessionLocal() as db:
            r = await db.execute(
                select(Connection).where(Connection.key_name == _key(provider)))
            row = r.scalar_one_or_none()
            if row:
                row.key_value = payload
            else:
                db.add(Connection(key_name=_key(provider), key_value=payload))
            await db.commit()
    except Exception as e:
        print(f"[NEXUS] реестр моделей не сохранён: {type(e).__name__}: "
              f"{str(e)[:120]}", flush=True)


async def remember_catalog(provider: str, models: list[dict], source: str) -> int:
    """Записать каталог, названный самим провайдером.

    `models`: [{'id', 'kind', 'label'?}]. Источник (`source`) сохраняется: по
    нему видно, откуда знание — из MCP, из ответа API или из разметки сайта.
    Прежние результаты испытаний не стираются: модель, уже доказавшая работу,
    не должна из-за переобнаружения снова стать «непроверенной».
    """
    data = await _load(provider)
    known = data.get("models") or {}
    fresh = {}
    for m in models or []:
        mid = str(m.get("id") or "").strip()
        if not mid:
            continue
        was = known.get(mid) or {}
        fresh[mid] = {
            "id": mid,
            "kind": m.get("kind") or was.get("kind") or "image",
            "label": m.get("label") or was.get("label") or mid,
            "status": was.get("status") or DISCOVERED,
            "last_test": was.get("last_test", ""),
            "last_error": was.get("last_error", ""),
        }
    data.update(models=fresh, source=source,
                discovered_at=datetime.utcnow().isoformat())
    await _save(provider, data)
    return len(fresh)


async def mark_result(provider: str, model: str, ok: bool, error: str = "") -> None:
    """Исход НАСТОЯЩЕЙ генерации этой моделью."""
    model = (model or "").strip()
    if not model:
        return
    data = await _load(provider)
    models = data.get("models") or {}
    row = models.get(model) or {"id": model, "kind": "image", "label": model}
    row.update(status=READY if ok else FAILED,
               last_test=datetime.utcnow().isoformat(),
               last_error="" if ok else (error or "")[:300])
    models[model] = row
    data["models"] = models
    await _save(provider, data)


async def catalog(provider: str, kind: str = "") -> list[dict]:
    """Известные модели провайдера, при необходимости одного вида."""
    data = await _load(provider)
    rows = list((data.get("models") or {}).values())
    if kind:
        rows = [r for r in rows if r.get("kind") == kind]
    return sorted(rows, key=lambda r: (r.get("status") != READY, r.get("id", "")))


async def usable(provider: str, kind: str = "") -> list[str]:
    """Модели, которыми стоит пробовать: сперва доказавшие работу.

    Провалившиеся не исключаются навсегда — отказ мог быть временным, — но
    уходят в конец очереди.
    """
    rows = await catalog(provider, kind)
    order = {READY: 0, DISCOVERED: 1, FAILED: 2}
    rows.sort(key=lambda r: order.get(r.get("status"), 3))
    return [r["id"] for r in rows]


async def freshness(provider: str) -> dict:
    """Когда каталог обновлялся и откуда он взят."""
    data = await _load(provider)
    when = data.get("discovered_at", "")
    hours = 1e9
    try:
        hours = (datetime.utcnow()
                 - datetime.fromisoformat(when)).total_seconds() / 3600
    except Exception:
        pass
    return {"when": when, "source": data.get("source", ""),
            "stale": hours > FRESH_HOURS, "count": len(data.get("models") or {})}


ICONS = {READY: "✅", DISCOVERED: "❓", FAILED: "❌"}
WORDS = {READY: "проверена", DISCOVERED: "не проверена", FAILED: "не сработала"}


def as_text(rows: list[dict], title: str) -> str:
    if not rows:
        return (f"<b>{title}</b>\nКаталог пуст — провайдер ещё не спрошен. "
                "Обнаружение идёт при первой генерации.")
    lines = [f"<b>{title}</b>"]
    for r in rows:
        line = f"{ICONS.get(r['status'], '❓')} {r['label']} — {WORDS.get(r['status'], '')}"
        if r.get("last_error"):
            line += f"\n   {r['last_error'][:120]}"
        lines.append(line)
    return "\n".join(lines)
