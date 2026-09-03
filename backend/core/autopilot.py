"""
Автопилот: полный цикл от анализа аккаунта до готового ролика.

Этапы:
  1. deep_analysis  — досье аккаунта (yt-dlp/Bright Data) + тренды + рецепт вируса
  2. interview      — агент сам решает, чего не хватает, и задаёт вопросы
  3. strategies     — 3 варианта стратегии на основе всего собранного
  4. week_plan      — план на неделю: reels / посты / карусели / сторис / threads
  5. predict        — прогноз залёта в % и лучшее время публикации

Состояние хранится в таблице Connection (без миграций схемы).
Экономия токенов: тяжёлые данные ужимаются, самопроверка идёт на дешёвой модели.
"""
import json
from datetime import datetime

from sqlalchemy import select
from database.db import AsyncSessionLocal
from database.models import Connection, Niche, UserProfile
from core.ai_router import ai_router, ECONOMY_MODELS

STATE_KEY = "autopilot_state"     # {stage, answers, questions, analysis, options, plan}


# ─────────────────────────── состояние ───────────────────────────

async def _load(db) -> dict:
    r = await db.execute(select(Connection).where(Connection.key_name == STATE_KEY))
    c = r.scalar_one_or_none()
    if c and c.key_value:
        try:
            return json.loads(c.key_value)
        except Exception:
            return {}
    return {}


async def _save(db, state: dict):
    r = await db.execute(select(Connection).where(Connection.key_name == STATE_KEY))
    c = r.scalar_one_or_none()
    payload = json.dumps(state, ensure_ascii=False)
    if c:
        c.key_value = payload
    else:
        db.add(Connection(key_name=STATE_KEY, key_value=payload))
    await db.commit()


async def get_state() -> dict:
    async with AsyncSessionLocal() as db:
        return await _load(db)


async def set_state(state: dict):
    async with AsyncSessionLocal() as db:
        await _save(db, state)


async def reset():
    await set_state({})


# ─────────────────────────── 1. анализ ───────────────────────────

async def deep_analysis() -> dict:
    """Собирает всё, что знаем: аккаунт, топ-посты, тренды, рецепт вируса."""
    out = {"collected_at": datetime.utcnow().isoformat()}

    async with AsyncSessionLocal() as db:
        nr = await db.execute(select(Niche).where(Niche.status == "active").limit(1))
        niche = nr.scalar_one_or_none()
        pr = await db.execute(select(UserProfile).limit(1))
        prof = pr.scalar_one_or_none()

    out["niche"] = niche.name if niche else ""
    out["city"] = (niche.city if niche else "") or ""
    out["platforms"] = (niche.platforms if niche else None) or ["instagram"]
    out["product"] = (prof.product_description if prof else "") or ""

    # Досье аккаунта (бесплатно: yt-dlp + опц. Bright Data)
    try:
        from core.social_intel import is_configured, get_account_intelligence
        if await is_configured():
            pf = [p for p in out["platforms"] if p != "telegram"] or ["instagram"]
            out["account"] = await get_account_intelligence(pf)
    except Exception as e:
        out["account_error"] = str(e)[:150]

    # Рецепт вируса из прошлой разведки (/viral), если был
    try:
        from core.viral_research import get_recipe
        rec = await get_recipe()
        if rec:
            out["viral_recipe"] = {k: v for k, v in rec.items() if k != "_refs"}
    except Exception:
        pass

    return out


# ─────────────────────────── 2. интервью ───────────────────────────

INTERVIEW_SYSTEM = (
    "Ты — стратег SMM. По данным аккаунта определи, каких сведений НЕ ХВАТАЕТ, "
    "чтобы делать залетающий контент. Задай максимум 5 коротких вопросов "
    "владельцу — по одному предложению каждый. Отвечай СТРОГО JSON."
)


async def build_questions(analysis: dict) -> list[str]:
    """Агент сам решает, что спросить у владельца для полной картины."""
    ctx = json.dumps(analysis, ensure_ascii=False)[:5000]
    prompt = (f"Данные аккаунта и ниши:\n{ctx}\n\n"
              'JSON: {"questions": ["вопрос", ...]}  (максимум 5, по-русски, конкретные)')
    model = ECONOMY_MODELS.get("niche_analyst", "gemini-2.0-flash")
    try:
        res = await ai_router.call(model, INTERVIEW_SYSTEM, prompt)
        t = res.get("text", "")
        data = json.loads(t[t.find("{"):t.rfind("}") + 1])
        qs = [q for q in data.get("questions", []) if q][:5]
    except Exception:
        qs = []
    if not qs:
        qs = ["Кто твой клиент и какую проблему решаешь?",
              "Какой оффер и цена?",
              "Какой тон: экспертный, дерзкий или развлекательный?",
              "Есть аккаунты-конкуренты, чей контент нравится?",
              "Сколько роликов в неделю готов выпускать?"]
    return qs


# ─────────────────────────── 3. стратегии ───────────────────────────

STRATEGY_SYSTEM = (
    "Ты — креативный директор. По данным аккаунта, ответам владельца и трендам "
    "предложи ровно 3 РАЗНЫЕ стратегии контента. Каждая — со своим углом подачи. "
    "Отвечай СТРОГО JSON, кратко и по делу."
)


async def build_strategies(analysis: dict, answers: dict) -> list[dict]:
    ctx = json.dumps(analysis, ensure_ascii=False)[:4000]
    ans = json.dumps(answers, ensure_ascii=False)[:2000]
    prompt = (
        f"Данные:\n{ctx}\n\nОтветы владельца:\n{ans}\n\n"
        'JSON: {"options":[{"title":"до 5 слов","angle":"угол подачи одним предложением",'
        '"why":"почему сработает на этом аккаунте","first_reel":"идея первого рилса — хук и суть"}]}'
    )
    model = ECONOMY_MODELS.get("strategist", "gemini-2.0-flash")
    try:
        res = await ai_router.call(model, STRATEGY_SYSTEM, prompt)
        t = res.get("text", "")
        data = json.loads(t[t.find("{"):t.rfind("}") + 1])
        return data.get("options", [])[:3]
    except Exception:
        return []


# ─────────────────────────── 4. план на неделю ───────────────────────────

PLAN_SYSTEM = (
    "Ты — контент-стратег. Составь план на 7 дней под выбранную стратегию. "
    "Форматы: reels, пост, карусель, сторис, threads. Учитывай, что reels дают охват, "
    "карусели — сохранения, сторис — вовлечение, threads — обсуждение. "
    "Отвечай СТРОГО JSON."
)


async def build_week_plan(strategy: dict, analysis: dict) -> list[dict]:
    prompt = (
        f"Стратегия: {json.dumps(strategy, ensure_ascii=False)}\n"
        f"Ниша: {analysis.get('niche')} | Продукт: {analysis.get('product')[:300]}\n\n"
        'JSON: {"days":[{"day":1,"format":"reels|post|carousel|stories|threads",'
        '"topic":"тема","hook":"хук первой секунды","cta":"призыв","best_time":"19:00"}]}'
        " — ровно 7 дней, форматы чередуй."
    )
    model = ECONOMY_MODELS.get("strategist", "gemini-2.0-flash")
    try:
        res = await ai_router.call(model, PLAN_SYSTEM, prompt)
        t = res.get("text", "")
        data = json.loads(t[t.find("{"):t.rfind("}") + 1])
        return data.get("days", [])[:7]
    except Exception:
        return []


# ─────────────────────────── 5. прогноз виральности ───────────────────────────

PREDICT_SYSTEM = (
    "Ты — аналитик виральности. Оцени шанс, что ролик наберёт охват выше среднего "
    "для ЭТОГО аккаунта. Опирайся на метрики аккаунта, силу хука и попадание в тренд. "
    "Будь реалистичен: большинство роликов — 20-50%. Отвечай СТРОГО JSON."
)


async def predict_virality(idea: dict, analysis: dict) -> dict:
    """Прогноз: шанс залёта в % + лучшее время публикации + что усилить."""
    acc = json.dumps(analysis.get("account", {}), ensure_ascii=False)[:2500]
    rec = json.dumps(analysis.get("viral_recipe", {}), ensure_ascii=False)[:1500]
    prompt = (
        f"Идея ролика: {json.dumps(idea, ensure_ascii=False)[:1200]}\n"
        f"Метрики аккаунта: {acc}\n"
        f"Рецепт залетевших в нише: {rec}\n\n"
        'JSON: {"score": 0-100, "verdict":"короткий вывод",'
        '"strong":["что сильно"],"weak":["что слабо"],'
        '"fix":["как поднять шанс"],"best_time":"день недели и час по местному",'
        '"why_time":"почему это время"}'
    )
    model = ECONOMY_MODELS.get("reviewer", "gemini-2.0-flash")
    try:
        res = await ai_router.call(model, PREDICT_SYSTEM, prompt)
        t = res.get("text", "")
        data = json.loads(t[t.find("{"):t.rfind("}") + 1])
        data["score"] = max(0, min(100, int(data.get("score", 40))))
        return data
    except Exception as e:
        return {"score": 0, "verdict": f"не удалось оценить: {str(e)[:100]}",
                "best_time": "", "strong": [], "weak": [], "fix": []}


def format_prediction(p: dict) -> str:
    """Читаемый прогноз для Telegram."""
    score = p.get("score", 0)
    bar = "🟩" * (score // 10) + "⬜" * (10 - score // 10)
    lines = [f"📈 <b>Шанс залёта: {score}%</b>", bar, ""]
    if p.get("verdict"):
        lines.append(p["verdict"])
    if p.get("strong"):
        lines += ["", "<b>Сильно:</b>"] + [f"• {x}" for x in p["strong"][:3]]
    if p.get("weak"):
        lines += ["", "<b>Слабо:</b>"] + [f"• {x}" for x in p["weak"][:3]]
    if p.get("fix"):
        lines += ["", "<b>Как усилить:</b>"] + [f"• {x}" for x in p["fix"][:3]]
    if p.get("best_time"):
        lines += ["", f"🕐 <b>Публиковать:</b> {p['best_time']}"]
        if p.get("why_time"):
            lines.append(f"<i>{p['why_time']}</i>")
    return "\n".join(lines)
