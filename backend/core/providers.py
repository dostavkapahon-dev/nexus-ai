"""
Реестр провайдеров: кто есть, что умеет и что из этого доказано.

Требование, из-за которого он появился (ТЗ §36–§40): в одном месте видеть все
внешние сервисы и их настоящее состояние. До сих пор ответ собирался по
кусочкам — ключи в одном месте, Higgsfield в другом, площадки в третьем, — и
каждый кусок отвечал на свой вопрос, а на главный («получится ли сейчас
сделать контент») не отвечал никто.

Четыре состояния и они НЕ синонимы (§37):

  ``not_configured`` — нет ключа или доступа, сервис даже не пробовали;
  ``authenticated``  — доступ есть, но настоящей работы ещё не было;
  ``ready``          — есть подтверждённый результат настоящей работы;
  ``error``          — последняя настоящая попытка провалилась, причина есть.

«Ключ задан» само по себе даёт только `authenticated`. Зелёное берётся из
реестра возможностей и реестра моделей — там оно появляется лишь после
настоящего результата.
"""
import os

NOT_CONFIGURED, AUTHENTICATED, READY, ERROR = (
    "not_configured", "authenticated", "ready", "error")

ICONS = {NOT_CONFIGURED: "⚪", AUTHENTICATED: "🟡", READY: "🟢", ERROR: "🔴"}
WORDS = {NOT_CONFIGURED: "не подключён", AUTHENTICATED: "подключён, не проверен",
         READY: "работает", ERROR: "ошибка"}

# Что именно провайдер делает для нас. Возможность связывает провайдера с
# реестром возможностей: по ней и берётся доказательство.
PROVIDERS = (
    {"id": "telegram", "name": "Telegram", "cap": "publish_telegram",
     "env": ("TELEGRAM_BOT_TOKEN",), "does": "доставка и управление"},
    {"id": "higgsfield", "name": "Higgsfield", "cap": "image",
     "env": ("HIGGSFIELD_API_KEY", "HIGGSFIELD_SECRET"), "does": "картинки и видео"},
    {"id": "browser", "name": "Браузер", "cap": "", "env": (),
     "does": "работа на сайтах без API"},
    {"id": "search", "name": "Поиск", "cap": "search", "env": (),
     "does": "исследование темы"},
    {"id": "drive", "name": "Google Drive", "cap": "", "env": (),
     "does": "архив результатов"},
    {"id": "instagram", "name": "Instagram", "cap": "publish_instagram",
     "env": ("INSTAGRAM_ACCESS_TOKEN",), "does": "публикация"},
    {"id": "anthropic", "name": "Claude", "cap": "", "env": ("ANTHROPIC_API_KEY",),
     "does": "оркестратор"},
    {"id": "google", "name": "Gemini", "cap": "", "env": ("GEMINI_API_KEY",),
     "does": "тексты и зрение"},
    {"id": "openai", "name": "OpenAI", "cap": "", "env": ("OPENAI_API_KEY",),
     "does": "тексты"},
)


def _keys_present(names) -> bool:
    return all((os.getenv(n) or "").strip() for n in names) if names else False


async def _special(pid: str) -> dict:
    """Провайдеры, состояние которых знает не ключ, а отдельная проверка."""
    if pid == "browser":
        from core.hixiit import browser_available, higgsfield_session
        seen = await browser_available(quick=True)
        login = higgsfield_session()
        if seen.get("available"):
            return {"configured": True,
                    "note": f"{seen.get('where', '')}"
                            + ("; вход в higgsfield.ai есть" if login["ok"]
                               else "; входа в higgsfield.ai нет")}
        return {"configured": bool(login["ok"]),
                "note": seen.get("why", "") or "не проверялся"}
    if pid == "drive":
        from core import drive_store
        ready = drive_store.configured()
        return {"configured": ready["ok"], "note": ready["why"] or "ключ и папка заданы"}
    if pid == "search":
        keys = [n for n in ("PERPLEXITY_API_KEY",) if (os.getenv(n) or "").strip()]
        return {"configured": True,
                "note": "платный ключ есть" if keys else "только бесплатные источники"}
    if pid == "instagram":
        # Токен живёт и в базе: площадка подключается через /channels, а не
        # только переменной окружения.
        if _keys_present(("INSTAGRAM_ACCESS_TOKEN",)):
            return {"configured": True, "note": "переменная хостинга"}
        try:
            from core import credentials
            return {"configured": bool(await credentials.get("INSTAGRAM_ACCESS_TOKEN")),
                    "note": "ключ из базы"}
        except Exception:
            return {"configured": False, "note": ""}
    return {}


async def state(provider: dict) -> dict:
    """Состояние одного провайдера с доказательством или его отсутствием."""
    pid = provider["id"]
    special = await _special(pid)
    configured = special.get("configured") if special else _keys_present(provider["env"])
    note = special.get("note", "")

    row = {"id": pid, "name": provider["name"], "does": provider["does"],
           "note": note, "status": NOT_CONFIGURED, "why": "", "when": ""}
    if not configured:
        row["why"] = note or "нет ключа или доступа"
        return row

    row["status"] = AUTHENTICATED
    cap = provider.get("cap")
    if not cap:
        # Доказывать нечем — так и оставляем «подключён, не проверен».
        return row

    from core import capabilities
    proof = await capabilities.state(cap)
    if proof["state"] == "yes":
        row.update(status=READY, when=proof.get("when", ""))
    elif proof["state"] == "no":
        row.update(status=ERROR, why=proof.get("why", ""), when=proof.get("when", ""))
    else:
        row["why"] = "настоящей работы ещё не было"
    return row


async def registry() -> list[dict]:
    return [await state(p) for p in PROVIDERS]


def as_text(rows: list[dict]) -> str:
    lines = ["🔌 <b>Подключения</b>",
             "🟢 работает · 🟡 подключён, но не проверен · 🔴 ошибка · ⚪ не подключён"]
    for r in rows:
        line = f"\n{ICONS.get(r['status'], '⚪')} <b>{r['name']}</b> — {r['does']}"
        if r["status"] == READY and r.get("when"):
            line += f"\n   подтверждено {r['when']} UTC"
        elif r.get("why"):
            line += f"\n   {r['why'][:160]}"
        elif r.get("note"):
            line += f"\n   {r['note'][:160]}"
        lines.append(line)
    ready = sum(1 for r in rows if r["status"] == READY)
    lines.append(f"\nПодтверждено работой: {ready} из {len(rows)}")
    return "\n".join(lines)
