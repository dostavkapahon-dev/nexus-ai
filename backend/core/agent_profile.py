"""
Профиль Главного агента: что он знает о бизнесе, прежде чем начать работать.

Смысл модуля. Пользователь задаёт нишу, бренд, цели, аудиторию, стиль, площадки,
частоту, правила и ограничения — и это должно доходить до модели. До сих пор
дирижёр работал по промпту, зашитому под одну студию, а введённые пользователем
настройки лежали в `Niche` и `UserProfile` и никуда не ехали: агент про них
просто не знал.

Профиль читается на каждом шаге tool-use, поэтому держим его в памяти процесса
и сбрасываем кэш при сохранении — иначе каждый шаг дирижёра стоил бы запроса в БД.
"""
import json

from sqlalchemy import select

from database.db import AsyncSessionLocal
from database.models import AgentProfile, Niche, UserProfile

FIELDS = ("niche", "brand_name", "brand_location", "goals", "audience", "style",
          "tone_of_voice", "platforms", "posts_per_day", "rules", "constraints",
          "tasks", "strategy", "timezone", "brand_voice")

_cache: dict | None = None


def _as_dict(p: AgentProfile) -> dict:
    return {
        "niche": p.niche or "", "brand_name": p.brand_name or "",
        "brand_location": p.brand_location or "", "goals": p.goals or "",
        "audience": p.audience or "", "style": p.style or "",
        "tone_of_voice": p.tone_of_voice or "", "platforms": p.platforms or [],
        "posts_per_day": int(p.posts_per_day or 0), "rules": p.rules or "",
        "constraints": p.constraints or "", "tasks": p.tasks or "",
        "strategy": p.strategy or "", "timezone": p.timezone or "",
        "brand_voice": p.brand_voice or "",
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def empty() -> dict:
    out = {f: "" for f in FIELDS}
    out["platforms"] = []
    out["posts_per_day"] = 0
    out["updated_at"] = None
    return out


async def get() -> dict:
    """Профиль агента. Пустой — не ошибка: система работает и без настроек."""
    global _cache
    if _cache is not None:
        return _cache
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(AgentProfile).limit(1))
        p = r.scalar_one_or_none()
    _cache = _as_dict(p) if p else empty()
    return _cache


async def save(data: dict) -> dict:
    global _cache
    clean = {k: v for k, v in (data or {}).items() if k in FIELDS and v is not None}
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(AgentProfile).limit(1))
        p = r.scalar_one_or_none()
        if not p:
            p = AgentProfile()
            db.add(p)
        for key, value in clean.items():
            setattr(p, key, value)
        await db.commit()
        await db.refresh(p)
        result = _as_dict(p)
    _cache = result
    return result


def invalidate():
    """Сброс кэша — нужен тестам и любому пути записи в обход `save`."""
    global _cache
    _cache = None


async def bootstrap() -> dict:
    """Первое заполнение профиля из того, что пользователь уже вводил раньше.

    Ниша, площадки, частота и tone of voice жили в `Niche`, продукт и стратегия —
    в `UserProfile`. Переносим их один раз, чтобы включение профиля не выглядело
    как «все мои настройки исчезли».
    """
    current = await get()
    if any(current.get(f) for f in ("niche", "goals", "audience", "brand_name")):
        return current

    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Niche).where(Niche.status == "active").limit(1))
        niche = r.scalar_one_or_none()
        r2 = await db.execute(select(UserProfile).limit(1))
        prof = r2.scalar_one_or_none()

    data = {}
    if niche:
        data.update({"niche": niche.name or "", "brand_location": niche.city or "",
                     "platforms": niche.platforms or [],
                     "posts_per_day": int(niche.posts_per_day or 1),
                     "tone_of_voice": niche.tone_of_voice or "",
                     "audience": niche.about_user or ""})
    if prof:
        data.update({"goals": prof.strategy_focus or "", "style": prof.brand_style or "",
                     "tasks": prof.product_description or ""})
    if not data:
        return current

    # Голос бренда до сих пор лежал в файле — забираем и его, чтобы профиль был
    # единственным местом правды.
    try:
        from core.brand import get_brand_voice
        voice = get_brand_voice()
        if voice:
            data["brand_voice"] = voice
    except Exception:
        pass
    return await save(data)


def _line(label: str, value) -> str:
    if isinstance(value, list):
        value = ", ".join(str(v) for v in value)
    value = str(value or "").strip()
    return f"{label}: {value}\n" if value else ""


async def as_prompt() -> str:
    """Профиль в виде блока для системного промпта.

    Пустые поля не выводим: строка «Ограничения:» без содержимого только сбивает
    модель и тратит токены.
    """
    p = await get()
    # Частота сама по себе ничего не говорит о бизнесе: если заполнена только она,
    # профиль считаем пустым и не тратим на него место в промпте.
    meaningful = any(str(p.get(f) or "").strip() for f in FIELDS if f != "posts_per_day")
    if not meaningful:
        return ""
    body = (
        _line("Ниша", p["niche"])
        + _line("Бренд", " · ".join(x for x in (p["brand_name"], p["brand_location"]) if x))
        + _line("Цели", p["goals"])
        + _line("Аудитория", p["audience"])
        + _line("Стиль", p["style"])
        + _line("Tone of voice", p["tone_of_voice"])
        + _line("Площадки", p["platforms"])
        + _line("Частота публикаций (в день)", p["posts_per_day"] or "")
        + _line("Правила", p["rules"])
        + _line("Ограничения (никогда не нарушать)", p["constraints"])
        + _line("Постоянные задачи", p["tasks"])
        + _line("Стратегия", p["strategy"])
        + _line("Часовой пояс", p["timezone"])
    )
    if not body:
        return ""
    voice = (p["brand_voice"] or "").strip()
    voice_block = f"\nГОЛОС БРЕНДА:\n{voice}\n" if voice else ""
    return ("--- ПРОФИЛЬ ГЛАВНОГО АГЕНТА (задан пользователем, важнее общих правил) ---\n"
            + body + voice_block)


async def platforms() -> list[str]:
    """Площадки из профиля — по ним фильтруются правила и планирование."""
    p = await get()
    items = p.get("platforms") or []
    if isinstance(items, str):
        try:
            items = json.loads(items)
        except ValueError:
            items = [x.strip() for x in items.split(",") if x.strip()]
    return [str(x).strip().lower() for x in items if str(x).strip()]
