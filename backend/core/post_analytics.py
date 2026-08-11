"""
Аналитика опубликованного: сбор реальных метрик и обучение на результатах.

Раньше аналитика только читалась «на лету» и нигде не сохранялась: сравнить
«до/после», понять какой хук сработал и учиться на фактах было невозможно.
Теперь метрики публикаций складываются в БД, а лучшие и худшие результаты
превращаются в уроки для памяти агента.
"""
from datetime import datetime, timedelta

from sqlalchemy import select, func

from database.db import AsyncSessionLocal
from database.models import Publication, ContentPlan, GeneratedContent

# Метрики берём не сразу: площадке нужно время, чтобы набрать показы.
MIN_AGE_HOURS = 2
# После этого срока цифры почти не меняются — перестаём опрашивать.
MAX_AGE_DAYS = 30


def _engagement_rate(likes: int, comments: int, saves: int, reach: int, views: int) -> float:
    """Вовлечённость в процентах. База — охват, если его нет, берём просмотры."""
    base = reach or views or 0
    if base <= 0:
        return 0.0
    return round((likes + comments + saves) / base * 100, 2)


async def record_publication(plan_id: str, niche_id: str, platform: str, status: str,
                             external_id: str = "", post_url: str = "",
                             topic: str = "", hook: str = "", content_format: str = "") -> str:
    """Сохраняет факт публикации вместе с тем, ЧТО именно опубликовали.

    Тема, хук и формат нужны, чтобы позже связать результат с приёмом.
    """
    async with AsyncSessionLocal() as db:
        pub = Publication(plan_id=plan_id, niche_id=niche_id or "", platform=platform,
                          status=status, external_id=external_id or "",
                          post_url=post_url or "", topic=topic[:300] if topic else "",
                          hook=hook or "", content_format=content_format or "")
        db.add(pub)
        await db.commit()
        return pub.id


async def _fetch_platform_metrics(platform: str, limit: int = 25) -> dict[str, dict]:
    """Свежие метрики площадки, разложенные по ссылке на пост.

    Идём через коннектор площадки — единый контракт из BLOCK 03.
    """
    try:
        from connectors import get_connector
        c = get_connector(platform)
        if not c:
            return {}
        data = await c.read_posts(limit)
    except Exception:
        return {}
    if not data.get("ok"):
        return {}

    by_url: dict[str, dict] = {}
    for post in data.get("top_posts") or []:
        url = post.get("url")
        if url:
            by_url[url] = post
    return by_url


async def collect_metrics(max_posts: int = 50) -> dict:
    """Обновляет метрики недавних публикаций. Запускается джобом раз в сутки."""
    now = datetime.utcnow()
    fresh_enough = now - timedelta(hours=MIN_AGE_HOURS)
    not_too_old = now - timedelta(days=MAX_AGE_DAYS)

    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(Publication)
            .where(Publication.status == "published",
                   Publication.published_at <= fresh_enough,
                   Publication.published_at >= not_too_old)
            .order_by(Publication.published_at.desc())
            .limit(max_posts)
        )
        pubs = list(r.scalars())

    if not pubs:
        return {"updated": 0, "platforms": [], "note": "нет публикаций для обновления"}

    platforms = sorted({p.platform for p in pubs if p.platform})
    cache: dict[str, dict[str, dict]] = {}
    for platform in platforms:
        cache[platform] = await _fetch_platform_metrics(platform)

    updated = 0
    async with AsyncSessionLocal() as db:
        for pub in pubs:
            metrics = (cache.get(pub.platform) or {}).get(pub.post_url or "")
            if not metrics:
                continue
            r = await db.execute(select(Publication).where(Publication.id == pub.id))
            row = r.scalar_one_or_none()
            if not row:
                continue
            row.views = int(metrics.get("views") or 0)
            row.likes = int(metrics.get("likes") or 0)
            row.comments = int(metrics.get("comments") or 0)
            row.saves = int(metrics.get("saved") or metrics.get("saves") or 0)
            row.shares = int(metrics.get("shares") or 0)
            row.reach = int(metrics.get("reach") or 0)
            row.engagement_rate = _engagement_rate(row.likes, row.comments, row.saves,
                                                   row.reach, row.views)
            row.metrics_updated_at = datetime.utcnow()
            updated += 1
        await db.commit()

    return {"updated": updated, "checked": len(pubs), "platforms": platforms}


async def performance(days: int = 30, niche_id: str = "") -> dict:
    """Сводка результатов: сколько опубликовано, суммарные охваты, средняя вовлечённость."""
    since = datetime.utcnow() - timedelta(days=days)
    async with AsyncSessionLocal() as db:
        q = select(
            func.count(Publication.id),
            func.coalesce(func.sum(Publication.views), 0),
            func.coalesce(func.sum(Publication.likes), 0),
            func.coalesce(func.sum(Publication.comments), 0),
            func.coalesce(func.avg(Publication.engagement_rate), 0.0),
        ).where(Publication.published_at >= since, Publication.status == "published")
        if niche_id:
            q = q.where(Publication.niche_id == niche_id)
        count, views, likes, comments, avg_er = (await db.execute(q)).one()

        by_platform_rows = await db.execute(
            select(Publication.platform,
                   func.count(Publication.id),
                   func.coalesce(func.sum(Publication.views), 0),
                   func.coalesce(func.avg(Publication.engagement_rate), 0.0))
            .where(Publication.published_at >= since, Publication.status == "published")
            .group_by(Publication.platform)
        )
        by_platform = [{"platform": p or "—", "posts": int(n or 0),
                        "views": int(v or 0), "avg_er": round(float(e or 0), 2)}
                       for p, n, v, e in by_platform_rows.all()]

        failed = await db.execute(
            select(func.count(Publication.id))
            .where(Publication.published_at >= since, Publication.status == "failed")
        )

    return {
        "days": days, "posts": int(count or 0), "failed": int(failed.scalar() or 0),
        "views": int(views or 0), "likes": int(likes or 0), "comments": int(comments or 0),
        "avg_engagement_rate": round(float(avg_er or 0), 2),
        "by_platform": by_platform,
    }


async def top_posts(days: int = 30, limit: int = 10, worst: bool = False) -> list[dict]:
    """Лучшие (или худшие) публикации по вовлечённости — на них учится агент."""
    since = datetime.utcnow() - timedelta(days=days)
    order = Publication.engagement_rate.asc() if worst else Publication.engagement_rate.desc()
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(Publication)
            .where(Publication.published_at >= since,
                   Publication.status == "published",
                   Publication.metrics_updated_at.isnot(None))
            .order_by(order)
            .limit(limit)
        )
        rows = list(r.scalars())
    return [{"id": p.id, "platform": p.platform, "topic": p.topic, "hook": p.hook,
             "format": p.content_format, "views": p.views, "likes": p.likes,
             "comments": p.comments, "saves": p.saves,
             "engagement_rate": p.engagement_rate, "url": p.post_url,
             "published_at": p.published_at.isoformat() if p.published_at else None}
            for p in rows]


async def learn_from_results(days: int = 30) -> dict:
    """Превращает реальные результаты в уроки для памяти агента.

    Смысл всего блока: агент должен опираться на то, что сработало у НЕГО,
    а не только на общие рассуждения модели.
    """
    best = await top_posts(days, limit=5)
    worst = await top_posts(days, limit=3, worst=True)
    if not best:
        return {"ok": False, "reason": "нет публикаций с собранными метриками"}

    lines = ["РЕАЛЬНЫЕ РЕЗУЛЬТАТЫ ПУБЛИКАЦИЙ ЗА ПЕРИОД:", "", "ЧТО СРАБОТАЛО ЛУЧШЕ ВСЕГО:"]
    for p in best:
        lines.append(f"- [{p['platform']}, {p['format'] or 'пост'}] «{p['topic'] or '—'}» "
                     f"хук: «{(p['hook'] or '—')[:100]}» → "
                     f"{p['views']} просмотров, ER {p['engagement_rate']}%")
    if worst:
        lines += ["", "ЧТО СРАБОТАЛО ХУЖЕ ВСЕГО:"]
        for p in worst:
            lines.append(f"- [{p['platform']}] «{p['topic'] or '—'}» "
                         f"хук: «{(p['hook'] or '—')[:100]}» → ER {p['engagement_rate']}%")

    try:
        from core.skills_store import learn_from
        learned = await learn_from("\n".join(lines), source="post_analytics")
        return {"ok": True, "learned": len(learned or []), "best": len(best),
                "worst": len(worst)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
