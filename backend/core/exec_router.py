"""Execution Router: каким каналом выполнять задачу — по факту, а не по списку.

До этого порядок каналов был зашит: MCP → REST → браузер. Это не маршрутизация,
а очередь. Она одинаково ведёт себя и когда MCP отвечает за секунду, и когда он
месяц подряд требует OAuth, которого на сервере не будет никогда.

Здесь порядок считается каждый раз из четырёх вещей:

  * режим, выбранный человеком (auto / mcp / api / browser) — он главнее всего;
  * настроен ли канал вообще (нет ключа — нечего и пробовать);
  * «остывание» после недавнего отказа (его ведёт core.hixiit);
  * история: сколько раз канал доводил задачу до результата и как быстро.

История — это §36 ТЗ: система должна постепенно понимать, какой путь работает.
Она хранится там же, где остальное состояние (KV в таблице Connection), поэтому
переживает перезапуск и не требует миграции схемы.

Модуль ничего не выполняет сам. Он только отвечает на вопрос «в каком порядке
пробовать» и записывает, чем закончилась попытка.
"""
import json
import time

# Каналы выполнения. Порядок здесь — только запасной, на случай полного
# отсутствия истории и одинаковой пригодности.
CHANNELS = ("mcp", "rest", "browser")

HUMAN = {"mcp": "MCP", "rest": "REST", "browser": "Браузер"}

STATS_KEY = "exec_router_stats"

# Режимы выполнения задают не «порядок», а ограничение: человек выбрал канал —
# значит остальные не трогаем вовсе, даже если они быстрее.
MODE_ONLY = {"mcp": ("mcp",), "api": ("rest",), "browser": ("browser",)}

# Как режим называется человеку. Слова те же, что были до появления роутера:
# людям и тестам важно узнавать знакомую формулировку, а не новую.
MODE_LABEL = {"mcp": "только MCP", "api": "только API по ключу",
              "browser": "через браузер"}

# Чего именно не хватает каналу. «Не настроен» без имени переменной заставляет
# человека угадывать, что вписать в хостинг, — а вписать нужно ровно это.
MISSING = {
    "mcp": "не настроен (нет HIGGSFIELD_MCP_URL)",
    "rest": "не настроен (нужны HIGGSFIELD_API_KEY и HIGGSFIELD_SECRET)",
    "browser": "не настроен",
}

# Режимы качества (§10/§17). Влияют на то, чем жертвуем при равной пригодности.
QUALITY_MODES = ("auto", "fast", "quality", "economy")

# Что каждый канал делает хорошо. Браузер работает в аккаунте с безлимитом,
# поэтому он дешёвый, но медленный: это не «хуже», это другой размен.
TRAITS = {
    "mcp":     {"speed": 3, "quality": 3, "cost": 2},
    "rest":    {"speed": 3, "quality": 3, "cost": 1},
    "browser": {"speed": 1, "quality": 3, "cost": 3},
}


def _blank() -> dict:
    return {"ok": 0, "fail": 0, "sec": 0.0, "last_ok": 0.0, "last_error": ""}


async def stats() -> dict:
    """История по каналам. Пустая, пока ни одной попытки не было."""
    try:
        from sqlalchemy import select
        from database.db import AsyncSessionLocal
        from database.models import Connection
        async with AsyncSessionLocal() as db:
            r = await db.execute(select(Connection).where(
                Connection.key_name == STATS_KEY))
            row = r.scalar_one_or_none()
        data = json.loads(row.key_value) if row and row.key_value else {}
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return {c: {**_blank(), **(data.get(c) or {})} for c in CHANNELS}


async def record(channel: str, ok: bool, seconds: float = 0.0,
                 error: str = "") -> None:
    """Запоминает исход попытки. Никогда не роняет генерацию."""
    if channel not in CHANNELS:
        return
    try:
        # Пишем прямо в KV, а не через core.credentials: история маршрутов —
        # не секрет, её незачем шифровать и тем более класть в os.environ.
        from sqlalchemy import select
        from database.db import AsyncSessionLocal
        from database.models import Connection
        data = await stats()
        stat = data[channel]
        if ok:
            stat["ok"] += 1
            stat["last_ok"] = time.time()
            stat["last_error"] = ""
            if seconds > 0:
                # Среднее по успешным: провалы бывают мгновенными, и смешивать
                # их со временем работы — значит считать сломанный канал быстрым.
                stat["sec"] = ((stat["sec"] * (stat["ok"] - 1) + seconds)
                               / stat["ok"] if stat["ok"] else seconds)
        else:
            stat["fail"] += 1
            stat["last_error"] = str(error or "")[:200]
        async with AsyncSessionLocal() as db:
            r = await db.execute(select(Connection).where(
                Connection.key_name == STATS_KEY))
            row = r.scalar_one_or_none()
            packed = json.dumps(data, ensure_ascii=False)
            if row:
                row.key_value = packed
            else:
                db.add(Connection(key_name=STATS_KEY, key_value=packed))
            await db.commit()
    except Exception as e:
        print(f"[NEXUS] маршруты не записались: {type(e).__name__}: "
              f"{str(e)[:120]}", flush=True)


def success_rate(row: dict) -> float:
    """Доля успеха. Без попыток — 0.5: не хвалим и не хороним заранее."""
    total = row.get("ok", 0) + row.get("fail", 0)
    if not total:
        return 0.5
    return row["ok"] / total


def _score(channel: str, row: dict, quality: str) -> float:
    """Чем больше, тем раньше пробуем.

    Основа — доля успеха: канал, который ни разу не довёл задачу до файла,
    не должен идти первым только потому, что он «основной». Режим качества
    добавляет вес одному из свойств, а не переворачивает порядок целиком.
    """
    score = success_rate(row) * 10
    traits = TRAITS.get(channel, {})
    if quality == "fast":
        score += traits.get("speed", 0)
        # Медленный канал в режиме скорости отодвигаем ещё и по замеру.
        if row.get("sec", 0) > 120:
            score -= 2
    elif quality == "economy":
        score += traits.get("cost", 0)
    elif quality == "quality":
        score += traits.get("quality", 0)
    return score


async def order(mode: str = "auto", quality: str = "auto",
                configured: dict | None = None,
                cooling: dict | None = None) -> list[dict]:
    """Порядок каналов с объяснением по каждому.

    `configured` — {канал: bool}, есть ли доступ вообще.
    `cooling`    — {канал: секунды до повтора}, 0 если канал не остывает.

    Возвращает список словарей: channel, use (пробовать ли), why (причина).
    Каналы, которые пробовать не нужно, остаются в списке — чтобы человек
    видел, почему путь пропущен, а не гадал.
    """
    configured = configured or {}
    cooling = cooling or {}
    data = await stats()
    allowed = MODE_ONLY.get(mode)
    quality = quality if quality in QUALITY_MODES else "auto"

    rows = []
    for channel in CHANNELS:
        row = data[channel]
        item = {"channel": channel, "use": True, "why": "",
                "score": _score(channel, row, quality),
                "rate": success_rate(row), "sec": row.get("sec", 0.0)}
        if allowed is not None and channel not in allowed:
            item.update(use=False,
                        why=f"пропущен (режим «{MODE_LABEL.get(mode, mode)}»)",
                        score=-1)
        elif not configured.get(channel, False):
            item.update(use=False, why=MISSING.get(channel, "не настроен"),
                        score=-1)
        elif cooling.get(channel, 0) > 0:
            item.update(use=False,
                        why=f"пропущен — отказал недавно, повтор через "
                            f"{cooling[channel] / 60:.0f} мин",
                        score=-1)
        rows.append(item)

    rows.sort(key=lambda r: (-r["score"], CHANNELS.index(r["channel"])))
    return rows


def as_text(rows: list[dict]) -> str:
    """Отчёт для Telegram: порядок и причина по каждому каналу."""
    lines = ["🔀 <b>Маршруты выполнения</b>", ""]
    live = [r for r in rows if r["use"]]
    if live:
        lines.append("Порядок: " + " → ".join(HUMAN[r["channel"]] for r in live))
        lines.append("")
    for r in rows:
        name = HUMAN[r["channel"]]
        if not r["use"]:
            lines.append(f"⛔️ {name} — {r['why']}")
            continue
        part = f"✅ {name} — успех {r['rate'] * 100:.0f}%"
        if r["sec"]:
            part += f", в среднем {r['sec']:.0f} с"
        lines.append(part)
    if not live:
        lines.append("")
        lines.append("Ни одного доступного канала: генерация сейчас невозможна.")
    return "\n".join(lines)
