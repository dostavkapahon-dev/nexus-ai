"""
Реестр возможностей: что система УМЕЕТ на самом деле, а не что заявлено в коде.

Зачем отдельный модуль. Наличие функции в репозитории, ключа в окружении и
зелёной галочки в `/diag` — это три разных утверждения, и ни одно из них не
означает «пользователь получит результат». Почти все жалобы вида «функция
заявлена, но не работает» происходили именно здесь: статус читал конфигурацию,
а человек ждал картинку.

Правило этого модуля одно: возможность считается подтверждённой ТОЛЬКО если
есть след настоящего результата — запись о реальной генерации, публикации или
ответе провайдера, сделанная не проверкой, а рабочим путём. Всё остальное —
«не проверено», и так и говорится вслух. Ложное «умею» здесь невозможно: нет
доказательства — нет зелёного.

Состояния:
  ``yes``     — есть доказательство результата (и когда именно);
  ``no``      — последняя настоящая попытка провалилась, причина сохранена;
  ``unknown`` — доступ, возможно, есть, но результата ещё никто не видел.
"""
import json
from datetime import datetime, timedelta

# Доказательство стареет: успех недельной давности ничего не говорит о сегодня.
PROOF_HOURS = 72
KEY_PREFIX = "cap:"

# Человеческие названия. Ключ — то, чем оперирует оркестратор.
CAPABILITIES = {
    "image": "Картинка",
    "video": "Видео",
    "publish_telegram": "Публикация в Telegram",
    "publish_instagram": "Публикация в Instagram",
    "search": "Поиск в интернете",
    "memory": "Память между перезапусками",
}


def _now() -> datetime:
    return datetime.utcnow()


async def record(cap: str, ok: bool, why: str = "", evidence: str = "") -> None:
    """Записать исход НАСТОЯЩЕЙ попытки. Вызывается рабочим путём, не проверкой."""
    if cap not in CAPABILITIES:
        return
    payload = json.dumps({"ok": bool(ok), "why": (why or "")[:300],
                          "evidence": (evidence or "")[:300],
                          "when": _now().isoformat()}, ensure_ascii=False)
    try:
        from sqlalchemy import select
        from database.db import AsyncSessionLocal
        from database.models import Connection
        async with AsyncSessionLocal() as db:
            r = await db.execute(
                select(Connection).where(Connection.key_name == KEY_PREFIX + cap))
            row = r.scalar_one_or_none()
            if row:
                row.key_value = payload
            else:
                db.add(Connection(key_name=KEY_PREFIX + cap, key_value=payload))
            await db.commit()
    except Exception as e:
        # Реестр — наблюдатель: он не имеет права уронить саму работу.
        print(f"[NEXUS] реестр возможностей не сохранил {cap}: "
              f"{type(e).__name__}: {str(e)[:120]}", flush=True)


async def _stored(cap: str) -> dict:
    try:
        from sqlalchemy import select
        from database.db import AsyncSessionLocal
        from database.models import Connection
        async with AsyncSessionLocal() as db:
            r = await db.execute(
                select(Connection).where(Connection.key_name == KEY_PREFIX + cap))
            row = r.scalar_one_or_none()
        if not row or not row.key_value:
            return {}
        data = json.loads(row.key_value)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _age(when: str) -> float:
    try:
        return (_now() - datetime.fromisoformat(when)).total_seconds() / 3600.0
    except Exception:
        return 1e9


async def state(cap: str) -> dict:
    """Состояние одной возможности: {'state', 'why', 'when', 'evidence'}."""
    data = await _stored(cap)
    if not data:
        return {"state": "unknown", "why": "настоящей попытки ещё не было",
                "when": "", "evidence": ""}
    hours = _age(data.get("when", ""))
    when = data.get("when", "")[:16].replace("T", " ")
    if not data.get("ok"):
        return {"state": "no", "why": data.get("why", "последняя попытка не удалась"),
                "when": when, "evidence": data.get("evidence", "")}
    if hours > PROOF_HOURS:
        return {"state": "unknown",
                "why": f"последний подтверждённый результат старше {PROOF_HOURS} ч",
                "when": when, "evidence": data.get("evidence", "")}
    return {"state": "yes", "why": data.get("why", ""), "when": when,
            "evidence": data.get("evidence", "")}


async def can(cap: str) -> bool:
    """Строгий ответ для оркестратора: обещать можно только подтверждённое."""
    return (await state(cap))["state"] == "yes"


async def registry() -> list[dict]:
    out = []
    for cap, human in CAPABILITIES.items():
        out.append({"id": cap, "human": human, **(await state(cap))})
    return out


ICONS = {"yes": "✅", "no": "❌", "unknown": "❓"}
WORDS = {"yes": "умею", "no": "не работает", "unknown": "не проверено"}


def as_text(rows: list[dict]) -> str:
    lines = ["🧩 <b>Что система умеет на самом деле</b>",
             "Зелёным — только то, что реально дало результат."]
    for r in rows:
        line = f"\n{ICONS.get(r['state'], '❓')} <b>{r['human']}</b> — {WORDS.get(r['state'], '')}"
        if r.get("when") and r["state"] != "unknown":
            line += f" ({r['when']} UTC)"
        lines.append(line)
        if r.get("why"):
            lines.append(f"   {r['why'][:200]}")
    return "\n".join(lines)
