"""
Измерение исходящей сети: что с сервера доходит, а что нет.

Догадки кончились. Картина была странной: Telegram и Groq отвечают, а
DuckDuckGo, Mojeek, браузер и Higgsfield — «не ответил за 10 секунд», все
разом. Такое бывает по трём разным причинам, и лечатся они по-разному:

  1. сеть хостинга не пускает часть адресов — лечится сменой источника;
  2. процессу не хватает воздуха (память, CPU) — лечится разгрузкой;
  3. событийный цикл занят — лечится переносом тяжёлой работы в поток.

Различить их можно только замером: каждый адрес отдельно, с коротким сроком, и
рядом — сколько времени занял простой расчёт в том же процессе. Если расчёт
тоже тормозит, дело не в сети.
"""
import asyncio
import time

# Адреса выбраны так, чтобы различить случаи: два заведомо рабочих (их видно в
# отчётах), два поисковых и два целевых для Higgsfield.
TARGETS = (
    ("Telegram API", "https://api.telegram.org"),
    ("Google", "https://www.google.com/generate_204"),
    ("Higgsfield API", "https://platform.higgsfield.ai"),
    ("Higgsfield MCP", "https://mcp.higgsfield.ai"),
    ("Mojeek", "https://www.mojeek.com"),
    ("DuckDuckGo", "https://duckduckgo.com"),
)

TIMEOUT = 8.0


async def _one(name: str, url: str) -> dict:
    import httpx
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as c:
            r = await c.get(url)
        return {"name": name, "ok": True, "code": r.status_code,
                "sec": round(time.monotonic() - started, 2)}
    except Exception as e:
        return {"name": name, "ok": False,
                "code": f"{type(e).__name__}: {str(e)[:80]}",
                "sec": round(time.monotonic() - started, 2)}


async def loop_lag() -> float:
    """Насколько опаздывает событийный цикл.

    Просим уснуть на 0.1 с и смотрим, сколько прошло на самом деле. Большая
    разница означает, что цикл занят чужой работой, и тогда «сайт не ответил» —
    это не про сайт.
    """
    started = time.monotonic()
    await asyncio.sleep(0.1)
    return round(time.monotonic() - started - 0.1, 3)


def memory() -> dict:
    """Сколько памяти занимает процесс и сколько её всего у контейнера."""
    out = {"rss_mb": 0.0, "limit_mb": 0.0}
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    out["rss_mb"] = round(int(line.split()[1]) / 1024, 1)
    except Exception:
        pass
    for path in ("/sys/fs/cgroup/memory.max",
                 "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            with open(path) as f:
                raw = f.read().strip()
            if raw and raw != "max":
                mb = int(raw) / 1024 / 1024
                # Когда лимит не задан, ядро пишет гигантское число вроде
                # 8 796 093 022 208 МБ. Это «без лимита», а не 8 петабайт.
                if mb < 1_000_000:
                    out["limit_mb"] = round(mb, 1)
                break
        except Exception:
            continue
    return out


async def run() -> dict:
    """Полный замер: сеть по адресам, задержка цикла, память."""
    lag_before = await loop_lag()
    # Последовательно, а не пачкой: пачка маскирует картину, если упирается
    # не сеть, а сам процесс.
    results = []
    for name, url in TARGETS:
        results.append(await _one(name, url))
    lag_after = await loop_lag()
    return {"targets": results, "lag_before": lag_before, "lag_after": lag_after,
            "memory": memory()}


def as_text(report: dict) -> str:
    lines = ["📡 <b>Проверка исходящей сети</b>"]
    for r in report.get("targets", []):
        icon = "✅" if r["ok"] else "❌"
        lines.append(f"{icon} {r['name']} — {r['code']} · {r['sec']} с")

    mem = report.get("memory", {})
    if mem.get("rss_mb"):
        limit = f" из {mem['limit_mb']:.0f} МБ" if mem.get("limit_mb") else ""
        lines.append(f"\n🧠 Память процесса: {mem['rss_mb']:.0f} МБ{limit}")
    lag = max(report.get("lag_before", 0), report.get("lag_after", 0))
    lines.append(f"⏱ Задержка событийного цикла: {lag:.3f} с")

    ok = [r for r in report.get("targets", []) if r["ok"]]
    if lag > 1.0:
        lines.append("\n<b>Вывод:</b> цикл занят чужой работой — «сайт не ответил» "
                     "тут не про сайт, а про процесс.")
    elif mem.get("limit_mb") and mem.get("rss_mb", 0) > mem["limit_mb"] * 0.85:
        lines.append("\n<b>Вывод:</b> память на исходе — процессу не хватает "
                     "воздуха, отсюда таймауты на всём подряд.")
    elif ok and len(ok) < len(report.get("targets", [])):
        closed = ", ".join(r["name"] for r in report["targets"] if not r["ok"])
        lines.append(f"\n<b>Вывод:</b> сеть работает выборочно — не доходит: "
                     f"{closed}. Это ограничение хостинга, а не ключей.")
    elif not ok:
        lines.append("\n<b>Вывод:</b> наружу не проходит ничего — проверьте "
                     "сеть хостинга.")
    else:
        lines.append("\n<b>Вывод:</b> сеть в порядке, причина таймаутов не здесь.")
    return "\n".join(lines)
