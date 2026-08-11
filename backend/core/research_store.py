"""
Хранилище исследований рынка и конкурентов.

Раньше результат разведки жил в одном KV-ключе `viral_recipe` и перезатирался при
каждом запуске: нельзя было ни сравнить «что менялось в нише», ни вернуться к
прошлым выводам, ни отследить динамику конкурентов.

Теперь у исследований есть история, привязка к нише и к задаче, а у конкурентов —
срезы метрик во времени.
"""
from datetime import datetime, timedelta

from sqlalchemy import select, func, desc

from database.db import AsyncSessionLocal
from database.models import Research, Competitor

KINDS = ("trends", "viral", "competitor", "market")


# ─────────────────────────── исследования ───────────────────────────

async def save(kind: str, query: str = "", summary: str = "", findings: dict | None = None,
               sources: list | None = None, niche_id: str = "") -> str:
    """Сохраняет исследование в историю. Задача подхватывается из контекста."""
    task_id = ""
    try:
        from core.cost_tracker import current_task_id
        task_id = current_task_id.get() or ""
    except Exception:
        pass

    async with AsyncSessionLocal() as db:
        item = Research(niche_id=niche_id or "", task_id=task_id, kind=kind,
                        query=(query or "")[:500], summary=(summary or "")[:4000],
                        findings=findings or {}, sources=sources or [])
        db.add(item)
        await db.commit()
        return item.id


async def latest(kind: str = "", niche_id: str = "") -> dict | None:
    """Самое свежее исследование нужного вида."""
    async with AsyncSessionLocal() as db:
        q = select(Research).order_by(desc(Research.created_at)).limit(1)
        if kind:
            q = q.where(Research.kind == kind)
        if niche_id:
            q = q.where(Research.niche_id == niche_id)
        r = await db.execute(q)
        item = r.scalar_one_or_none()
    return _as_dict(item) if item else None


async def history(kind: str = "", niche_id: str = "", limit: int = 20) -> list[dict]:
    async with AsyncSessionLocal() as db:
        q = select(Research).order_by(desc(Research.created_at)).limit(min(limit, 100))
        if kind:
            q = q.where(Research.kind == kind)
        if niche_id:
            q = q.where(Research.niche_id == niche_id)
        r = await db.execute(q)
        return [_as_dict(i) for i in r.scalars()]


async def stats() -> dict:
    """Сколько чего исследовано — для дашборда."""
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(Research.kind, func.count(Research.id)).group_by(Research.kind))
        by_kind = {k or "—": int(n) for k, n in rows.all()}
        last = await db.execute(select(func.max(Research.created_at)))
        last_at = last.scalar()
    return {"by_kind": by_kind, "total": sum(by_kind.values()),
            "last_at": last_at.isoformat() if last_at else None}


def _as_dict(r: Research) -> dict:
    return {"id": r.id, "kind": r.kind, "query": r.query, "summary": r.summary,
            "findings": r.findings or {}, "sources": r.sources or [],
            "niche_id": r.niche_id, "task_id": r.task_id,
            "created_at": r.created_at.isoformat() if r.created_at else None}


# ─────────────────────────── конкуренты ───────────────────────────

async def track_competitor(platform: str, handle: str, niche_id: str = "") -> dict:
    """Снимает текущие метрики конкурента и добавляет срез в историю.

    Читаем через тот же бесплатный путь, что и свои аккаунты (BLOCK 03/04):
    официальные API → yt-dlp → браузер.
    """
    handle = (handle or "").lstrip("@").strip()
    if not handle:
        return {"ok": False, "error": "не указан ник"}

    try:
        if platform == "instagram":
            from core.instagram_reader import analyze_competitor, is_configured
            data = await analyze_competitor(handle) if is_configured() else {}
            if not data.get("ok"):
                from core.social_intel import _fetch_instagram
                data = await _fetch_instagram(handle)
        elif platform == "youtube":
            from core.youtube_reader import analyze, is_configured
            data = await analyze(handle) if is_configured() else {}
            if not data.get("ok"):
                from core.social_intel import _fetch_channel
                data = await _fetch_channel("youtube", handle)
        else:
            from core.social_intel import _fetch_channel
            data = await _fetch_channel(platform, handle)
    except Exception as e:
        return {"ok": False, "error": str(e)[:200], "handle": handle}

    if not data.get("ok"):
        return {"ok": False, "error": data.get("error", "не удалось получить данные"),
                "handle": handle, "platform": platform}

    posts = data.get("top_posts") or []
    avg_er = _avg_engagement(posts, data.get("followers") or 0)

    async with AsyncSessionLocal() as db:
        row = Competitor(niche_id=niche_id or "", platform=platform, handle=handle,
                         followers=int(data.get("followers") or 0),
                         posts_count=int(data.get("posts_count") or 0),
                         avg_engagement=avg_er, top_posts=posts[:5])
        db.add(row)
        await db.commit()
        snapshot_id = row.id

    return {"ok": True, "id": snapshot_id, "platform": platform, "handle": handle,
            "followers": int(data.get("followers") or 0),
            "posts_count": int(data.get("posts_count") or 0),
            "avg_engagement": avg_er, "top_posts": posts[:5]}


def _avg_engagement(posts: list, followers: int) -> float:
    """Средняя вовлечённость по постам конкурента (лайки+комменты к подписчикам)."""
    if not posts or followers <= 0:
        return 0.0
    total = 0
    counted = 0
    for p in posts:
        likes = int(p.get("likes") or 0)
        comments = int(p.get("comments") or 0)
        if likes or comments:
            total += likes + comments
            counted += 1
    if not counted:
        return 0.0
    return round(total / counted / followers * 100, 2)


async def tracked_competitors(niche_id: str = "") -> list[dict]:
    """Последний срез по каждому отслеживаемому конкуренту + динамика."""
    async with AsyncSessionLocal() as db:
        q = select(Competitor).where(Competitor.active == True)  # noqa: E712
        if niche_id:
            q = q.where(Competitor.niche_id == niche_id)
        r = await db.execute(q.order_by(desc(Competitor.checked_at)))
        rows = list(r.scalars())

    seen: dict[tuple, dict] = {}
    for row in rows:
        key = (row.platform, row.handle)
        if key not in seen:
            seen[key] = {"platform": row.platform, "handle": row.handle,
                         "followers": row.followers, "posts_count": row.posts_count,
                         "avg_engagement": row.avg_engagement,
                         "top_posts": row.top_posts or [],
                         "checked_at": row.checked_at.isoformat() if row.checked_at else None,
                         "followers_delta": None, "snapshots": 1}
        else:
            # Более старый срез — считаем прирост подписчиков от него.
            entry = seen[key]
            entry["snapshots"] += 1
            if entry["followers_delta"] is None:
                entry["followers_delta"] = entry["followers"] - (row.followers or 0)
    return list(seen.values())


async def competitor_history(platform: str, handle: str, limit: int = 30) -> list[dict]:
    """Динамика одного конкурента по срезам."""
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(Competitor)
            .where(Competitor.platform == platform, Competitor.handle == handle.lstrip("@"))
            .order_by(desc(Competitor.checked_at)).limit(limit))
        rows = list(r.scalars())
    return [{"followers": c.followers, "posts_count": c.posts_count,
             "avg_engagement": c.avg_engagement,
             "checked_at": c.checked_at.isoformat() if c.checked_at else None}
            for c in rows]


async def refresh_all(niche_id: str = "") -> dict:
    """Обновляет срезы всех отслеживаемых конкурентов (джоб раз в неделю)."""
    existing = await tracked_competitors(niche_id)
    if not existing:
        return {"updated": 0, "note": "нет отслеживаемых конкурентов"}
    updated, failed = 0, []
    for c in existing:
        res = await track_competitor(c["platform"], c["handle"], niche_id)
        if res.get("ok"):
            updated += 1
        else:
            failed.append(f"{c['platform']}/{c['handle']}: {res.get('error', '')[:60]}")
    return {"updated": updated, "failed": failed, "total": len(existing)}


async def stop_tracking(platform: str, handle: str) -> int:
    """Перестать следить за конкурентом (история сохраняется)."""
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(Competitor)
            .where(Competitor.platform == platform, Competitor.handle == handle.lstrip("@")))
        n = 0
        for row in r.scalars():
            row.active = False
            n += 1
        await db.commit()
    return n


async def market_context(niche_id: str = "") -> str:
    """Короткая сводка рынка для промптов агентов.

    Даёт стратегу и копирайтеру опору на факты: свежие тренды, рецепт вируса и
    цифры конкурентов — вместо общих рассуждений модели.
    """
    parts = []

    trends = await latest("trends", niche_id)
    if trends and trends.get("summary"):
        parts.append(f"ТРЕНДЫ (от {trends['created_at'][:10]}): {trends['summary'][:600]}")

    viral = await latest("viral", niche_id)
    if viral and viral.get("summary"):
        parts.append(f"РЕЦЕПТ ЗАЛЕТЕВШИХ РОЛИКОВ: {viral['summary'][:600]}")

    comps = await tracked_competitors(niche_id)
    if comps:
        lines = []
        for c in comps[:5]:
            delta = ""
            if c.get("followers_delta"):
                sign = "+" if c["followers_delta"] > 0 else ""
                delta = f" ({sign}{c['followers_delta']} подписчиков)"
            lines.append(f"@{c['handle']} [{c['platform']}]: {c['followers']} подписчиков{delta}, "
                         f"вовлечённость {c['avg_engagement']}%")
        parts.append("КОНКУРЕНТЫ:\n" + "\n".join(lines))

    return "\n\n".join(parts)
