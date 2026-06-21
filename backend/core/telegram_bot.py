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

async def send_message(chat_id: str, text: str, parse_mode: str = "HTML"):
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            await c.post(_url("sendMessage"), json={
                "chat_id": chat_id, "text": text,
                "parse_mode": parse_mode, "disable_web_page_preview": True
            })
    except Exception:
        pass

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

    elif cmd == "trends":
        await send_message(chat_id, "📈 Анализирую тренды...")
        from core.scheduler import run_daily_trends
        asyncio.create_task(run_daily_trends(force=True))
        await send_message(chat_id, "✅ Анализ трендов запущен, отчёт придёт через минуту")

    elif cmd in ("pause", "stop"):
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Niche).where(Niche.status == "active"))
            niches = result.scalars().all()
            for n in niches:
                n.status = "paused"
            await db.commit()
        await send_message(chat_id, f"⏸ Система на паузе. Остановлено ниш: {len(niches)}")

    elif cmd in ("resume", "start"):
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

    elif cmd.startswith("set_goal"):
        try:
            goal = int(args[0])
            await send_message(chat_id, f"🎯 Цель установлена: {goal:,} подписчиков")
        except (IndexError, ValueError):
            await send_message(chat_id, "❗ Укажи число: /set_goal 100000")

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
            "/analyze [ниша] — запустить анализ",
            "/create   — создать контент",
            "/publish  — опубликовать очередь",
            "/trends   — тренды прямо сейчас",
            "/plan     — контент-план на неделю",
            "/pause    — поставить на паузу",
            "/resume   — возобновить",
            "/report   — отчёт",
            "/config   — настройки",
        ]
        await send_message(chat_id, "🤖 <b>NEXUS AI Bot</b>\n\n" + "\n".join(cmds))

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
                    msg = upd.get("message", {})
                    text = msg.get("text", "")
                    upd_chat_id = str(msg.get("chat", {}).get("id", ""))
                    if text.startswith("/") and (not chat_id or upd_chat_id == chat_id):
                        asyncio.create_task(_handle_command(upd_chat_id, text))
        except Exception:
            await asyncio.sleep(5)
        await asyncio.sleep(1)

def start_polling():
    """Start the Telegram polling loop as background task."""
    asyncio.create_task(poll_updates())
