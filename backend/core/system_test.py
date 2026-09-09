"""
Самопроверка системы: что реально работает прямо сейчас.

Отличие от `/diag`. Диагностика отвечает на вопрос «что настроено»: есть ключ,
подключена площадка, живой ли планировщик. Этого мало — ключ бывает от другого
аккаунта, модель отвечает отказом, а память теряется при рестарте. Здесь каждая
проверка делает НАСТОЯЩИЙ вызов и показывает доказательство: что отправили, что
получили обратно и почему это считается успехом.

Что проверка НЕ делает по умолчанию:
  * не публикует ничего наружу — ни одного поста;
  * не жжёт генерации. Картинка создаётся только в режиме `deep=True`, и об
    этом сказано прямо в отчёте, чтобы расход не становился сюрпризом.
"""
import asyncio
import time

# Проверка не должна висеть: лучше честное «не ответил за N секунд».
TIMEOUT = 60


def _ok(name: str, detail: str, evidence: str = "", started: float = 0.0) -> dict:
    return {"name": name, "ok": True, "detail": detail, "evidence": evidence[:300],
            "sec": round(time.monotonic() - started, 1) if started else 0.0}


def _fail(name: str, detail: str, evidence: str = "", started: float = 0.0) -> dict:
    return {"name": name, "ok": False, "detail": detail, "evidence": evidence[:300],
            "sec": round(time.monotonic() - started, 1) if started else 0.0}


async def check_memory() -> dict:
    """Память: записать значение и прочитать его обратно."""
    t = time.monotonic()
    from core.health import _probe_memory
    res = await _probe_memory()
    name = "Память"
    if res.get("ok"):
        return _ok(name, res.get("detail", ""), "запись и чтение подтверждены", t)
    return _fail(name, res.get("detail", "не работает"), "", t)


async def check_ai() -> dict:
    """Модель ИИ: задать вопрос с известным ответом и сверить его.

    «Ключ задан» ничего не доказывает. Здесь модель обязана вернуть текст, и
    ответ проверяется по существу, а не по факту непустой строки.
    """
    t = time.monotonic()
    name = "Модель ИИ"
    from core.ai_router import ai_router, ECONOMY_MODELS
    model = ECONOMY_MODELS.get("copywriter", "gemini-2.0-flash")
    try:
        res = await ai_router.call(
            model, "Отвечай одним словом, без пояснений.",
            "Сколько будет два плюс два? Ответь только числом.")
    except Exception as e:
        return _fail(name, f"{type(e).__name__}: {str(e)[:140]}", "", t)

    text = (res.get("text") or "").strip()
    used = res.get("model_used") or model
    if not text:
        return _fail(name, "модель ответила пустотой", f"модель: {used}", t)
    if "4" not in text and "четыре" not in text.lower():
        # Ответ есть, но неверный: связь работает, доверять содержимому нельзя.
        return _fail(name, "ответ не совпал с ожидаемым",
                     f"{used} → {text[:80]}", t)
    return _ok(name, f"ответила {used}", f"2+2 → {text[:40]}", t)


async def check_search() -> dict:
    """Веб-поиск: настоящий запрос и непустая выдача."""
    t = time.monotonic()
    name = "Интернет-поиск"
    from core.websearch import search
    try:
        res = await search("новости маркетинга", 2)
    except Exception as e:
        return _fail(name, f"{type(e).__name__}: {str(e)[:140]}", "", t)
    items = res.get("results") or []
    if res.get("ok") and items:
        first = (items[0].get("title") or items[0].get("url") or "")[:80]
        return _ok(name, f"найдено: {len(items)}", first, t)
    return _fail(name, str(res.get("error") or "пустая выдача")[:140], "", t)


async def check_hixiit(deep: bool = False) -> dict:
    """Генеративный слой: доступ, а в глубоком режиме — настоящая картинка."""
    t = time.monotonic()
    name = "Higgsfield"
    from core.hixiit import status
    try:
        st = await status()
    except Exception as e:
        return _fail(name, f"{type(e).__name__}: {str(e)[:140]}", "", t)

    if st.get("mcp_ok"):
        route = f"MCP, кредитов: {st.get('credits', '—')}"
    elif st.get("api_ok"):
        route = "API по ключу и секрету"
    elif st.get("browser_agent"):
        route = "браузер-агент на ПК"
    else:
        return _fail(name, str(st.get("api_error") or st.get("mcp_error")
                               or "доступа нет")[:140],
                     "ни один путь генерации не отвечает", t)

    if not deep:
        # Доступ есть, но генерация не запускалась: писать «работает» про то,
        # чего не проверяли, — ровно та ложь, от которой уходим.
        return _ok(name, route, "доступ подтверждён; генерация не запускалась "
                                "(нужен глубокий режим)", t)

    from core.hixiit import generate
    try:
        res = await generate("минималистичный логотип: чашка кофе",
                             kind="image", qc=False)
    except Exception as e:
        return _fail(name, f"генерация упала: {type(e).__name__}", str(e)[:140], t)
    url = res.get("url") or res.get("image_url") or ""
    if res.get("ok") and url:
        return _ok(name, f"{route}; картинка создана", url, t)
    return _fail(name, str(res.get("error") or "генерация не дала файла")[:140],
                 route, t)


async def check_model_routing() -> dict:
    """Выбор модели: разные задачи не должны уходить в одну и ту же модель."""
    t = time.monotonic()
    name = "Выбор модели"
    from core.hixiit import pick_by_task
    try:
        product = pick_by_task("реклама кофейного стакана, товар крупно", "image")
        person = pick_by_task("портрет бариста за стойкой", "image")
        video = pick_by_task("динамичный ролик о кофейне", "video")
    except Exception as e:
        return _fail(name, f"{type(e).__name__}: {str(e)[:140]}", "", t)
    if not (product and person and video):
        return _fail(name, "маршрутизатор вернул пустую модель",
                     f"{product} / {person} / {video}", t)
    if product == person:
        return _fail(name, "товар и человек идут в одну модель",
                     f"обе задачи → {product}", t)
    return _ok(name, "задачи расходятся по моделям",
               f"товар → {product}; человек → {person}; видео → {video}", t)


async def check_queue() -> dict:
    """Учёт задач: задача создаётся, читается и закрывается."""
    t = time.monotonic()
    name = "Очередь задач"
    from core import task_manager as tm
    try:
        task_id = await tm.create("selftest", "самопроверка системы", source="system_test")
        await tm.add_step(task_id, "проверочный шаг", ok=True)
        task = await tm.get(task_id)
        await tm.cancel(task_id)
        closed = await tm.get(task_id)
    except Exception as e:
        return _fail(name, f"{type(e).__name__}: {str(e)[:140]}", "", t)
    if not task or not task.get("steps"):
        return _fail(name, "задача создана, но журнал шагов пуст", str(task_id), t)
    if closed.get("status") != tm.CANCELLED:
        return _fail(name, "задачу не удалось закрыть", str(closed.get("status")), t)
    return _ok(name, "создание, журнал и закрытие работают", str(task_id), t)


async def check_scheduler() -> dict:
    """Планировщик: живой процесс и джобы с ближайшим запуском."""
    t = time.monotonic()
    name = "Планировщик"
    from core.health import scheduler_jobs
    st = scheduler_jobs()
    if not st.get("running"):
        return _fail(name, "не запущен — расписание не сработает",
                     str(st.get("error") or "")[:140], t)
    jobs = st.get("jobs") or []
    if not jobs:
        return _fail(name, "запущен, но задач в расписании нет", "", t)
    nxt = next((j["next_run"] for j in jobs if j.get("next_run")), "—")
    return _ok(name, f"джобов: {len(jobs)}", f"ближайший запуск: {nxt}", t)


async def check_telegram() -> dict:
    """Telegram: бот отвечает на getMe своим именем."""
    t = time.monotonic()
    name = "Telegram"
    from core.health import _probe_telegram
    res = await _probe_telegram()
    if res.get("ok"):
        return _ok(name, "бот отвечает", res.get("detail", ""), t)
    return _fail(name, res.get("detail", "не отвечает"), "", t)


CHECKS = (check_memory, check_telegram, check_ai, check_search,
          check_model_routing, check_hixiit, check_queue, check_scheduler)


async def run(deep: bool = False) -> dict:
    """Прогоняет все проверки параллельно и собирает честный отчёт."""
    async def one(fn):
        try:
            kwargs = {"deep": deep} if fn is check_hixiit else {}
            return await asyncio.wait_for(fn(**kwargs), timeout=TIMEOUT)
        except asyncio.TimeoutError:
            return _fail(getattr(fn, "__name__", "проверка"),
                         f"не ответила за {TIMEOUT} секунд")
        except Exception as e:
            return _fail(getattr(fn, "__name__", "проверка"),
                         f"{type(e).__name__}: {str(e)[:140]}")

    started = time.monotonic()
    results = list(await asyncio.gather(*(one(f) for f in CHECKS)))
    passed = [r for r in results if r["ok"]]
    return {"ok": len(passed) == len(results), "passed": len(passed),
            "total": len(results), "deep": deep,
            "sec": round(time.monotonic() - started, 1), "checks": results}


def as_text(report: dict) -> str:
    """Отчёт для Telegram: сначала итог, потом каждая проверка с доказательством."""
    head = ("✅ Все проверки пройдены" if report.get("ok")
            else f"⚠️ Пройдено {report.get('passed', 0)} из {report.get('total', 0)}")
    lines = [f"🧪 <b>Самопроверка системы</b>\n{head} "
             f"за {report.get('sec', 0)} с"]
    for c in report.get("checks", []):
        lines.append(f"\n{'✅' if c['ok'] else '❌'} <b>{c['name']}</b> — {c['detail']}")
        if c.get("evidence"):
            lines.append(f"   <code>{c['evidence']}</code>")
    if not report.get("deep"):
        lines.append("\nГенерация не запускалась, чтобы не тратить кредиты: "
                     "полная проверка — <code>/system_test deep</code>")
    return "\n".join(lines)
