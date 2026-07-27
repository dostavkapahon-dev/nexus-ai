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

async def send_message(chat_id: str, text: str, parse_mode: str = "HTML", reply_markup: dict = None):
    try:
        payload = {
            "chat_id": chat_id, "text": text,
            "parse_mode": parse_mode, "disable_web_page_preview": True
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        async with httpx.AsyncClient(timeout=10) as c:
            await c.post(_url("sendMessage"), json=payload)
    except Exception:
        pass


def _main_menu_kb() -> dict:
    """Инлайн-кнопки пульта управления."""
    return {"inline_keyboard": [
        [{"text": "📊 Статус", "callback_data": "status"},
         {"text": "📋 План", "callback_data": "plan"}],
        [{"text": "✍️ Создать", "callback_data": "create"},
         {"text": "📤 Опубликовать", "callback_data": "publish"}],
        [{"text": "🧠 Стратегия", "callback_data": "strategy"},
         {"text": "📈 Тренды", "callback_data": "trend"}],
        [{"text": "🏭 Фабрика (превью)", "callback_data": "factory"}],
        [{"text": "⏸ Пауза", "callback_data": "pause"},
         {"text": "▶️ Возобновить", "callback_data": "resume"}],
        [{"text": "⚙️ Настройки", "callback_data": "config"}],
    ]}


async def _answer_callback(callback_id: str, text: str = ""):
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            await c.post(_url("answerCallbackQuery"),
                         json={"callback_query_id": callback_id, "text": text})
    except Exception:
        pass


async def setup_bot_commands():
    """Регистрирует список команд (кнопка «Меню» в клиенте Telegram)."""
    cmds = [
        {"command": "menu", "description": "Пульт управления (кнопки)"},
        {"command": "diag", "description": "Диагностика: что подключено"},
        {"command": "status", "description": "Статус системы"},
        {"command": "strategy", "description": "Анализ + выбор стратегии"},
        {"command": "factory", "description": "Весь цикл: анализ→генерация→превью"},
        {"command": "create", "description": "Создать контент"},
        {"command": "publish", "description": "Опубликовать очередь"},
        {"command": "plan", "description": "Контент-план на неделю"},
        {"command": "trend", "description": "Тренды сейчас"},
        {"command": "pause", "description": "Пауза"},
        {"command": "resume", "description": "Возобновить"},
        {"command": "config", "description": "Настройки"},
    ]
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            # Снимаем webhook — иначе getUpdates (long-polling) вернёт 409 и бот «молчит».
            await c.post(_url("deleteWebhook"), json={"drop_pending_updates": False})
            await c.post(_url("setMyCommands"), json={"commands": cmds})
    except Exception:
        pass

async def _handle_command(chat_id: str, text: str):
    """Неубиваемая обёртка: любая ошибка команды уходит в чат, а не в тишину."""
    try:
        await _dispatch_command(chat_id, text)
    except Exception as e:
        import traceback
        traceback.print_exc()
        msg = str(e)
        if "All AI providers failed" in msg or "authentication" in msg.lower():
            hint = ("⚠️ Не задан ключ ИИ — анализ и генерация не работают.\n\n"
                    "Добавь хотя бы один (дешёвый) ключ в Render → Environment или в "
                    "Настройках сайта:\n"
                    "• <code>DEEPSEEK_API_KEY</code> (дёшево) или\n"
                    "• <code>GEMINI_API_KEY</code> (почти бесплатно)\n\n"
                    "Проверить что подключено: /diag")
        else:
            hint = f"⚠️ Ошибка команды: {type(e).__name__}: {msg[:200]}"
        try:
            await send_message(chat_id, hint)
        except Exception:
            pass


async def _dispatch_command(chat_id: str, text: str):
    from core.orchestrator import nexus_core
    from agents.reporter import reporter

    cmd = text.strip().split()[0].lower().replace("/", "")
    # убираем @botusername из команды (в группах Telegram добавляет его)
    cmd = cmd.split("@")[0]
    args = text.strip().split()[1:]

    if cmd in ("menu", "start"):
        await send_message(chat_id,
                           "🎛 <b>Пульт управления · NEXUS AI</b>\nВыбери действие:",
                           reply_markup=_main_menu_kb())
        return

    if cmd == "diag":
        def yn(v):
            return "✅" if v else "❌"
        ai_keys = {
            "Claude": os.getenv("ANTHROPIC_API_KEY"),
            "OpenAI": os.getenv("OPENAI_API_KEY"),
            "Gemini": os.getenv("GEMINI_API_KEY"),
            "DeepSeek": os.getenv("DEEPSEEK_API_KEY"),
        }
        any_ai = any(ai_keys.values())
        lines = [
            "🩺 <b>Диагностика</b>",
            f"{yn(os.getenv('TELEGRAM_BOT_TOKEN'))} Telegram-бот токен",
            f"{yn(os.getenv('TELEGRAM_CHAT_ID'))} Админ-чат",
            f"{yn(os.getenv('TELEGRAM_POST_CHAT_ID'))} Группа постов",
            f"{yn(os.getenv('AYRSHARE_API_KEY'))} Ayrshare (соцсети)",
            f"{yn(any_ai)} ИИ-ключ (" + ", ".join(k for k, v in ai_keys.items() if v) + ")" if any_ai
            else "❌ ИИ-ключ — НЕ задан ни один (анализ/генерация не будут работать)",
        ]
        await send_message(chat_id, "\n".join(lines))
        return

    if cmd == "strategy":
        await send_message(chat_id, "🧠 Анализирую свой аккаунт и тренды, готовлю варианты стратегии...")
        async with AsyncSessionLocal() as db:
            from core.strategy_advisor import build_options
            data = await build_options(db)
        analysis = data.get("analysis", [])
        options = data.get("options", [])
        lines = ["📊 <b>Анализ</b>"] + [f"• {a}" for a in analysis]
        lines += ["", "🎯 <b>Варианты стратегии</b>"]
        for i, o in enumerate(options):
            lines.append(f"\n<b>{i+1}. {o.get('title','')}</b>\n{o.get('desc','')}\n<i>{o.get('plan','')}</i>")
        kb = {"inline_keyboard": [[
            {"text": f"Взять вариант {i+1}", "callback_data": f"strat_{i}"}
        ] for i in range(len(options))]} if options else None
        await send_message(chat_id, "\n".join(lines), reply_markup=kb)
        return

    if cmd.startswith(("pub_", "fix_", "rej_", "see_")):
        action, pid = cmd.split("_", 1)
        from core import moderation
        if action == "pub":
            res = await moderation.approve(pid)
        elif action == "rej":
            res = await moderation.reject(pid)
        elif action == "see":
            await send_message(chat_id, "🔍 Смотрю визуал, секунду...")
            res = await moderation.analyze_media_for(pid)
        else:
            res = await moderation.request_fix(pid)
        await send_message(chat_id, res)
        return

    if cmd == "see":
        if not args:
            await send_message(chat_id, "❗ Дай ссылку на картинку/видео: /see https://...")
            return
        await send_message(chat_id, "🔍 Анализирую визуал, секунду...")
        from core.vision import analyze_media
        r = await analyze_media(args[0])
        await send_message(chat_id, ("🔍 <b>Разбор</b>\n\n" + r["analysis"]) if r.get("ok")
                           else f"⚠️ {r.get('error')}")
        return

    if cmd.startswith("strat_"):
        try:
            idx = int(cmd.split("_", 1)[1])
        except (ValueError, IndexError):
            await send_message(chat_id, "❌ Не понял выбор")
            return
        async with AsyncSessionLocal() as db:
            from core.strategy_advisor import choose_option
            chosen = await choose_option(db, idx)
        if chosen:
            await send_message(chat_id,
                               f"✅ Принята стратегия: <b>{chosen.get('title','')}</b>\n"
                               f"{chosen.get('plan','')}\n\nТеперь /create будет учитывать её.")
        else:
            await send_message(chat_id, "❌ Список вариантов устарел — запусти /strategy заново")
        return

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
                f"📂 Google Drive: {'✅' if p.google_drive_folder_id else '❌'}\n"
                f"📢 Группа постов: {'✅ ' + os.getenv('TELEGRAM_POST_CHAT_ID') if os.getenv('TELEGRAM_POST_CHAT_ID') else '❌ (постим в этот чат)'}"
            )
        else:
            msg = "⚙️ Профиль не настроен. Зайди в дашборд."
        await send_message(chat_id, msg)

    elif cmd in ("trend", "trends"):
        await send_message(chat_id, "📈 Анализирую тренды...")
        from core.scheduler import run_daily_trends
        asyncio.create_task(run_daily_trends())
        await send_message(chat_id, "✅ Анализ трендов запущен, отчёт придёт через минуту")

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
            "/menu     — пульт с кнопками",
            "/diag     — что подключено (диагностика)",
            "/status   — статус системы",
            "/strategy — анализ + выбор стратегии",
            "/see [url] — разбор картинки/ролика (зрение)",
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
            "/config   — настройки",
        ]
        await send_message(chat_id, "🤖 <b>Pakhon Studio · NEXUS AI</b>\n\n" + "\n".join(cmds))

async def _handle_plain_text(chat_id: str, text: str):
    """Обычное сообщение: если ждём правки к контенту — применяем их."""
    from core import moderation
    async with AsyncSessionLocal() as db:
        pid = await moderation.pending_fix_id(db)
    if not pid:
        return  # нечего править — игнорируем свободный текст
    await send_message(chat_id, "🔄 Применяю правки, секунду...")
    res = await moderation.apply_fix(text)
    if res:
        await send_message(chat_id, res)


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

                    # Нажатие инлайн-кнопки пульта
                    cb = upd.get("callback_query")
                    if cb:
                        cb_chat_id = str(cb.get("message", {}).get("chat", {}).get("id", ""))
                        data = cb.get("data", "")
                        if not chat_id or cb_chat_id == chat_id:
                            await _answer_callback(cb["id"])
                            asyncio.create_task(_handle_command(cb_chat_id, "/" + data))
                        continue

                    msg = upd.get("message", {})
                    text = msg.get("text", "")
                    upd_chat_id = str(msg.get("chat", {}).get("id", ""))
                    if not text or (chat_id and upd_chat_id != chat_id):
                        continue
                    if text.startswith("/"):
                        asyncio.create_task(_handle_command(upd_chat_id, text))
                    else:
                        # Обычный текст — возможно, это правки к контенту на согласовании.
                        asyncio.create_task(_handle_plain_text(upd_chat_id, text))
        except Exception:
            await asyncio.sleep(5)
        await asyncio.sleep(1)

def start_polling():
    """Start the Telegram polling loop as background task."""
    if os.getenv("TELEGRAM_BOT_TOKEN"):
        asyncio.create_task(setup_bot_commands())
    asyncio.create_task(poll_updates())
