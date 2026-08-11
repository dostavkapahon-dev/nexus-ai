"""
Хранилище контент-стратегий: версии, период действия, измеримый результат.

Раньше стратегия жила в KV-ключах и перезатиралась: при выборе новой прошлая
терялась, а сравнить «какая работала лучше» было нечем — публикации не знали,
под какой стратегией они вышли.

Теперь у стратегии есть версия, статус и период, а у публикаций — привязка к ней.
"""
from datetime import datetime

from sqlalchemy import select, func, desc

from database.db import AsyncSessionLocal
from database.models import Strategy, Publication

DRAFT, ACTIVE, ARCHIVED = "draft", "active", "archived"


async def _next_version(db, niche_id: str) -> int:
    r = await db.execute(
        select(func.max(Strategy.version)).where(Strategy.niche_id == (niche_id or "")))
    return int(r.scalar() or 0) + 1


async def save_options(options: list[dict], niche_id: str = "") -> list[str]:
    """Сохраняет предложенные варианты как черновики. Возвращает их id."""
    ids = []
    async with AsyncSessionLocal() as db:
        version = await _next_version(db, niche_id)
        items = []
        for opt in options[:5]:
            item = Strategy(
                niche_id=niche_id or "", version=version,
                title=(opt.get("title") or "Без названия")[:200],
                angle=opt.get("angle") or opt.get("desc") or "",
                why=opt.get("why") or "",
                plan=opt.get("plan") or opt.get("first_reel") or "",
                pillars=opt.get("pillars") or [],
                status=DRAFT, source="auto")
            db.add(item)
            items.append(item)
        # id проставляется значением по умолчанию только при вставке —
        # без flush читать его рано (вернётся None).
        await db.flush()
        ids = [i.id for i in items]
        await db.commit()
    return ids


async def activate(strategy_id: str) -> dict | None:
    """Делает стратегию активной, прошлую — архивной.

    Активной может быть только одна: иначе непонятно, чей результат мы меряем.
    """
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Strategy).where(Strategy.id == strategy_id))
        item = r.scalar_one_or_none()
        if not item:
            return None

        prev = await db.execute(
            select(Strategy).where(Strategy.niche_id == item.niche_id,
                                   Strategy.status == ACTIVE))
        for old in prev.scalars():
            old.status = ARCHIVED
            old.archived_at = datetime.utcnow()

        item.status = ACTIVE
        item.activated_at = datetime.utcnow()
        await db.commit()
        return _as_dict(item)


async def current(niche_id: str = "") -> dict | None:
    """Действующая стратегия — её угол подачи подмешивается в генерацию."""
    async with AsyncSessionLocal() as db:
        q = select(Strategy).where(Strategy.status == ACTIVE)
        if niche_id:
            q = q.where(Strategy.niche_id == niche_id)
        r = await db.execute(q.order_by(desc(Strategy.activated_at)).limit(1))
        item = r.scalar_one_or_none()
    return _as_dict(item) if item else None


async def history(niche_id: str = "", status: str = "", limit: int = 30) -> list[dict]:
    async with AsyncSessionLocal() as db:
        q = select(Strategy).order_by(desc(Strategy.created_at)).limit(min(limit, 100))
        if niche_id:
            q = q.where(Strategy.niche_id == niche_id)
        if status:
            q = q.where(Strategy.status == status)
        r = await db.execute(q)
        return [_as_dict(i) for i in r.scalars()]


async def add_manual(title: str, angle: str = "", plan: str = "",
                     pillars: list | None = None, niche_id: str = "") -> str:
    """Своя стратегия, написанная руками — равноправна с предложенными агентом."""
    async with AsyncSessionLocal() as db:
        item = Strategy(niche_id=niche_id or "", version=await _next_version(db, niche_id),
                        title=title[:200], angle=angle, plan=plan,
                        pillars=pillars or [], status=DRAFT, source="manual")
        db.add(item)
        await db.commit()
        return item.id


async def effectiveness(niche_id: str = "") -> list[dict]:
    """Сравнение стратегий по фактическому результату публикаций.

    Ради этого блок и делался: видно, какая стратегия дала лучший отклик,
    а не только какая красивее звучала.
    """
    async with AsyncSessionLocal() as db:
        q = select(Strategy).order_by(desc(Strategy.created_at))
        if niche_id:
            q = q.where(Strategy.niche_id == niche_id)
        r = await db.execute(q)
        strategies = list(r.scalars())

        out = []
        for s in strategies:
            stats = await db.execute(
                select(func.count(Publication.id),
                       func.coalesce(func.sum(Publication.views), 0),
                       func.coalesce(func.avg(Publication.engagement_rate), 0.0))
                .where(Publication.strategy_id == s.id,
                       Publication.status == "published"))
            posts, views, avg_er = stats.one()
            if not posts and s.status == DRAFT:
                continue          # черновик без публикаций сравнивать не с чем
            out.append({**_as_dict(s), "posts": int(posts or 0),
                        "views": int(views or 0),
                        "avg_engagement_rate": round(float(avg_er or 0), 2)})

    out.sort(key=lambda x: x["avg_engagement_rate"], reverse=True)
    return out


async def best(niche_id: str = "") -> dict | None:
    """Самая результативная стратегия из тех, что реально публиковались."""
    items = [i for i in await effectiveness(niche_id) if i["posts"] >= 3]
    return items[0] if items else None


async def context(niche_id: str = "") -> str:
    """Строка для промптов: чем сейчас руководствуемся и что показал опыт."""
    parts = []
    cur = await current(niche_id)
    if cur:
        parts.append(f"ДЕЙСТВУЮЩАЯ СТРАТЕГИЯ (v{cur['version']}): «{cur['title']}». "
                     f"Угол: {cur['angle'][:300]}")
        if cur.get("pillars"):
            parts.append("Рубрики: " + ", ".join(str(p) for p in cur["pillars"][:8]))
        if cur.get("plan"):
            parts.append(f"План: {cur['plan'][:300]}")

    top = await best(niche_id)
    if top and (not cur or top["id"] != cur["id"]):
        parts.append(f"ЛУЧШИЙ ИСТОРИЧЕСКИЙ РЕЗУЛЬТАТ: «{top['title']}» — "
                     f"{top['posts']} публикаций, средний ER {top['avg_engagement_rate']}%")
    return "\n".join(parts)


def _as_dict(s: Strategy) -> dict:
    return {"id": s.id, "niche_id": s.niche_id, "version": s.version, "title": s.title,
            "angle": s.angle or "", "why": s.why or "", "plan": s.plan or "",
            "pillars": s.pillars or [], "status": s.status, "source": s.source,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "activated_at": s.activated_at.isoformat() if s.activated_at else None,
            "archived_at": s.archived_at.isoformat() if s.archived_at else None}
