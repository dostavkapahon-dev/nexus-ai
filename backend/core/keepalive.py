"""
Самоподдержка сервиса: не даём бесплатному Render усыпить процесс.

Зачем это нужно. Telegram-бот работает long-polling'ом внутри этого же процесса.
На бесплатном тарифе Render останавливает сервис после ~15 минут без входящих
запросов — и вместе с ним останавливается бот, планировщик и очередь публикаций.
Снаружи это выглядит ровно как «пока не зайдёшь на сайт, ничего не работает»:
открытие адреса будит сервис, и всё «чинится само».

Поэтому раз в несколько минут сервис дёргает собственный `/api/health`. Запрос
уходит наружу и возвращается как входящий — именно его Render и считает
активностью.

Выключается переменной NEXUS_KEEPALIVE=off (например, на платном тарифе, где
сервис и так не засыпает, или если пинг ведут снаружи UptimeRobot'ом).
"""
import os
import asyncio

import httpx

INTERVAL = 600          # 10 минут: Render усыпляет после 15
_TIMEOUT = 20


def base_url() -> str:
    """Публичный адрес сервиса. Пусто — пинговать некуда."""
    return (os.getenv("RENDER_EXTERNAL_URL", "")
            or os.getenv("NEXUS_PUBLIC_URL", "")).strip().rstrip("/")


def enabled() -> bool:
    if (os.getenv("NEXUS_KEEPALIVE", "") or "").strip().lower() in ("off", "0", "false", "no"):
        return False
    return bool(base_url())


def status() -> dict:
    """Для диагностики: работает ли самоподдержка и почему нет."""
    if (os.getenv("NEXUS_KEEPALIVE", "") or "").strip().lower() in ("off", "0", "false", "no"):
        return {"on": False, "reason": "выключена (NEXUS_KEEPALIVE=off)"}
    if not base_url():
        return {"on": False, "reason": "неизвестен адрес сервиса "
                                       "(RENDER_EXTERNAL_URL или NEXUS_PUBLIC_URL)"}
    return {"on": True, "url": base_url(), "interval_sec": INTERVAL}


async def ping_once() -> bool:
    """Один запрос к своему /api/health. Ошибку не поднимаем: это фоновая задача."""
    url = base_url()
    if not url:
        return False
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            r = await c.get(f"{url}/api/health")
        return r.status_code < 400
    except Exception:
        return False


async def loop():
    """Фоновый цикл. Живёт столько же, сколько процесс."""
    while True:
        await asyncio.sleep(INTERVAL)
        await ping_once()


def start():
    """Запускает самоподдержку, если она нужна и есть куда стучаться."""
    st = status()
    if not st["on"]:
        print(f"[NEXUS] самоподдержка не запущена: {st['reason']}", flush=True)
        return None
    print(f"[NEXUS] самоподдержка включена: {st['url']} раз в "
          f"{INTERVAL // 60} мин — Telegram не замолкает от засыпания сервиса",
          flush=True)
    return asyncio.create_task(loop())
