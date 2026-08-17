"""
Telegram Bot command handler.
Runs as background webhook/polling alongside FastAPI.
Commands: /status /analyze /create /publish /plan /trends /pause /resume /report /config
"""
import os
import json
import asyncio
import contextvars

import httpx
from sqlalchemy import select
from database.db import AsyncSessionLocal
from database.models import Niche, ContentPlan, UserProfile

BOT_API = "https://api.telegram.org/bot{token}"
_offset = 0

# Внутри обработки команды ответы бота автоматически уходят в общую ленту —
# ту же, что видит сайт. Иначе на сайте видно «пользователь написал /publish»,
# но не видно, чем это кончилось.
_in_command = contextvars.ContextVar("tg_in_command", default=False)

def _url(method: str) -> str:
    return f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN', '')}/{method}"

async def send_message(chat_id: str, text: str, parse_mode: str = "HTML",
                       reply_markup: dict = None, feed: bool = False):
    """Отправка сообщения ботом.

    Длинный текст режется по лимиту Telegram: раньше сообщение свыше 4096
    символов просто не доходило, а ошибка глушилась — выглядело как молчание.
    """
    from publishers.telegram_pub import TEXT_LIMIT, fit

    # Пустой текст Telegram отвергает («message text is empty»), и для человека
    # это выглядит как молчание бота. Лучше честная строка, чем ничего.
    if not (text or "").strip():
        text = "🤔 Ответ получился пустым. Повторите запрос другими словами или /help."
    body, cut = fit(text, TEXT_LIMIT)
    try:
        payload = {
            "chat_id": chat_id, "text": body,
            "parse_mode": parse_mode, "disable_web_page_preview": True
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(_url("sendMessage"), json=payload)
            data = r.json()
        if not data.get("ok"):
            desc = str(data.get("description") or "")
            # Разметка ломается об один символ «<» в тексте модели. Раньше
            # сообщение в этом случае исчезало совсем; теперь отправляем как
            # обычный текст — лучше без форматирования, чем никак.
            if "parse" in desc.lower() and parse_mode:
                async with httpx.AsyncClient(timeout=10) as c:
                    await c.post(_url("sendMessage"),
                                 json={**payload, "parse_mode": None})
            else:
                print(f"[NEXUS] Telegram sendMessage: {desc[:150]}", flush=True)
    except Exception as e:
        print(f"[NEXUS] Telegram sendMessage: {type(e).__name__}: {str(e)[:120]}",
              flush=True)

    # Ответы бота должны быть видны на сайте: раньше в общую ленту попадала
    # только команда пользователя, а результат — нет.
    if feed or _in_command.get():
        try:
            from core.command_center import log_event
            await log_event("telegram", "agent", text)
        except Exception:
            pass
    if cut:
        return {"truncated": True}
    return {}


def _main_menu_kb() -> dict:
    """Главное меню. Восемь кнопок вместо россыпи: по ТЗ человек управляет
    результатом, а не выбирает, какую из четырнадцати команд нажать. Остальные
    команды продолжают работать текстом — просто не занимают экран."""
    return {"inline_keyboard": [
        [{"text": "✍️ СОЗДАТЬ", "callback_data": "create"}],
        [{"text": "📊 Статус", "callback_data": "status"},
         {"text": "📋 Контент", "callback_data": "queue"}],
        [{"text": "🧠 Стратегия", "callback_data": "strategy"},
         {"text": "📈 Тренды", "callback_data": "trend"}],
        [{"text": "📤 Публикация", "callback_data": "publish"},
         {"text": "⚙️ Настройки", "callback_data": "config"}],
    ]}


def _create_kb() -> dict:
    """Шаг 1 сценария CREATE: что именно создаём."""
    return {"inline_keyboard": [
        [{"text": "🎬 Видео", "callback_data": "mk_video"},
         {"text": "🖼 Изображение", "callback_data": "mk_image"}],
        [{"text": "📝 Пост", "callback_data": "mk_post"},
         {"text": "🎠 Карусель", "callback_data": "mk_carousel"}],
        [{"text": "📅 Контент-план", "callback_data": "mk_plan"}],
    ]}


def _platform_kb(kind: str) -> dict:
    """Шаг 2: для какой площадки."""
    return {"inline_keyboard": [
        [{"text": "Instagram", "callback_data": f"pf_{kind}_instagram"},
         {"text": "TikTok", "callback_data": f"pf_{kind}_tiktok"}],
        [{"text": "Telegram", "callback_data": f"pf_{kind}_telegram"},
         {"text": "YouTube", "callback_data": f"pf_{kind}_youtube"}],
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
        {"command": "tasks", "description": "Последние задачи и их статусы"},
        {"command": "cost", "description": "Расходы на AI и бюджет"},
        {"command": "queue", "description": "Очередь публикаций и повторы"},
        {"command": "channels", "description": "Каналы для публикации"},
        {"command": "approve", "description": "Подтвердить публикацию"},
        {"command": "errors", "description": "Что сломалось за сутки"},
        {"command": "rivals", "description": "Конкуренты: метрики и динамика"},
        {"command": "strategies", "description": "Стратегии: версии и результат"},
        {"command": "comments", "description": "Комментарии: подготовленные ответы"},
        {"command": "pc", "description": "Статус ПК (браузер-агент)"},
        {"command": "do", "description": "Выполнить задачу в браузере на ПК"},
        {"command": "status", "description": "Статус системы"},
        {"command": "strategy", "description": "Анализ + выбор стратегии"},
        {"command": "hunt", "description": "Топ залетевших в YouTube по нише"},
        {"command": "viral", "description": "Разбор чужих роликов → рецепт"},
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
    # Пишем в общую ленту — чтобы действия из Telegram были видны в дашборде.
    try:
        from core.command_center import log_event
        await log_event("telegram", "user", text)
    except Exception:
        pass
    token = _in_command.set(True)
    try:
        # Ответа ждёт человек в чате: не ответит ни одна своя модель — вопрос
        # уйдёт Клоду, а не потеряется.
        from core import ai_escrow
        ai_escrow.interactive(source="telegram", chat_id=chat_id)
        await _dispatch_command(chat_id, text)
    except Exception as e:
        import traceback
        traceback.print_exc()
        msg = str(e)
        ai_failed = ("Все ИИ-провайдеры отказали" in msg
                     or "Нет ни одного ключа ИИ" in msg
                     or "All AI providers failed" in msg)   # старый текст — на всякий случай
        if ai_failed or "authentication" in msg.lower():
            keys = {"ANTHROPIC": os.getenv("ANTHROPIC_API_KEY"),
                    "OPENAI": os.getenv("OPENAI_API_KEY"),
                    "GEMINI": os.getenv("GEMINI_API_KEY"),
                    "DEEPSEEK": os.getenv("DEEPSEEK_API_KEY")}
            present = [k for k, v in keys.items() if v]
            low = msg.lower()
            if "quota" in low or "429" in low or "resource_exhausted" in low:
                hint = ("⏳ <b>Лимит бесплатных запросов исчерпан</b> у всех подключённых ИИ.\n\n"
                        "Что делать:\n"
                        "• <b>Подождать</b> — квота Gemini обновляется каждые сутки\n"
                        "• <b>Добавить DeepSeek</b> — очень дёшево (центы за сотни запросов):\n"
                        "   platform.deepseek.com → API Keys → создать\n"
                        "   → в Render: <code>DEEPSEEK_API_KEY</code>\n"
                        "• Либо новый ключ Gemini на другом Google-аккаунте\n\n"
                        "Проверить: /diag")
            elif present:
                # Ключи ЕСТЬ — значит сам вызов упал. Показываем реальную причину.
                hint = ("⚠️ Ключи ИИ есть (" + ", ".join(present) + "), но вызов упал.\n"
                        "Причина: <code>" + msg[-350:] + "</code>\n\n"
                        "Обычно это неверный ключ или недоступная модель. Проверь /diag.")
            else:
                hint = ("⚠️ На сервере не найден ни один ключ ИИ.\n\n"
                        "Похоже, ключи сохранены не там. Добавь в <b>Render → Environment</b>:\n"
                        "• <code>GEMINI_API_KEY</code> (бесплатно) или\n"
                        "• <code>DEEPSEEK_API_KEY</code>\n\n"
                        "Проверить: /diag")
        else:
            hint = f"⚠️ Ошибка команды: {type(e).__name__}: {msg[:300]}"
        try:
            await send_message(chat_id, hint)
        except Exception:
            pass
    finally:
        _in_command.reset(token)


def _gemini_model_line() -> str:
    """Какая Gemini-модель реально доступна ключу (для /diag)."""
    try:
        from core.ai_router import resolve_gemini_model
        return resolve_gemini_model() or "— (ключ не задан или моделей нет)"
    except Exception as e:
        return f"ошибка: {str(e)[:60]}"


async def _refresh_env_from_db():
    """Подтягивает ключи из БД в окружение — чтобы сохранённое в дашборде
    работало сразу, без перезапуска сервера (процесс бота читал env на старте)."""
    try:
        # Тот же слой, что и на старте сервера: он расшифровывает значения,
        # иначе после включения шифрования бот подставлял бы шифротекст.
        from core.credentials import load_into_env
        await load_into_env()
    except Exception:
        pass


async def _dispatch_command(chat_id: str, text: str):
    from core.orchestrator import nexus_core
    from agents.reporter import reporter

    await _refresh_env_from_db()  # ключи из дашборда — сразу, без рестарта

    cmd = text.strip().split()[0].lower().replace("/", "")
    # убираем @botusername из команды (в группах Telegram добавляет его)
    cmd = cmd.split("@")[0]
    args = text.strip().split()[1:]

    if cmd in ("comments", "reply_all", "reply_discard"):
        from core.engagement import pending, approve_all, discard_pending, process_comments
        if cmd == "reply_all":
            res = await approve_all()
            msg = f"✅ Отправлено ответов: {res.get('sent', 0)} из {res.get('total', 0)}"
            if res.get("failed"):
                msg += "\n⚠️ Не ушли:\n" + "\n".join(res["failed"][:5])
            await send_message(chat_id, msg)
            return
        if cmd == "reply_discard":
            n = await discard_pending()
            await send_message(chat_id, f"🗑 Отклонено ответов: {n}")
            return

        items = await pending()
        if not items:
            await send_message(chat_id, "💬 Готовых ответов нет. Ищу новые комментарии...")
            res = await process_comments("instagram", limit=10)
            if not res.get("pending_approval"):
                await send_message(chat_id,
                    f"Новых комментариев для ответа нет "
                    f"(разобрано: {res.get('processed', 0)}, пропущено: {res.get('skipped', 0)}).")
            return

        lines = [f"💬 <b>Ответы на согласовании: {len(items)}</b>", ""]
        for i, p in enumerate(items[:8], 1):
            lines.append(f"<b>{i}. @{p['author']}</b> ({p.get('intent') or 'вопрос'})")
            lines.append(f"   «{p['text'][:120]}»")
            lines.append(f"   → {p['reply'][:200]}\n")
        lines.append("Отправить все: /reply_all · Отклонить: /reply_discard")
        await send_message(chat_id, "\n".join(lines)[:4000])
        return

    if cmd == "strategies":
        from core.strategy_store import effectiveness, current as cur_strategy
        cur = await cur_strategy()
        items = await effectiveness()
        lines = ["🧭 <b>Стратегии</b>", ""]
        if cur:
            lines.append(f"▶️ Действующая: <b>«{cur['title']}»</b> (v{cur['version']})")
            if cur.get("angle"):
                lines.append(f"   {cur['angle'][:200]}")
            lines.append("")
        if items:
            lines.append("<b>Результативность:</b>")
            for i in items[:6]:
                mark = "▶️" if i["status"] == "active" else ("📦" if i["status"] == "archived" else "📝")
                lines.append(f"{mark} «{i['title']}» v{i['version']} — "
                             f"{i['posts']} публикаций, ER {i['avg_engagement_rate']}%")
        else:
            lines.append("Пока нечего сравнивать. Запусти /strategy — агент предложит варианты.")
        await send_message(chat_id, "\n".join(lines)[:4000])
        return

    if cmd == "rivals":
        from core.research_store import tracked_competitors, track_competitor
        # /rivals instagram nike — добавить и сразу снять срез
        if len(args) >= 2:
            await send_message(chat_id, f"🔍 Снимаю метрики @{args[1]}...")
            res = await track_competitor(args[0], args[1])
            if res.get("ok"):
                await send_message(chat_id,
                    f"✅ <b>@{res['handle']}</b> [{res['platform']}]\n"
                    f"Подписчиков: {res['followers']}\n"
                    f"Постов: {res['posts_count']}\n"
                    f"Вовлечённость: {res['avg_engagement']}%")
            else:
                await send_message(chat_id, f"⚠️ {res.get('error', 'не удалось')}")
            return

        comps = await tracked_competitors()
        if not comps:
            await send_message(chat_id,
                "🔍 Конкуренты не отслеживаются.\n\n"
                "Добавить: <code>/rivals instagram nike</code>\n"
                "Площадки: instagram, youtube, tiktok")
            return
        lines = ["🔍 <b>Конкуренты</b>", ""]
        for c in comps:
            delta = ""
            if c.get("followers_delta"):
                sign = "+" if c["followers_delta"] > 0 else ""
                delta = f" ({sign}{c['followers_delta']})"
            lines.append(f"<b>@{c['handle']}</b> [{c['platform']}]\n"
                         f"  {c['followers']} подписчиков{delta} · "
                         f"ER {c['avg_engagement']}% · срезов: {c['snapshots']}")
        await send_message(chat_id, "\n".join(lines)[:4000])
        return

    if cmd == "cost":
        from core.cost_tracker import budget_status, by_model, by_agent
        st = await budget_status()
        bar = "🛑" if st["exceeded"] else ("⚠️" if st["alert"] else "✅")
        lines = [f"{bar} <b>Расходы на AI за сутки</b>",
                 f"Потрачено: <b>${st['cost_usd']:.4f}</b> из ${st['limit_usd']:.2f} ({st['used_pct']}%)",
                 f"Вызовов: {st['calls']} · токенов: {st['tokens']}"]
        models = await by_model(24, 5)
        if models:
            lines += ["", "<b>По моделям:</b>"]
            for m in models:
                lines.append(f"• {m['model']}: ${m['cost_usd']:.4f} ({m['calls']} выз.)")
        agents = await by_agent(24, 5)
        if agents:
            lines += ["", "<b>По агентам:</b>"]
            for a in agents:
                lines.append(f"• {a['agent']}: ${a['cost_usd']:.4f} ({a['calls']} выз.)")
        lines.append("\nЛимит меняется в дашборде → Расходы")
        await send_message(chat_id, "\n".join(lines)[:4000])
        return

    if cmd == "errors":
        # Всё сломанное за сутки в одном месте: провалы задач и ошибки моделей.
        from core.notify import recent_errors
        hours = 24
        if args and args[0].isdigit():
            hours = max(1, min(int(args[0]), 168))
        data = await recent_errors(hours)
        if not data["total"]:
            await send_message(chat_id, f"✅ За последние {hours} ч ошибок нет.")
            return
        lines = [f"🚨 <b>Ошибки за {hours} ч</b>", ""]
        if data["tasks"]:
            lines.append("<b>Задачи:</b>")
            for t in data["tasks"]:
                lines.append(f"❌ <code>{t['id']}</code> {t['kind']} — {t['goal']}")
                lines.append(f"   {t['error'][:120]}")
        if data["agents"]:
            lines += ["", "<b>Вызовы моделей:</b>"]
            for a in data["agents"]:
                lines.append(f"⚠️ {a['agent']} / {a['model'] or '—'}: {a['error'][:120]}")
        lines.append("\nДетали задачи: /task &lt;id&gt;")
        await send_message(chat_id, "\n".join(lines)[:4000])
        return

    if cmd == "channels":
        # Каналы для постинга — тот же список, что на сайте: система одна.
        from core import telegram_channels as tch
        arg = args[0].strip() if args else ""
        if arg:
            res = await tch.add_channel(arg)
            if res.get("ok"):
                ch = res["channel"]
                await send_message(chat_id, f"✅ Канал подключён: "
                                            f"<b>{ch['title'] or ch['chat_id']}</b> "
                                            f"{ch['username']}")
            else:
                await send_message(chat_id, f"⚠️ {res.get('error')}\n{res.get('hint') or ''}")
            return

        items = await tch.list_channels()
        if not items:
            await send_message(chat_id, "📭 Каналы не подключены.\n"
                                        "Добавьте бота администратором в канал и пришлите: "
                                        "/channels @имя_канала")
            return
        lines = ["📢 <b>Каналы для публикации</b>", ""]
        for c in items:
            star = "⭐️ " if c.get("default") else "• "
            lines.append(f"{star}{c.get('title') or c['chat_id']} "
                         f"{c.get('username') or c['chat_id']}")
        lines.append("\nДобавить: /channels &lt;@имя&gt;")
        await send_message(chat_id, "\n".join(lines)[:4000])
        return

    if cmd == "approve":
        # Подтверждение поста площадки, которая работает «с подтверждением».
        from core.publish_queue import pending as pending_pubs, approve as approve_pub
        arg = args[0].strip() if args else ""
        items = await pending_pubs()
        if not arg:
            if not items:
                await send_message(chat_id, "✅ Нечего подтверждать.")
                return
            lines = ["⏸ <b>Ждут подтверждения</b>", ""]
            for i in items[:10]:
                lines.append(f"<code>{i['id']}</code> {i['platform']}\n   {i['text'][:100]}")
            lines.append("\nОпубликовать: /approve &lt;id&gt;")
            await send_message(chat_id, "\n".join(lines)[:4000])
            return

        # Из списка удобно копировать начало id — принимаем и его.
        match = [i["id"] for i in items if i["id"] == arg or i["id"].startswith(arg)]
        if not match:
            await send_message(chat_id, f"⚠️ Публикация {arg} не ждёт подтверждения.")
            return
        res = await approve_pub(match[0])
        mark = "✅" if res.get("ok") else "⚠️"
        await send_message(chat_id, f"{mark} {res.get('error') or 'Опубликовано.'}")
        return

    if cmd == "queue":
        # Очередь публикаций: что ждёт своего часа, что упало и когда повтор.
        from core.publish_queue import queue as pub_queue, stats as pub_stats, retry_now
        arg = args[0].strip() if args else ""
        if arg:
            res = await retry_now(arg)
            mark = "✅" if res.get("ok") else "⚠️"
            await send_message(chat_id, f"{mark} Повтор {arg}: "
                                        f"{res.get('error') or res.get('status') or 'опубликовано'}")
            return

        st = await pub_stats()
        items = await pub_queue(limit=10)
        if not items:
            await send_message(chat_id, "📭 Очередь публикаций пуста.")
            return
        emoji = {"published": "✅", "scheduled": "🕓", "retrying": "🔁",
                 "failed": "❌", "blocked": "🚫", "cancelled": "⛔",
                 "pending_approval": "⏸"}
        lines = ["📤 <b>Очередь публикаций</b>",
                 " · ".join(f"{emoji.get(k, '•')} {k}: {v}" for k, v in st.items()), ""]
        for i in items:
            when = (i.get("next_retry_at") or i.get("scheduled_at") or "")[:16].replace("T", " ")
            lines.append(f"{emoji.get(i['status'], '•')} <code>{i['id'][:8]}</code> "
                         f"{i['platform']} · попыток {i['attempts']} · {when}")
            if i.get("error"):
                lines.append(f"   ⚠️ {i['error'][:90]}")
        lines.append("\nПовторить сейчас: /queue &lt;id&gt;")
        await send_message(chat_id, "\n".join(lines)[:4000])
        return

    if cmd == "tasks":
        from core.task_manager import list_tasks, STATUS_EMOJI
        tasks = await list_tasks(limit=10)
        if not tasks:
            await send_message(chat_id, "📭 Задач пока нет.")
            return
        lines = ["🗂 <b>Последние задачи</b>", ""]
        for t in tasks:
            em = STATUS_EMOJI.get(t["status"], "•")
            dur = f" · {t['duration_sec']:.0f}с" if t.get("duration_sec") else ""
            lines.append(f"{em} <code>{t['id']}</code> — {t['kind']}{dur}\n   {(t['goal'] or '')[:70]}")
            if t.get("error"):
                lines.append(f"   ⚠️ {t['error'][:90]}")
        lines.append("\nДетали: /task &lt;id&gt;")
        await send_message(chat_id, "\n".join(lines)[:4000])
        return

    if cmd == "task":
        if not args:
            await send_message(chat_id, "Укажи id: <code>/task TASK-2026-000001</code>")
            return
        from core.task_manager import get, STATUS_EMOJI
        t = await get(args[0].strip())
        if not t:
            await send_message(chat_id, "Задача не найдена.")
            return
        em = STATUS_EMOJI.get(t["status"], "•")
        lines = [f"{em} <b>{t['id']}</b> — {t['status']}",
                 f"Тип: {t['kind']} · источник: {t['source']}",
                 f"Цель: {(t['goal'] or '—')[:300]}",
                 f"Попыток: {t['attempts']} · время: {t['duration_sec']:.0f}с",
                 f"Расход: ${t['cost_usd']:.4f} · токенов: {t['tokens']}"]
        if t.get("agents"):
            lines.append("Агенты: " + ", ".join(t["agents"][:8]))
        if t.get("error"):
            lines.append(f"\n⚠️ <b>Ошибка:</b> <code>{t['error'][:400]}</code>")
        steps = t.get("steps") or []
        if steps:
            lines.append("\n<b>Шаги:</b>")
            for st in steps[-8:]:
                mark = "✓" if st.get("ok") else "✗"
                lines.append(f" {mark} {str(st.get('action'))[:70]}")
        await send_message(chat_id, "\n".join(lines)[:4000])
        return

    if cmd in ("menu", "start"):
        await send_message(chat_id,
                           "🎛 <b>Пульт управления · NEXUS AI</b>\nВыбери действие:",
                           reply_markup=_main_menu_kb())
        return

    if cmd == "auto":
        from core import autopilot as ap
        await send_message(chat_id, "🔍 <b>Шаг 1/4</b> — собираю полную картину аккаунта, топ-постов и трендов...")
        analysis = await ap.deep_analysis()
        acc = analysis.get("account") or {}
        accounts = acc.get("accounts") or {}
        top_total = sum(len((d.get("top_posts") or [])) for d in accounts.values() if isinstance(d, dict))
        summary = [f"📊 Ниша: {analysis.get('niche') or '—'}",
                   f"📈 Площадок проанализировано: {len(accounts)}",
                   f"🔥 Топ-роликов найдено: {top_total}"]
        if analysis.get("account_error"):
            summary.append(f"⚠️ Анализ: {analysis['account_error'][:80]}")
        await send_message(chat_id, "\n".join(summary))

        await send_message(chat_id, "🧠 <b>Шаг 2/4</b> — чего мне не хватает для полной картины...")
        questions = await ap.build_questions(analysis)
        await ap.set_state({"stage": "interview", "analysis": analysis,
                            "questions": questions, "answers": {}, "idx": 0})
        await send_message(chat_id,
            f"❓ <b>Вопрос 1 из {len(questions)}</b>\n\n{questions[0]}\n\n"
            "<i>Ответь обычным сообщением. Пропустить — напиши «-»</i>")
        return

    if cmd == "plan7":
        from core import autopilot as ap
        st = await ap.get_state()
        strat = st.get("chosen")
        if not strat:
            await send_message(chat_id, "❗ Сначала пройди /auto и выбери стратегию")
            return
        await send_message(chat_id, "🗓 Составляю план на 7 дней...")
        days = await ap.build_week_plan(strat, st.get("analysis", {}))
        if not days:
            await send_message(chat_id, "⚠️ Не удалось составить план, попробуй ещё раз")
            return
        icons = {"reels": "🎬", "post": "📝", "carousel": "🖼", "stories": "📱", "threads": "🧵"}
        lines = ["🗓 <b>План на неделю</b>", ""]
        for d in days:
            ic = icons.get(str(d.get("format", "")).lower(), "•")
            lines.append(f"{ic} <b>День {d.get('day')}</b> · {d.get('format')} · {d.get('best_time', '')}\n"
                         f"   {d.get('topic', '')}\n   <i>Хук: {d.get('hook', '')}</i>")
        st["week_plan"] = days
        await ap.set_state(st)
        await send_message(chat_id, "\n".join(lines)[:4000])
        return

    if cmd == "predict":
        from core import autopilot as ap
        st = await ap.get_state()
        idea = " ".join(args) or json.dumps(st.get("chosen", {}), ensure_ascii=False)
        if not idea.strip():
            await send_message(chat_id, "❗ Опиши идею ролика: /predict хук про ИИ-двойника")
            return
        await send_message(chat_id, "📈 Считаю шанс залёта...")
        p = await ap.predict_virality({"idea": idea}, st.get("analysis", {}))
        await send_message(chat_id, ap.format_prediction(p))
        return

    if cmd.startswith("strat2_"):
        from core import autopilot as ap
        try:
            idx = int(cmd.split("_", 1)[1])
        except (ValueError, IndexError):
            return
        st = await ap.get_state()
        opts = st.get("options", [])
        if idx >= len(opts):
            await send_message(chat_id, "❌ Список устарел — запусти /auto заново")
            return
        chosen = opts[idx]
        st["chosen"] = chosen
        st["stage"] = "ready"
        await ap.set_state(st)
        await send_message(chat_id,
            f"✅ Стратегия принята: <b>{chosen.get('title')}</b>\n{chosen.get('angle', '')}\n\n"
            f"💡 Первый рилс: {chosen.get('first_reel', '')}")
        # Сразу прогноз по первой идее
        p = await ap.predict_virality({"idea": chosen.get("first_reel", "")}, st.get("analysis", {}))
        await send_message(chat_id, ap.format_prediction(p), reply_markup={"inline_keyboard": [
            [{"text": "🎬 Создать этот рилс", "callback_data": "makereel"}],
            [{"text": "🗓 План на неделю", "callback_data": "plan7"}],
        ]})
        return

    if cmd == "makereel":
        from core import autopilot as ap
        st = await ap.get_state()
        idea = (st.get("chosen") or {}).get("first_reel", "")
        await send_message(chat_id, f"🎬 Запускаю фабрику: <i>{idea[:120]}</i>\nПришлю на согласование.")
        from core.content_factory import run_factory
        from core.task_manager import spawn
        await spawn("factory", f"Рилс: {idea or 'по стратегии'}",
                    lambda: run_factory(topic=idea or None, dry_run=False), source="telegram")
        return

    if cmd == "pc":
        from api.routes_desktop import desktop_connected
        if desktop_connected():
            await send_message(chat_id,
                "🖥 <b>ПК подключён</b> ✅\nБраузер под управлением агента.\n\n"
                "Дай задачу: <code>/do Открой instagram.com и посмотри уведомления</code>")
        else:
            await send_message(chat_id,
                "🖥 <b>ПК не подключён</b> ❌\n\n"
                "Как подключить:\n"
                "1. Скачай <code>start_agent.bat</code> из репозитория\n"
                "2. Дважды кликни по нему на своём ПК\n"
                "3. Откроется браузер — войди в нужные аккаунты\n"
                "4. Не закрывай окно\n\n"
                "Проверить снова: /pc")
        return

    if cmd == "do":
        from api.routes_desktop import desktop_connected
        if not desktop_connected():
            await send_message(chat_id, "❌ ПК не подключён. Запусти start_agent.bat — проверь через /pc")
            return
        task = " ".join(args)
        if not task:
            await send_message(chat_id, "❗ Что сделать? Напр.:\n<code>/do Открой olx.ua и найди цены на iPhone 15</code>")
            return
        await send_message(chat_id, f"🖥 Выполняю на твоём ПК: <i>{task[:100]}</i>\nЭто может занять пару минут...")
        from core.browser_agent import run_agent
        try:
            res = await run_agent(task=task, max_steps=25)
            status = res.get("status")
            if status == "done":
                await send_message(chat_id, f"✅ <b>Готово</b>\n{res.get('summary', '')[:1500]}")
            elif status == "needs_input":
                await send_message(chat_id, f"❓ Агент спрашивает:\n{res.get('question', '')[:800]}")
            else:
                await send_message(chat_id, f"⚠️ Статус: {status}\n{str(res.get('summary') or res.get('error'))[:500]}")
        except Exception as e:
            await send_message(chat_id, f"⚠️ Ошибка агента: {str(e)[:200]}")
        return

    if cmd == "music":
        from core import music_library as ml
        if not args:
            tracks = ml.list_tracks()
            if not tracks:
                await send_message(chat_id,
                    "🎵 <b>Библиотека музыки пуста</b>\n\n"
                    "Добавь трек прямой ссылкой на mp3:\n"
                    "<code>/music https://...mp3 energetic</code>\n\n"
                    "Настроения: energetic / calm / fun / dramatic\n"
                    "Бесплатные треки: Pixabay Music, YouTube Audio Library, FMA")
                return
            lines = [f"🎵 <b>Треков: {len(tracks)}</b>"] + [f"• {t['file']} — {t['mood']}" for t in tracks[:20]]
            await send_message(chat_id, "\n".join(lines))
            return
        url = args[0]
        mood = args[1] if len(args) > 1 else "universal"
        await send_message(chat_id, "⬇️ Скачиваю трек...")
        r = await ml.add_track_from_url(url, mood)
        if r.get("ok"):
            await send_message(chat_id, f"✅ Добавлен: {r['file']} ({r['mood']}). Всего треков: {r['total']}")
        else:
            await send_message(chat_id, f"⚠️ Не скачался: {r.get('error')}")
        return

    if cmd == "montage":
        # Формат: /montage url1 url2 ... [| текст титров для караоке]
        raw = text.split(" ", 1)[1] if " " in text else ""
        script = None
        if "|" in raw:
            raw, script = raw.split("|", 1)
            script = script.strip() or None
        urls = [u for u in raw.split() if u.startswith("http")]
        if len(urls) < 2:
            await send_message(chat_id,
                "❗ Дай 2+ ссылки на клипы. Титры — после | :\n"
                "/montage https://...mp4 https://...mp4 | Слева я. Справа ИИ-я. Работаем вместе")
            return
        await send_message(chat_id, f"🎬 Собираю ролик из {len(urls)} сцен"
                           + (" + титры" if script else "") + " + музыка... минуту.")
        from core.montage import assemble_and_send
        res = await assemble_and_send(urls, chat_id, caption="🎬 Готовый ролик", script=script)
        if res.get("ok") and res.get("sent"):
            return  # видео уже отправлено
        if res.get("ok"):
            await send_message(chat_id, f"✅ Ролик собран ({res.get('clips')} сцен), но не отправился: {res.get('send_error', 'неизвестно')}")
        else:
            await send_message(chat_id, f"⚠️ Монтаж не удался: {res.get('error')}")
        return

    if cmd == "diag":
        # Первым делом — главный вопрос: сможем ли мы сейчас создать контент.
        from core import preflight
        await send_message(chat_id, preflight.as_text(await preflight.check("video")))

        def yn(v):
            return "✅" if v else "❌"
        ai_keys = {
            "Claude": os.getenv("ANTHROPIC_API_KEY"),
            "OpenAI": os.getenv("OPENAI_API_KEY"),
            "Gemini": os.getenv("GEMINI_API_KEY"),
            "DeepSeek": os.getenv("DEEPSEEK_API_KEY"),
        }
        any_ai = any(ai_keys.values())
        # Режим работы важнее списка галочек: без ИИ система не «сломана»,
        # она работает как пульт — публикация, очередь и отчёты на месте.
        from core.ai_router import available_providers
        providers = available_providers()
        mode = (f"✅ Режим: полный (ИИ: {', '.join(providers)})" if providers
                else "⚙️ Режим: только управление — ИИ не подключён.\n"
                     "Работают: /queue /tasks /errors /cost /rivals, публикация и отчёты.\n"
                     "Генерация текста и видео недоступна.")
        lines = [
            "🩺 <b>Диагностика</b>",
            mode,
            "",
            f"{yn(os.getenv('TELEGRAM_BOT_TOKEN'))} Telegram-бот токен",
            f"{yn(os.getenv('TELEGRAM_CHAT_ID'))} Админ-чат",
            f"{yn(os.getenv('TELEGRAM_POST_CHAT_ID'))} Группа постов",
            f"{yn(os.getenv('INSTAGRAM_ACCESS_TOKEN'))} Instagram API",
            f"{yn(os.getenv('TIKTOK_ACCESS_TOKEN'))} TikTok API",
            f"{yn(os.getenv('IG_HANDLE') or os.getenv('TIKTOK_HANDLE') or os.getenv('YOUTUBE_HANDLE'))} Ники для анализа",
        ]
        await send_message(chat_id, "\n".join(lines) + "\n\n⏳ Проверяю ключи ИИ вживую...")

        # Реальная проверка: ключ может быть задан, но невалиден/без квоты.
        checks = []
        if key := os.getenv("GEMINI_API_KEY"):
            try:
                async with httpx.AsyncClient(timeout=15) as c:
                    r = await c.get("https://generativelanguage.googleapis.com/v1beta/models",
                                    params={"key": key})
                d = r.json()
                if r.status_code == 200:
                    from core.ai_router import resolve_gemini_model
                    checks.append(f"✅ Gemini — рабочий (модель: {resolve_gemini_model() or '—'})")
                else:
                    checks.append(f"❌ Gemini — {d.get('error', {}).get('message', 'ошибка')[:90]}")
            except Exception as e:
                checks.append(f"❌ Gemini — {str(e)[:80]}")
        else:
            checks.append("⬜ Gemini — не задан")

        if key := os.getenv("OPENAI_API_KEY"):
            try:
                import openai
                cl = openai.AsyncOpenAI(api_key=key)
                await cl.models.list()
                checks.append("✅ OpenAI — рабочий")
            except Exception as e:
                msg = str(e)
                short = "квота исчерпана" if "insufficient_quota" in msg else msg[:80]
                checks.append(f"❌ OpenAI — {short}")
        else:
            checks.append("⬜ OpenAI — не задан")

        for name, env in (("Claude", "ANTHROPIC_API_KEY"), ("DeepSeek", "DEEPSEEK_API_KEY")):
            checks.append(f"{'✅' if os.getenv(env) else '⬜'} {name} — "
                          f"{'задан' if os.getenv(env) else 'не задан'}")

        verdict = ("\n\n<b>Итог:</b> " +
                   ("система готова ✅" if any("✅" in c for c in checks)
                    else "рабочих ИИ-ключей нет — анализ и генерация не запустятся ❌"))
        await send_message(chat_id, "🧠 <b>Ключи ИИ (живая проверка)</b>\n" + "\n".join(checks) + verdict)
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

    if cmd == "viral":
        if not args:
            await send_message(chat_id, "❗ Дай 1-5 ссылок на залетевшие ролики (YT/TikTok/IG):\n/viral https://... https://...")
            return
        await send_message(chat_id, "🕵️ Разбираю референсы (метрики + смотрю кадры)... это займёт минуту.")
        from core.viral_research import research
        niche = ""
        async with AsyncSessionLocal() as db:
            nr = await db.execute(select(Niche).where(Niche.status == "active").limit(1))
            n = nr.scalar_one_or_none()
            niche = n.name if n else ""
        rec = await research(args, niche)
        lines = ["🧬 <b>Рецепт вируса</b> (сохранён, учту в генерации)", ""]
        if rec.get("why_viral"):
            lines += ["<b>Почему заходят:</b>"] + [f"• {x}" for x in rec["why_viral"][:5]]
        if rec.get("hook_patterns"):
            lines += ["", "<b>Хуки:</b>"] + [f"• {x}" for x in rec["hook_patterns"][:5]]
        if rec.get("structure"):
            lines += ["", f"<b>Структура:</b> {rec['structure']}"]
        if rec.get("recipe"):
            lines += ["", f"<b>Как собрать наш:</b> {rec['recipe']}"]
        await send_message(chat_id, "\n".join(lines)[:4000])
        return

    if cmd == "hunt":
        query = " ".join(args)
        if not query:
            async with AsyncSessionLocal() as db:
                nr = await db.execute(select(Niche).where(Niche.status == "active").limit(1))
                n = nr.scalar_one_or_none()
                query = n.name if n else ""
        if not query:
            await send_message(chat_id, "❗ Укажи нишу: /hunt смм для кофейни")
            return
        await send_message(chat_id, f"🔎 Ищу топ YouTube по «{query}»...")
        from core.viral_research import youtube_search
        tops = await youtube_search(query, 8)
        if not tops:
            await send_message(chat_id, "❌ Ничего не нашёл (или yt-dlp недоступен)")
            return
        lines = [f"🔥 <b>Топ по «{query}»</b> (по просмотрам)", ""]
        for m in tops[:8]:
            v = m.get("views")
            lines.append(f"• {(m.get('title') or '')[:60]} — {v:,} просм." if v else f"• {(m.get('title') or '')[:60]}")
        lines += ["", "Скинь лучшие ссылки в /viral — соберу рецепт."]
        await send_message(chat_id, "\n".join(lines)[:4000])
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
        # Про временное хранилище говорим в каждом отчёте: это единственная
        # поломка, которая тихо стирает всё остальное.
        from database.db import storage_info
        st = storage_info()
        if not st["persistent"]:
            report += f"\n\n⚠️ <b>Данные временные.</b> {st['warning']}"
        await send_message(chat_id, report)

    elif cmd == "analyze":
        query = " ".join(args).strip()
        if not query:
            await send_message(chat_id, "❗ Укажи нишу: /analyze кофейня")
            return
        await send_message(chat_id, f"🔍 Запускаю анализ: <b>{query}</b>…")
        async with AsyncSessionLocal() as db:
            # Ищем по всей строке, а если не нашли — по первому слову: раньше
            # «/analyze кофейня Алматы» искалось целиком вместе с городом и
            # почти всегда давало «ниша не найдена».
            result = await db.execute(
                select(Niche).where(Niche.name.ilike(f"%{query}%")).limit(1))
            niche = result.scalar_one_or_none()
            if not niche and len(args) > 1:
                result = await db.execute(
                    select(Niche).where(Niche.name.ilike(f"%{args[0]}%")).limit(1))
                niche = result.scalar_one_or_none()
            if niche:
                from core.task_manager import spawn
                await spawn("pipeline", f"Полный цикл по нише «{niche.name}»",
                            lambda nid=niche.id: nexus_core.run_full_pipeline(nid),
                            source="telegram", ref_id=niche.id)
                await send_message(chat_id, f"✅ Анализ запущен для ниши <b>{niche.name}</b>")
            else:
                r_all = await db.execute(select(Niche).where(Niche.status == "active").limit(10))
                names = [n.name for n in r_all.scalars()]
                have = ("\n\nЕсть такие: " + ", ".join(names)) if names else \
                    "\n\nНи одной ниши пока не заведено — создайте её в дашборде."
                await send_message(chat_id, f"❌ Ниша «{query}» не найдена.{have}")

    elif cmd == "create" and not args:
        # Главная команда системы: человек говорит, ЧТО он хочет, остальное
        # решает система. Раньше «Создать» сразу лезло в контент-план и упиралось
        # в «запусти /analyze».
        await send_message(chat_id, "✍️ <b>Что создать?</b>", reply_markup=_create_kb())

    elif cmd.startswith("mk_"):
        kind = cmd[3:]
        if kind == "plan":
            await _dispatch_command(chat_id, "/plan7")
            return
        await send_message(chat_id, "📱 <b>Для какой площадки?</b>",
                           reply_markup=_platform_kb(kind))

    elif cmd.startswith("pf_"):
        # pf_<вид>_<площадка> — вид и площадка выбраны, осталась тема.
        parts = cmd.split("_")
        kind, platform = (parts + ["video", "instagram"])[1:3]
        from core import dialog
        await dialog.expect(chat_id, dialog.AWAIT_TOPIC,
                            {"kind": kind, "platform": platform})
        titles = {"video": "ролика", "image": "изображения", "post": "поста",
                  "carousel": "карусели"}
        await send_message(chat_id,
                           f"🎯 <b>О чём {titles.get(kind, 'контент')}?</b>\n"
                           f"Напишите тему одной строкой — или ответьте "
                           f"«по трендам», и я выберу сам.")

    elif cmd == "create":
        await send_message(chat_id, "✍️ Создаю контент...")
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ContentPlan).where(ContentPlan.status == "pending").limit(3)
            )
            plans = result.scalars().all()
            if not plans:
                # Пустой контент-план — не повод отказывать: конвейер умеет
                # придумать тему сам. Раньше здесь был тупик «запусти /analyze».
                await send_message(chat_id,
                                   "📋 Запланированных постов нет — запускаю фабрику: "
                                   "тема, сценарий, кадры, монтаж.")
                await _dispatch_command(chat_id, "/factory " + " ".join(args))
                return
            for plan in plans:
                from core.task_manager import spawn
                await spawn("generate", "Генерация контента",
                            lambda pid=plan.id: nexus_core.generate_content_for_plan(pid),
                            source="telegram", ref_id=plan.id)
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

    elif cmd in ("trend", "trends"):
        await send_message(chat_id, "📈 Анализирую тренды...")
        from core.scheduler import run_daily_trends
        from core.task_manager import spawn
        await spawn("trends", "Анализ трендов", lambda: run_daily_trends(), source="telegram")
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
        from core.task_manager import spawn
        await spawn("generate", "Генерация контента по id",
                    lambda pid=args[0]: nexus_core.generate_content_for_plan(pid),
                    source="telegram", ref_id=args[0])
        await send_message(chat_id, f"⚙️ Генерация запущена для {args[0][:8]}...")

    elif cmd in ("factory", "reel", "create_reel"):
        # Полный цикл: анализ → генерация → монтаж → согласование в Telegram.
        # Раньше без аргументов запускался dry-run: конвейер отрабатывал, но шаг
        # согласования пропускался, и ролик не приходил никуда — выглядело как
        # «ничего не создалось».
        from core.content_factory import run_factory
        from core import dialog

        rest = list(args)
        preview = bool(rest) and rest[-1].lower() in ("превью", "preview", "dry")
        if preview:
            rest = rest[:-1]
        if rest and rest[-1].lower() in ("post", "publish", "go"):
            rest = rest[:-1]
        topic = " ".join(rest).strip() or None
        auto = topic and topic.lower() in ("авто", "auto")
        if auto:
            topic = None

        if not topic and not preview and not auto:
            # Один вопрос вместо рассказа о том, как всё будет сделано.
            await dialog.expect(chat_id, dialog.AWAIT_TOPIC)
            await send_message(chat_id,
                               "🎬 Делаю ролик. <b>Какая тема?</b>\n"
                               "Напишите тему одной строкой — или ответьте "
                               "«по трендам», и я выберу сам.")
            return

        from core.task_manager import spawn
        from core import task_feed
        goal = f"Фабрика: {topic or 'тема по трендам'}"
        task_id = await spawn("factory", goal,
                              lambda: run_factory(topic=topic, dry_run=preview),
                              source="telegram")
        # Одно живое сообщение вместо тишины на минуты: шаги дописываются в него.
        await task_feed.start(task_id, chat_id, goal)

    elif cmd.startswith("set_goal"):
        # Раньше команда рапортовала об установке цели, ничего не сохраняя.
        goal_text = " ".join(args).strip()
        if not goal_text:
            await send_message(chat_id, "❗ Укажи цель: /set_goal 100000 подписчиков")
        else:
            from core.agent_profile import get as get_profile, save as save_profile
            current = (await get_profile()).get("goals") or ""
            merged = f"{current}\n{goal_text}".strip() if current else goal_text
            await save_profile({"goals": merged})
            await send_message(chat_id,
                               f"🎯 Цель сохранена в профиле агента:\n<b>{goal_text}</b>\n\n"
                               f"Она уходит в каждый запрос к модели.")

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
            "/hunt [ниша] — топ залетевших в YouTube",
            "/viral [ссылки] — разобрать чужие ролики → рецепт",
            "/see [url] — разбор картинки/ролика (зрение)",
            "/montage [ссылки] — склеить клипы в один ролик",
            "/music [url] [настроение] — добавить трек",
            "/pc       — статус подключённого ПК",
            "/do [задача] — выполнить в браузере на ПК",
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

async def _handle_media(chat_id: str, msg: dict):
    """Голос → расшифровка → обычная обработка. Медиа → сохранение + разбор зрением."""
    from core import tg_input
    try:
        res = await tg_input.handle_media(msg)
    except Exception as e:
        await send_message(chat_id, f"⚠️ Не смог обработать вложение: {str(e)[:150]}")
        return

    kind = res.get("kind")
    if not kind:
        return

    if kind == "voice":
        text = res.get("text", "").strip()
        if not text:
            await send_message(chat_id, "🎤 Не разобрал речь. Нужен GEMINI_API_KEY или OPENAI_API_KEY.")
            return
        await send_message(chat_id, f"🎤 <i>Услышал:</i> {text[:300]}")
        # Речь может быть командой («статус», «сделай рилс») или ответом в интервью.
        low = text.lower()
        cmd_map = {"статус": "/status", "меню": "/menu", "стратег": "/strategy",
                   "автопилот": "/auto", "план": "/plan7", "тренд": "/trend",
                   "публик": "/publish", "фабрик": "/factory"}
        for word, cmd in cmd_map.items():
            if low.startswith(word):
                await _handle_command(chat_id, cmd)
                return
        await _handle_plain_text(chat_id, text)
        return

    if kind == "audio":
        await send_message(chat_id, f"🎵 Трек сохранён в библиотеку музыки.\n"
                                    f"Проверить: /music")
        return

    if kind == "font":
        await send_message(chat_id, f"🔤 Шрифт сохранён: {res.get('name', '')}\n"
                                    "Буду использовать в титрах.")
        return

    # Фото или видео — сразу разбираем зрением
    path = res.get("path")
    await send_message(chat_id, "🔍 Смотрю, что на этом... секунду.")
    try:
        from core.vision import analyze_image, analyze_video
        fn = analyze_video if kind == "video" else analyze_image
        r = await fn(path)
        if r.get("ok"):
            await send_message(chat_id, "🔍 <b>Разбор</b>\n\n" + r["analysis"][:3000])
        else:
            await send_message(chat_id, f"💾 Сохранил как референс.\n⚠️ Разбор не вышел: {r.get('error')}")
    except Exception as e:
        await send_message(chat_id, f"💾 Сохранил как референс. Разбор не удался: {str(e)[:120]}")


async def _start_creation(chat_id: str, kind: str, platform: str, topic: str):
    """Запускает создание выбранного вида контента и показывает живой статус.

    Один вход для всех форматов: человек выбрал «что» и «где», тему назвал —
    дальше система сама решает, чем и как это делать.
    """
    from core.content_factory import run_factory
    from core.task_manager import spawn
    from core import task_feed, preflight

    # Сначала — сможем ли мы это сделать. «Запускаю» при пустых ключах означало
    # тишину на месте результата: человек ждал ролик, которого не будет.
    gate = await preflight.check(kind)
    if not gate["ok"]:
        await send_message(chat_id, preflight.as_text(gate))
        return
    if gate["warnings"]:
        await send_message(chat_id, preflight.as_text({"warnings": gate["warnings"]}))

    real_topic = None if topic.lower() in ("авто", "auto", "") else topic
    platforms = [platform] if platform else None
    want_video = kind == "video"
    content_type = {"video": "auto", "image": "photo", "post": "post",
                    "carousel": "carousel"}.get(kind, "auto")

    titles = {"video": "Ролик", "image": "Изображение", "post": "Пост",
              "carousel": "Карусель"}
    goal = f"{titles.get(kind, 'Контент')}: {real_topic or 'тема по трендам'}"

    await send_message(chat_id,
                       f"🎬 <b>План готов</b>\n"
                       f"{titles.get(kind, 'Контент')} · {platform or 'все площадки'} · "
                       f"{real_topic or 'тема по трендам'}\n"
                       f"Запускаю. Готовое пришлю на согласование.")

    task_id = await spawn(kind if kind != "video" else "factory", goal,
                          lambda: run_factory(topic=real_topic, platforms=platforms,
                                              dry_run=False, want_video=want_video,
                                              content_type=content_type),
                          source="telegram")
    await task_feed.start(task_id, chat_id, goal, kind=kind)


async def _handle_plain_text(chat_id: str, text: str):
    """Неубиваемая обёртка: ошибка разбора текста уходит в чат, а не в тишину.

    Обработчик запускается фоновой задачей, и раньше исключение в ней просто
    гасло: человек писал сообщение и не получал вообще ничего.
    """
    try:
        from core import ai_escrow
        ai_escrow.interactive(source="telegram", chat_id=chat_id)
        await _plain_text(chat_id, text)
    except Exception as e:
        import traceback
        traceback.print_exc()
        await send_message(chat_id, f"⚠️ Не смог обработать сообщение: {str(e)[:200]}\n"
                                    f"Попробуйте иначе или /help.")


async def _plain_text(chat_id: str, text: str):
    """Обычное сообщение: ответ на вопрос автопилота или правки к контенту."""
    from core import autopilot as ap

    # 1) Идёт интервью автопилота — записываем ответ и задаём следующий вопрос.
    st = await ap.get_state()
    if st.get("stage") == "interview":
        qs = st.get("questions", [])
        i = st.get("idx", 0)
        if i < len(qs):
            st.setdefault("answers", {})[qs[i]] = text.strip()
            i += 1
            st["idx"] = i
        if i < len(qs):
            await ap.set_state(st)
            await send_message(chat_id, f"❓ <b>Вопрос {i+1} из {len(qs)}</b>\n\n{qs[i]}")
            return
        # Вопросы кончились → строим стратегии
        st["stage"] = "strategies"
        await ap.set_state(st)
        await send_message(chat_id, "🎯 <b>Шаг 3/4</b> — собираю варианты стратегии на основе всего...")
        opts = await ap.build_strategies(st.get("analysis", {}), st.get("answers", {}))
        if not opts:
            await send_message(chat_id, "⚠️ Не удалось собрать стратегии — попробуй /auto ещё раз")
            return
        st["options"] = opts
        await ap.set_state(st)
        lines = ["🎯 <b>Варианты стратегии</b>", ""]
        for n, o in enumerate(opts):
            lines.append(f"<b>{n+1}. {o.get('title','')}</b>\n{o.get('angle','')}\n"
                         f"<i>Почему: {o.get('why','')}</i>\n💡 Первый рилс: {o.get('first_reel','')}\n")
        kb = {"inline_keyboard": [[{"text": f"Взять «{o.get('title','')[:20]}»",
                                    "callback_data": f"strat2_{n}"}] for n, o in enumerate(opts)]}
        await send_message(chat_id, "\n".join(lines)[:4000], reply_markup=kb)
        return

    from core import dialog
    await dialog.remember(chat_id, "user", text)

    # 1б) Ждём тему ролика — следующее сообщение и есть тема. Без этого «ИИ ролик»
    # → «какая тема?» → ответ уходил в общий разбор и терялся.
    if await dialog.awaiting(chat_id) == dialog.AWAIT_TOPIC:
        ctx = await dialog.pending(chat_id)
        await dialog.expect(chat_id, "")
        # «авто» — служебное слово: тему выберет сам конвейер, спрашивать
        # второй раз нельзя, иначе разговор зациклится.
        topic = "авто" if text.strip().lower() in (
            "сам", "сама", "сам придумай", "по трендам", "любая", "на твой выбор",
            "не знаю", "давай", "напиши", "1") else text.strip()
        if ctx.get("kind"):
            await _start_creation(chat_id, ctx["kind"], ctx.get("platform", ""), topic)
        else:
            await _handle_command(chat_id, f"/factory {topic}")
        return

    # 2) Правки к контенту на согласовании.
    from core import moderation
    async with AsyncSessionLocal() as db:
        pid = await moderation.pending_fix_id(db)
    if not pid:
        # 3) Свободный текст: понимаем намерение и выполняем нужное действие.
        from core import intent
        hist = await dialog.history(chat_id)
        cmd = await intent.route(text, hist)
        if cmd and cmd != "/chat":
            await send_message(chat_id, f"🤖 Понял: <code>{cmd[:80]}</code>")
            await _handle_command(chat_id, cmd)
            return
        reply = await intent.chat_reply(text, hist)
        await dialog.remember(chat_id, "agent", reply)
        await send_message(chat_id, reply)
        try:
            from core.command_center import log_event
            await log_event("telegram", "user", text)
            await log_event("telegram", "agent", reply)
        except Exception:
            pass
        return
    await send_message(chat_id, "🔄 Применяю правки, секунду...")
    res = await moderation.apply_fix(text)
    if res:
        await send_message(chat_id, res)


async def poll_updates():
    """Цикл получения сообщений (long-polling).

    Три вещи, которых здесь раньше не было и из-за которых бот «молчал»:
      * токен перечитывается на каждом круге — подключённый через веб бот
        оживает сразу, а не после перезапуска сервера;
      * ответ Telegram проверяется: 409 (запущен второй экземпляр) и 401
        (неверный токен) больше не выглядят как «сообщений нет»;
      * команды исполняются только от владельца — см. core/telegram_owner.
    """
    global _offset
    from core import telegram_owner as owner_mod

    last_complaint = ""
    while True:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            # Токена ещё нет — ждём, пока его подключат в панели.
            await asyncio.sleep(10)
            continue
        try:
            async with httpx.AsyncClient(timeout=35) as c:
                r = await c.get(_url("getUpdates"),
                                params={"offset": _offset, "timeout": 30})
                data = r.json()

            if not data.get("ok"):
                desc = str(data.get("description") or "Telegram отказал")
                code = data.get("error_code")
                # Жалуемся один раз на причину, а не на каждом круге:
                # иначе лог забивается одинаковыми строками раз в секунду.
                if desc != last_complaint:
                    print(f"[NEXUS] Telegram getUpdates: {code} {desc}", flush=True)
                    last_complaint = desc
                if code == 401:
                    # Неверный токен: ждать бессмысленно, пока его не заменят.
                    await asyncio.sleep(60)
                elif code == 409:
                    # Работает второй экземпляр бота (или включён webhook).
                    await asyncio.sleep(15)
                else:
                    await asyncio.sleep(5)
                continue
            last_complaint = ""

            for upd in data.get("result", []):
                _offset = upd["update_id"] + 1

                # Каналы, которые видит бот, запоминаем: мастеру подключения
                # нельзя дёргать getUpdates самому — он отберёт соединение у
                # этого цикла и получит 409.
                try:
                    from core.telegram_channels import remember_chat
                    for key in ("channel_post", "edited_channel_post", "my_chat_member",
                                "message"):
                        chat = ((upd.get(key) or {}).get("chat")) or {}
                        if chat.get("type") in ("channel", "supergroup", "group"):
                            remember_chat(chat)
                except Exception:
                    pass

                # Нажатие инлайн-кнопки пульта
                cb = upd.get("callback_query")
                if cb:
                    cb_chat_id = str(cb.get("message", {}).get("chat", {}).get("id", ""))
                    from_id = str((cb.get("from") or {}).get("id", ""))
                    data_cb = cb.get("data", "")
                    if await owner_mod.allowed(from_id, cb_chat_id):
                        await _answer_callback(cb["id"])
                        asyncio.create_task(_handle_command(cb_chat_id, "/" + data_cb))
                    else:
                        await _answer_callback(cb["id"], "Доступ только у владельца")
                    continue

                msg = upd.get("message", {})
                text = msg.get("text", "")
                upd_chat_id = str(msg.get("chat", {}).get("id", ""))
                from_id = str((msg.get("from") or {}).get("id", ""))

                if not await owner_mod.allowed(from_id, upd_chat_id):
                    # Первый написавший /start становится владельцем — иначе
                    # бота пришлось бы настраивать вручную, а до тех пор он
                    # слушался бы кого угодно.
                    if text.startswith("/start") and await owner_mod.claim(from_id):
                        await send_message(upd_chat_id, owner_mod.CLAIMED)
                        asyncio.create_task(_handle_command(upd_chat_id, "/menu"))
                    elif text.startswith("/"):
                        await send_message(upd_chat_id, owner_mod.DENIED)
                    continue

                # Голос / фото / видео / документ — обрабатываем отдельно.
                if not text and any(k in msg for k in
                                    ("voice", "audio", "photo", "video", "document")):
                    asyncio.create_task(_handle_media(upd_chat_id, msg))
                    continue
                if not text:
                    continue
                if text.startswith("/"):
                    asyncio.create_task(_handle_command(upd_chat_id, text))
                else:
                    # Обычный текст — возможно, это правки к контенту на согласовании.
                    asyncio.create_task(_handle_plain_text(upd_chat_id, text))
        except Exception as e:
            print(f"[NEXUS] Telegram polling: {type(e).__name__}: {str(e)[:150]}", flush=True)
            await asyncio.sleep(5)
        await asyncio.sleep(1)

def start_polling():
    """Запускает цикл бота фоном. Токен на этот момент может быть ещё не задан —
    цикл дождётся его сам."""
    if os.getenv("TELEGRAM_BOT_TOKEN"):
        asyncio.create_task(setup_bot_commands())
    asyncio.create_task(poll_updates())
