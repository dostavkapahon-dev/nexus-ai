"""
Авто-запуск анализа на старте сервера — «сервер сам делает и присылает в Telegram».

Логика (раз в сутки, чтобы не спамить при перезапусках Render):
  • нет Telegram-бота → выходим тихо;
  • нет никнеймов для анализа → раз в день шлём напоминание их добавить;
  • всё настроено → запускаем разбор аккаунта (Роль 1) и шлём отчёт админу.
"""
import os
import asyncio
from datetime import date
from sqlalchemy import select
from database.db import AsyncSessionLocal
from database.models import Connection

MARKER = "last_auto_analyze"


async def _marker_get(db):
    r = await db.execute(select(Connection).where(Connection.key_name == MARKER))
    c = r.scalar_one_or_none()
    return (c.key_value if c else None), c


async def _marker_set(db, value: str):
    _, c = await _marker_get(db)
    if c:
        c.key_value = value
    else:
        db.add(Connection(key_name=MARKER, key_value=value))
    await db.commit()


async def auto_analyze_on_start(delay: float = 25.0):
    """Фоновая задача: ждёт запуска и раз в сутки шлёт разбор аккаунта в Telegram."""
    try:
        await asyncio.sleep(delay)
    except Exception:
        pass

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    admin = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not admin:
        return  # без бота/чата некуда слать

    from core.telegram_bot import send_message
    today = date.today().isoformat()

    async with AsyncSessionLocal() as db:
        last, _ = await _marker_get(db)
        if last == today:
            return  # сегодня уже отправляли

        from core.social_intel import is_configured
        if not await is_configured():
            await send_message(
                admin,
                "👋 <b>NEXUS AI запущен.</b>\n\nЧтобы я сам анализировал твои аккаунты, "
                "укажи ники в Настройках сайта: <code>IG_HANDLE</code>, "
                "<code>TIKTOK_HANDLE</code>, <code>YOUTUBE_HANDLE</code> (для Instagram "
                "можно добавить <code>BRIGHTDATA_API_KEY</code>). После этого пришлю "
                "разбор автоматически.\n\nПроверить вручную: /strategy",
            )
            await _marker_set(db, today)
            return

        await send_message(admin, "🧠 <b>NEXUS AI</b>: анализирую твой Instagram, минуту...")
        try:
            from core.strategy_advisor import build_options
            data = await build_options(db)
            analysis = data.get("analysis", [])
            options = data.get("options", [])
            lines = ["📊 <b>Разбор аккаунта</b>"] + [f"• {a}" for a in analysis]
            if options:
                lines += ["", "🎯 <b>Варианты стратегии</b> (выбрать: /strategy)"]
                for i, o in enumerate(options):
                    lines.append(f"{i+1}. <b>{o.get('title','')}</b> — {o.get('desc','')}")
            await send_message(admin, "\n".join(lines))
        except Exception as e:
            await send_message(admin, f"⚠️ Не смог разобрать аккаунт: {str(e)[:150]}\nПопробуй /strategy")
        await _marker_set(db, today)
