"""
Telegram Bot command handler.
Runs as background webhook/polling alongside FastAPI.
Commands: /status /analyze /create /publish /plan /trends /pause /resume /report /config
"""
import os
import asyncio
import httpx
from sqlalchemy import select
from database.db import AsyncSessionLocal
from database.models import Niche, ContentPlan, UserProfile

BOT_API = "https://api.telegram.org/bot{token}"
_offset = 0

def _url(method: str) -> str:
    return f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN', '')}/{method}"

async def _post(method: str, payload: dict, timeout: float = 20) -> dict:
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(_url(method), json=payload)
            return r.json()
    except Exception as e:
        return {"ok": False, "description": str(e)}


async def send_message(chat_id: str, text: str, parse_mode: str = "HTML",
                       buttons: list = None):
    payload = {"chat_id": chat_id, "text": text[:4096],
               "parse_mode": parse_mode, "disable_web_page_preview": True}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    return await _post("sendMessage", payload)


async def send_photo(chat_id: str, photo_url: str, caption: str = "", buttons: list = None):
    payload = {"chat_id": chat_id, "photo": photo_url,
               "caption": caption[:1024], "parse_mode": "HTML"}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    res = await _post("sendPhoto", payload, timeout=60)
    if not res.get("ok"):
        # Telegram не смог скачать файл — отдаём ссылкой, чтобы результат не потерялся.
        await send_message(chat_id, f"{caption}\n\n🖼 {photo_url}", buttons=buttons)
    return res


async def send_video(chat_id: str, video_url: str, caption: str = "", buttons: list = None):
    payload = {"chat_id": chat_id, "video": video_url,
               "caption": caption[:1024], "parse_mode": "HTML"}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    res = await _post("sendVideo", payload, timeout=120)
    if not res.get("ok"):
        await send_message(chat_id, f"{caption}\n\n🎬 {video_url}", buttons=buttons)
    return res


async def answer_callback(callback_id: str, text: str = ""):
    await _post("answerCallbackQuery", {"callback_query_id": callback_id, "text": text[:200]})


async def send_media(chat_id: str, item: dict, caption: str = "", buttons: list = None):
    """Отправляет один медиа-результат нужным методом."""
    if item.get("kind") == "video":
        return await send_video(chat_id, item["url"], caption, buttons)
    return await send_photo(chat_id, item["url"], caption, buttons)

# Ожидание уточняющего ввода: chat_id → {"action": ..., "plan_id": ...}
_pending: dict = {}


def _plan_buttons(plan_id: str) -> list:
    """Кнопки под готовым контентом: подтвердить / переделать / отредактировать."""
    return [
        [{"text": "✅ Подтвердить", "callback_data": f"ok:{plan_id}"},
         {"text": "🔄 Перегенерировать", "callback_data": f"regen:{plan_id}"}],
        [{"text": "✏️ Редактировать", "callback_data": f"edit:{plan_id}"},
         {"text": "📥 В очередь", "callback_data": f"queue:{plan_id}"}],
        [{"text": "🚀 Опубликовать", "callback_data": f"pub:{plan_id}"}],
    ]


def _task_buttons() -> list:
    """Кнопки под результатом свободной задачи (без привязки к пункту плана)."""
    return [[{"text": "🔄 Ещё вариант", "callback_data": "again"},
             {"text": "🚀 Опубликовать", "callback_data": "pub_last"}]]


async def _handle_text(chat_id: str, text: str):
    """Свободный текст из Telegram → Cloud Opus решает, каких агентов включить.

    Это главная цепочка: Telegram → Cloud Opus → агенты → HIXIIT → Telegram.
    Сайт для неё не нужен.
    """
    # Ждём уточнение после «Редактировать»?
    pending = _pending.pop(chat_id, None)
    if pending and pending.get("action") == "edit":
        await _apply_edit(chat_id, pending["plan_id"], text)
        return

    from core.marketing_director import run_director
    from core.memory import build_context

    await send_message(chat_id, "🧠 Принял задачу. Подключаю агентов…")
    try:
        context = await build_context()
        result = await run_director(text, context)
    except Exception as e:
        await send_message(chat_id, f"❌ Ошибка оркестратора: {str(e)[:300]}")
        return

    summary = result.get("summary") or "Готово."
    media = result.get("media") or []

    if media:
        _last_media[chat_id] = media[-1]
        for i, item in enumerate(media):
            caption = summary if i == len(media) - 1 else ""
            tail = f"\n\n<i>HIXIIT · {item.get('provider','')} · {item.get('model','')}</i>"
            await send_media(chat_id, item, (caption + tail)[:1024],
                             _task_buttons() if i == len(media) - 1 else None)
        return

    steps = result.get("steps") or []
    tail = ""
    if steps:
        tail = "\n\n<i>Шаги: " + ", ".join(
            f"{st.get('action')}{'' if st.get('result_ok', True) else ' ⚠️'}" for st in steps
        ) + "</i>"
    await send_message(chat_id, f"{summary}{tail}", buttons=_task_buttons())


# Последний созданный медиа-результат на чат — для кнопки «Опубликовать»
_last_media: dict = {}
# Последняя задача на чат — для кнопки «Ещё вариант»
_last_task: dict = {}


async def _apply_edit(chat_id: str, plan_id: str, new_text: str):
    """Сохраняет отредактированный пользователем текст контента."""
    from database.models import GeneratedContent
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(GeneratedContent).where(GeneratedContent.plan_id == plan_id).limit(1))
        content = r.scalar_one_or_none()
        if not content:
            await send_message(chat_id, "❌ Контент не найден — нечего редактировать.")
            return
        content.text_reviewed = new_text
        await db.commit()
    await send_message(chat_id, "✏️ Текст обновлён.", buttons=_plan_buttons(plan_id))


async def _handle_callback(chat_id: str, callback_id: str, data: str):
    """Нажатия на inline-кнопки: подтверждение, перегенерация, очередь, публикация."""
    from core.orchestrator import nexus_core
    action, _, plan_id = data.partition(":")

    if action == "ok":
        await answer_callback(callback_id, "Подтверждено")
        async with AsyncSessionLocal() as db:
            r = await db.execute(select(ContentPlan).where(ContentPlan.id == plan_id))
            plan = r.scalar_one_or_none()
            if plan:
                plan.status = "generated"
                await db.commit()
        await send_message(chat_id, "✅ Контент подтверждён и ждёт публикации.")

    elif action == "regen":
        await answer_callback(callback_id, "Перегенерирую")
        asyncio.create_task(nexus_core.generate_content_for_plan(plan_id))
        await send_message(chat_id, "🔄 Перегенерация запущена — пришлю результат.")

    elif action == "edit":
        await answer_callback(callback_id, "Жду новый текст")
        _pending[chat_id] = {"action": "edit", "plan_id": plan_id}
        await send_message(chat_id, "✏️ Пришли новый текст следующим сообщением.")

    elif action == "queue":
        await answer_callback(callback_id, "В очереди")
        async with AsyncSessionLocal() as db:
            r = await db.execute(select(ContentPlan).where(ContentPlan.id == plan_id))
            plan = r.scalar_one_or_none()
            if plan:
                plan.status = "generated"
                await db.commit()
        await send_message(chat_id, "📥 Добавлено в очередь публикаций.")

    elif action == "pub":
        await answer_callback(callback_id, "Публикую")
        try:
            res = await nexus_core.publish_plan(plan_id)
            report = res.get("report", {})
            lines = [f"{'✅' if v.get('ok') else '❌'} {k}: "
                     f"{v.get('via') or v.get('error', '')}" for k, v in report.items()]
            await send_message(chat_id, "🚀 <b>Публикация</b>\n" + "\n".join(lines))
        except Exception as e:
            await send_message(chat_id, f"❌ Ошибка публикации: {str(e)[:300]}")

    elif action == "pub_last":
        await answer_callback(callback_id, "Публикую")
        item = _last_media.get(chat_id)
        if not item:
            await send_message(chat_id, "❗ Нечего публиковать — сначала создай контент.")
            return
        res = await nexus_core._publish_one("telegram", "", item["url"])
        await send_message(chat_id,
                           "🚀 Опубликовано." if res.get("ok")
                           else f"❌ {res.get('error', 'не удалось')}")

    elif action == "again":
        await answer_callback(callback_id, "Ещё вариант")
        task = _last_task.get(chat_id)
        if not task:
            await send_message(chat_id, "❗ Не помню исходную задачу — сформулируй заново.")
            return
        asyncio.create_task(_handle_text(chat_id, task))

    else:
        await answer_callback(callback_id, "Неизвестная кнопка")


async def _handle_command(chat_id: str, text: str):
    from core.orchestrator import nexus_core
    from agents.reporter import reporter

    cmd = text.strip().split()[0].lower().replace("/", "")
    args = text.strip().split()[1:]

    if cmd == "status":
        async with AsyncSessionLocal() as db:
            report = await reporter.build_status_report(db)
        await send_message(chat_id, report)

    elif cmd == "analyze":
        niche_name = " ".join(args) if args else None
        if not niche_name:
            await send_message(chat_id, "❗ Укажи нишу: /analyze [ниша] [город]")
            return
        city = args[1] if len(args) > 1 else ""
        await send_message(chat_id, f"🔍 Запускаю анализ ниши: <b>{niche_name}</b> {city}...")
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Niche).where(Niche.name.ilike(f"%{niche_name}%")).limit(1)
            )
            niche = result.scalar_one_or_none()
            if niche:
                asyncio.create_task(nexus_core.run_full_pipeline(niche.id))
                await send_message(chat_id, f"✅ Анализ запущен для ниши <b>{niche.name}</b>")
            else:
                await send_message(chat_id, f"❌ Ниша '{niche_name}' не найдена. Создай её в дашборде.")

    elif cmd == "create":
        await send_message(chat_id, "✍️ Создаю контент для всех активных ниш...")
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ContentPlan).where(ContentPlan.status == "pending").limit(3)
            )
            plans = result.scalars().all()
            if not plans:
                await send_message(chat_id, "❗ Нет запланированного контента. Запусти /analyze сначала.")
                return
            for plan in plans:
                asyncio.create_task(nexus_core.generate_content_for_plan(plan.id))
        await send_message(chat_id, f"⚙️ Запущена генерация для {len(plans)} постов")

    elif cmd == "publish":
        await send_message(chat_id, "📤 Запускаю публикацию из очереди...")
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ContentPlan).where(ContentPlan.status == "generated").limit(5)
            )
            plans = result.scalars().all()
            if not plans:
                await send_message(chat_id, "❗ Очередь пуста. Запусти /create сначала.")
                return
            published = 0
            for plan in plans:
                try:
                    await nexus_core.publish_plan(plan.id)
                    published += 1
                except Exception as e:
                    await send_message(chat_id, f"⚠️ Ошибка публикации: {str(e)[:100]}")
        await send_message(chat_id, f"✅ Опубликовано: {published} постов")

    elif cmd in ("trends", "trend"):
        await send_message(chat_id, "📈 Анализирую тренды...")
        from core.scheduler import run_daily_trends
        asyncio.create_task(run_daily_trends())
        await send_message(chat_id, "✅ Анализ трендов запущен, отчёт придёт через минуту")

    elif cmd in ("pause", "stop"):
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Niche).where(Niche.status == "active"))
            niches = result.scalars().all()
            for n in niches:
                n.status = "paused"
            await db.commit()
        await send_message(chat_id, f"⏸ Система на паузе. Остановлено ниш: {len(niches)}")

    elif cmd == "resume":
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Niche).where(Niche.status == "paused"))
            niches = result.scalars().all()
            for n in niches:
                n.status = "active"
            await db.commit()
        await send_message(chat_id, f"▶️ Система возобновлена. Активных ниш: {len(niches)}")

    elif cmd == "plan":
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ContentPlan).where(ContentPlan.status == "pending")
                .order_by(ContentPlan.day_number).limit(7)
            )
            plans = result.scalars().all()
        if not plans:
            await send_message(chat_id, "📋 Контент-план пуст")
            return
        lines = ["📋 <b>Контент-план (ближайшие 7)</b>", ""]
        for p in plans:
            lines.append(f"День {p.day_number} · {p.platform} · {p.topic[:50]}")
        await send_message(chat_id, "\n".join(lines))

    elif cmd == "report":
        async with AsyncSessionLocal() as db:
            report = await reporter.build_status_report(db)
        await send_message(chat_id, report)

    elif cmd == "config":
        async with AsyncSessionLocal() as db:
            prof_r = await db.execute(select(UserProfile).limit(1))
            p = prof_r.scalar_one_or_none()
        if p:
            msg = (
                f"⚙️ <b>Конфигурация NEXUS AI</b>\n\n"
                f"🧠 Активный AI: {(p.active_ai or 'claude').upper()}\n"
                f"🎯 Режим: {(p.ai_mode or 'economy').upper()}\n"
                f"📝 Продукт: {(p.product_description or '—')[:100]}\n"
                f"🗓 Стратегия: {p.strategy_focus} · {p.strategy_duration} дней\n"
                f"📂 Google Drive: {'✅' if p.google_drive_folder_id else '❌'}"
            )
        else:
            msg = "⚙️ Профиль не настроен. Зайди в дашборд."
        await send_message(chat_id, msg)

    elif cmd == "prompt":
        from core.brand import set_brand_voice, get_brand_voice
        if not args:
            await send_message(chat_id, "📝 <b>Текущий голос бренда:</b>\n\n" + get_brand_voice()
                               + "\n\nЧтобы изменить: /prompt [новый текст]")
            return
        set_brand_voice(" ".join(args))
        await send_message(chat_id, "✅ Голос бренда обновлён (brand_voice.txt)")

    elif cmd == "preview":
        from core.brand import system_prompt, PLATFORM_SPECS, BRAND
        if args:
            async with AsyncSessionLocal() as db:
                pr = await db.execute(select(ContentPlan).where(ContentPlan.id == args[0]))
                p = pr.scalar_one_or_none()
            if p:
                await send_message(chat_id, f"👁 <b>Превью #{args[0][:8]}</b>\n"
                                   f"{p.platform} · {p.topic}\nХук: {p.hook or '—'}")
            else:
                await send_message(chat_id, "❌ Пункт плана не найден")
            return
        specs = "\n".join(f"• {k}: {v.get('format')} {v.get('length_sec') or v.get('length_chars')}"
                          for k, v in PLATFORM_SPECS.items())
        await send_message(chat_id, f"🎬 <b>{BRAND['name']}</b> — платформо-специфика:\n{specs}")

    elif cmd == "generate":
        if not args:
            await send_message(chat_id, "❗ Укажи id пункта плана: /generate [id]")
            return
        asyncio.create_task(nexus_core.generate_content_for_plan(args[0]))
        await send_message(chat_id, f"⚙️ Генерация запущена для {args[0][:8]}...")

    elif cmd in ("hixiit", "hixit", "higgsfield"):
        from core.hixiit import status as hixiit_status
        st = await hixiit_status()
        paths = [
            f"{'✅' if st.get('mcp_ok') else ('⚠️' if st['mcp_configured'] else '❌')} "
            f"MCP (основной путь)"
            + (f" — {st.get('mcp_error','')[:120]}" if st.get("mcp_error") else ""),
            f"{'✅' if st['api_key'] else '❌'} API-ключ HIGGSFIELD_API_KEY",
            f"{'✅' if st['browser_agent'] else '❌'} браузер-агент на ПК",
        ]
        extra = ""
        if st.get("credits") is not None:
            extra = f"\n💳 Кредитов: {st['credits']} · план {st.get('plan', '—')}"
        if not st["mcp_configured"]:
            extra += ("\n\n⚠️ MCP не настроен: добавь HIGGSFIELD_MCP_URL "
                      "и HIGGSFIELD_MCP_TOKEN в переменные окружения.")
        await send_message(chat_id, "🎨 <b>HIXIIT — генеративный слой</b>\n\n"
                           + "\n".join(paths)
                           + f"\n\n🤖 Модель по умолчанию: {st['default_model']}" + extra)

    elif cmd in ("factory", "reel"):
        # Полный цикл: анализ → генерация → публикация. Без аргумента — dry-run.
        from core.content_factory import run_factory
        topic = " ".join(args) if args else None
        publish = bool(args) and args[-1].lower() in ("post", "publish", "go")
        if publish:
            topic = " ".join(args[:-1]) or None
        await send_message(chat_id, f"🏭 Фабрика контента запущена{' (публикация)' if publish else ' (превью)'}...")
        asyncio.create_task(run_factory(topic=topic, dry_run=not publish))

    elif cmd.startswith("set_goal"):
        try:
            goal = int(args[0])
        except (IndexError, ValueError):
            await send_message(chat_id, "❗ Укажи число: /set_goal 100000")
            return
        async with AsyncSessionLocal() as db:
            prof_r = await db.execute(select(UserProfile).limit(1))
            prof = prof_r.scalar_one_or_none()
            if not prof:
                prof = UserProfile()
                db.add(prof)
            prof.strategy_focus = f"{goal} подписчиков"
            await db.commit()
        await send_message(chat_id, f"🎯 Цель сохранена: {goal:,} подписчиков")

    elif cmd.startswith("set_posts"):
        try:
            n_posts = int(args[0])
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(Niche).where(Niche.status == "active"))
                niches = result.scalars().all()
                for n in niches:
                    n.posts_per_day = n_posts
                await db.commit()
            await send_message(chat_id, f"📅 Постов/день обновлено: {n_posts}")
        except (IndexError, ValueError):
            await send_message(chat_id, "❗ Укажи число: /set_posts 3")

    else:
        cmds = [
            "/status   — статус системы",
            "/factory [тема] — ВЕСЬ цикл: анализ→генерация→превью",
            "/factory [тема] post — то же + публикация",
            "/analyze [ниша] — запустить анализ",
            "/create   — создать контент",
            "/generate [id] — генерация по пункту плана",
            "/publish  — опубликовать очередь",
            "/trend    — тренды прямо сейчас",
            "/plan     — контент-план на неделю",
            "/preview [id] — превью контента/специфики",
            "/prompt [текст] — голос бренда",
            "/report   — отчёт",
            "/pause /resume — пауза/возобновить",
            "/hixiit   — статус генеративного слоя",
            "/config   — настройки",
        ]
        await send_message(
            chat_id,
            "🤖 <b>Pakhon Studio · NEXUS AI</b>\n\n"
            "💬 Просто напиши задачу словами — например «сделай reels про доставку»: "
            "её примет Cloud Opus, распределит по агентам, HIXIIT сгенерирует визуал, "
            "результат придёт сюда с кнопками.\n\n"
            "<b>Команды:</b>\n" + "\n".join(cmds))

async def poll_updates():
    """Long-polling loop for Telegram updates."""
    global _offset
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token:
        return

    while True:
        try:
            async with httpx.AsyncClient(timeout=35) as c:
                r = await c.get(_url("getUpdates"), params={"offset": _offset, "timeout": 30})
                updates = r.json().get("result", [])
                for upd in updates:
                    _offset = upd["update_id"] + 1

                    # Нажатие inline-кнопки
                    cb = upd.get("callback_query")
                    if cb:
                        cb_chat = str(cb.get("message", {}).get("chat", {}).get("id", ""))
                        if not chat_id or cb_chat == chat_id:
                            asyncio.create_task(_handle_callback(
                                cb_chat, cb.get("id", ""), cb.get("data", "")))
                        continue

                    msg = upd.get("message", {})
                    text = (msg.get("text") or msg.get("caption") or "").strip()
                    upd_chat_id = str(msg.get("chat", {}).get("id", ""))
                    if not text or (chat_id and upd_chat_id != chat_id):
                        continue

                    if text.startswith("/"):
                        asyncio.create_task(_handle_command(upd_chat_id, text))
                    else:
                        # Свободный текст — это задача для Cloud Opus.
                        _last_task[upd_chat_id] = text
                        asyncio.create_task(_handle_text(upd_chat_id, text))
        except Exception:
            await asyncio.sleep(5)
        await asyncio.sleep(1)

def start_polling():
    """Start the Telegram polling loop as background task."""
    asyncio.create_task(poll_updates())
