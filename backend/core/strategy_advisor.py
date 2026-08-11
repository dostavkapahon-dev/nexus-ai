"""
Роль 1 — SMM-стратег: анализ «своё vs чужое успешное» → 2-3 варианта стратегии.

Дёшево: один LLM-вызов на дешёвой модели, данные аккаунта берём бесплатно
(yt-dlp + опц. Bright Data), тренды — из уже собранного контекста. Результат — короткий
структурированный отчёт + варианты, которые пользователь выбирает кнопкой
в Telegram. Выбор сохраняется в таблицу Connection (без миграций схемы).
"""
import json
from sqlalchemy import select
from database.models import Niche, UserProfile, Connection
from core.ai_router import ai_router, ECONOMY_MODELS

SYSTEM = (
    "Ты SMM-стратег. Анализируешь метрики своего аккаунта и тренды ниши, "
    "сравниваешь что зашло у себя и у конкурентов. Отвечаешь СТРОГО в JSON, "
    "коротко и по делу, без воды."
)

TEMPLATE = """Ниша: {niche}
Профиль/продукт: {product}
Данные моего аккаунта (шапка, подписчики, ТОП постов по вовлечённости):
{account}

Сделай:
1. Короткий вывод «что из моего зашло, что нет и почему» (2-4 пункта).
2. Ровно 3 варианта дальнейшей стратегии (разные по подходу: напр. усилить
   экспертный тон / больше каруселей / другой тип хука). Каждый — с коротким
   планом на неделю.

Ответ строго в JSON:
{{"analysis": ["пункт", ...],
  "options": [
    {{"title": "коротко (до 5 слов)", "desc": "1 предложение",
      "plan": "что делать неделю, 2-3 пункта"}}
  ]}}"""

CONN_OPTIONS = "last_strategy_options"   # кэш предложенных вариантов (JSON)
CONN_CHOSEN = "chosen_strategy"          # выбранная стратегия (JSON)


async def _get_conn(db, key: str):
    r = await db.execute(select(Connection).where(Connection.key_name == key))
    return r.scalar_one_or_none()


async def _save_conn(db, key: str, value: str):
    conn = await _get_conn(db, key)
    if conn:
        conn.key_value = value
    else:
        db.add(Connection(key_name=key, key_value=value))
    await db.commit()


async def build_options(db) -> dict:
    """Собирает анализ + 3 варианта стратегии. Кэширует их для последующего выбора."""
    niche_r = await db.execute(select(Niche).where(Niche.status == "active").limit(1))
    niche = niche_r.scalar_one_or_none()
    prof_r = await db.execute(select(UserProfile).limit(1))
    prof = prof_r.scalar_one_or_none()

    # Данные своего аккаунта (бесплатно: yt-dlp + опц. Bright Data) — если задан ник.
    account = "нет данных аккаунта (укажи ники IG/TikTok/YouTube в настройках)"
    try:
        from core.social_intel import is_configured, get_account_intelligence
        if await is_configured():
            platforms = (niche.platforms if niche else None) or ["instagram"]
            intel = await get_account_intelligence([p for p in platforms if p != "telegram"] or ["instagram"])
            account = json.dumps(intel, ensure_ascii=False)[:5000]
    except Exception:
        pass

    # Реальные результаты собственных публикаций — самый honest источник для стратегии.
    try:
        from core.post_analytics import performance, top_posts
        perf = await performance(30)
        if perf.get("posts"):
            best = await top_posts(30, limit=5)
            account += ("\n\nФАКТИЧЕСКИЕ РЕЗУЛЬТАТЫ ЗА 30 ДНЕЙ: "
                        f"{perf['posts']} публикаций, {perf['views']} просмотров, "
                        f"средний ER {perf['avg_engagement_rate']}%.")
            if best:
                account += "\nЛучшее: " + "; ".join(
                    f"«{p['topic'] or '—'}» (ER {p['engagement_rate']}%)" for p in best[:3])
    except Exception:
        pass

    # Рынок и конкуренты из истории исследований — стратегия на фактах, а не догадках.
    try:
        from core.research_store import market_context
        ctx = await market_context()
        if ctx:
            account += "\n\n" + ctx[:2000]
    except Exception:
        pass

    prompt = TEMPLATE.format(
        niche=(niche.name if niche else "—"),
        product=(prof.product_description if prof else "—") or "—",
        account=account,
    )
    model = ECONOMY_MODELS.get("strategist", "deepseek-chat")
    res = await ai_router.call(model, SYSTEM, prompt)
    text = res.get("text", "")
    try:
        start, end = text.find("{"), text.rfind("}") + 1
        data = json.loads(text[start:end])
    except Exception:
        data = {"analysis": ["Не удалось разобрать ответ модели"], "options": []}

    data.setdefault("options", [])
    await _save_conn(db, CONN_OPTIONS, json.dumps(data, ensure_ascii=False))
    return data


async def choose_option(db, index: int) -> dict | None:
    """Фиксирует выбранный вариант стратегии (по индексу из последнего списка)."""
    conn = await _get_conn(db, CONN_OPTIONS)
    if not conn or not conn.key_value:
        return None
    data = json.loads(conn.key_value)
    options = data.get("options", [])
    if index < 0 or index >= len(options):
        return None
    chosen = options[index]
    await _save_conn(db, CONN_CHOSEN, json.dumps(chosen, ensure_ascii=False))
    return chosen


async def get_chosen(db) -> dict | None:
    conn = await _get_conn(db, CONN_CHOSEN)
    if conn and conn.key_value:
        try:
            return json.loads(conn.key_value)
        except Exception:
            return None
    return None
