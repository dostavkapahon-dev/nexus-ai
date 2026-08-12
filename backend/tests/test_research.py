"""История исследований и отслеживание конкурентов."""
import pytest
from sqlalchemy import delete

from core import research_store as rs
from database.db import AsyncSessionLocal
from database.models import Research, Competitor


@pytest.fixture(autouse=True)
async def _clean(client):
    """БД общая на прогон — чистим, чтобы проверки не зависели от соседних тестов."""
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Research))
        await db.execute(delete(Competitor))
        await db.commit()
    yield


@pytest.mark.asyncio
async def test_research_history_keeps_every_run(client):
    """Раньше результат жил в одном KV-ключе и перезатирался — теперь копится история."""
    await rs.save("trends", query="доставка", summary="первый прогон")
    await rs.save("trends", query="доставка", summary="второй прогон")

    items = await rs.history("trends")
    assert len(items) == 2
    # Свежее — первым
    assert items[0]["summary"] == "второй прогон"

    last = await rs.latest("trends")
    assert last["summary"] == "второй прогон"


@pytest.mark.asyncio
async def test_research_binds_to_running_task(client):
    """Исследование должно приписываться задаче, из которой запущено."""
    from core import task_manager as tm

    task_id = await tm.create("director", "разведка")

    async def work():
        await rs.save("viral", query="url", summary="рецепт")
        return {"ok": True}

    await tm.run(task_id, work)

    items = await rs.history("viral")
    assert items[0]["task_id"] == task_id


@pytest.mark.asyncio
async def test_history_filters_by_kind_and_niche(client):
    await rs.save("trends", summary="t", niche_id="n1")
    await rs.save("viral", summary="v", niche_id="n1")
    await rs.save("trends", summary="other", niche_id="n2")

    assert len(await rs.history("trends")) == 2
    assert len(await rs.history("trends", niche_id="n1")) == 1
    assert len(await rs.history(niche_id="n1")) == 2


@pytest.mark.asyncio
async def test_stats_counts_by_kind(client):
    await rs.save("trends", summary="a")
    await rs.save("trends", summary="b")
    await rs.save("competitor", summary="c")

    st = await rs.stats()
    assert st["total"] == 3
    assert st["by_kind"]["trends"] == 2
    assert st["last_at"] is not None


def test_avg_engagement_handles_missing_data():
    posts = [{"likes": 100, "comments": 20}, {"likes": 200, "comments": 40}]
    # (120 + 240) / 2 / 10000 * 100 = 1.8 %
    assert rs._avg_engagement(posts, 10000) == 1.8
    assert rs._avg_engagement([], 10000) == 0.0
    assert rs._avg_engagement(posts, 0) == 0.0       # без подписчиков не делим на ноль


@pytest.mark.asyncio
async def test_track_competitor_saves_snapshot(client, monkeypatch):
    async def fake_fetch(platform, handle, n=12):
        return {"ok": True, "followers": 50000, "posts_count": 300,
                "top_posts": [{"likes": 1000, "comments": 100, "title": "их хит"}]}

    import core.social_intel as si
    monkeypatch.setattr(si, "_fetch_channel", fake_fetch)

    res = await rs.track_competitor("youtube", "@rival")
    assert res["ok"] is True
    assert res["handle"] == "rival"          # собачка отброшена
    assert res["followers"] == 50000
    assert res["avg_engagement"] == 2.2      # 1100/50000*100

    comps = await rs.tracked_competitors()
    assert len(comps) == 1
    assert comps[0]["handle"] == "rival"


@pytest.mark.asyncio
async def test_competitor_snapshots_show_growth(client, monkeypatch):
    """Смысл истории: видеть динамику, а не только снимок сегодня."""
    followers = {"n": 1000}

    async def fake_fetch(platform, handle, n=12):
        return {"ok": True, "followers": followers["n"], "posts_count": 10, "top_posts": []}

    import core.social_intel as si
    monkeypatch.setattr(si, "_fetch_channel", fake_fetch)

    await rs.track_competitor("tiktok", "rival")
    followers["n"] = 1500
    await rs.track_competitor("tiktok", "rival")

    comps = await rs.tracked_competitors()
    assert comps[0]["followers"] == 1500
    assert comps[0]["followers_delta"] == 500     # прирост от прошлого среза
    assert comps[0]["snapshots"] == 2

    hist = await rs.competitor_history("tiktok", "rival")
    assert [h["followers"] for h in hist] == [1500, 1000]


@pytest.mark.asyncio
async def test_track_competitor_reports_failure_honestly(client, monkeypatch):
    async def fake_fetch(platform, handle, n=12):
        return {"ok": False, "error": "аккаунт закрыт"}

    import core.social_intel as si
    monkeypatch.setattr(si, "_fetch_channel", fake_fetch)

    res = await rs.track_competitor("tiktok", "private")
    assert res["ok"] is False
    assert "закрыт" in res["error"]
    assert await rs.tracked_competitors() == []      # пустышку не сохраняем


@pytest.mark.asyncio
async def test_stop_tracking_keeps_history(client, monkeypatch):
    async def fake_fetch(platform, handle, n=12):
        return {"ok": True, "followers": 100, "posts_count": 1, "top_posts": []}

    import core.social_intel as si
    monkeypatch.setattr(si, "_fetch_channel", fake_fetch)

    await rs.track_competitor("tiktok", "rival")
    assert await rs.stop_tracking("tiktok", "rival") == 1
    assert await rs.tracked_competitors() == []
    # История при этом остаётся
    assert len(await rs.competitor_history("tiktok", "rival")) == 1


@pytest.mark.asyncio
async def test_market_context_feeds_agents(client, monkeypatch):
    """Сводка рынка — то, что агенты подмешивают в промпт вместо догадок."""
    await rs.save("trends", summary="растёт спрос на доставку")
    await rs.save("viral", summary="хук первой секунды решает")

    # У Instagram свой путь чтения (_fetch_instagram), а не общий _fetch_channel.
    async def fake_ig(handle):
        return {"ok": True, "followers": 9000, "posts_count": 50,
                "top_posts": [{"likes": 90, "comments": 10}]}

    import core.social_intel as si
    monkeypatch.setattr(si, "_fetch_instagram", fake_ig)
    res = await rs.track_competitor("instagram", "rival")
    assert res["ok"] is True

    ctx = await rs.market_context()
    assert "растёт спрос" in ctx
    assert "хук первой секунды" in ctx
    assert "@rival" in ctx


@pytest.mark.asyncio
async def test_market_context_empty_when_nothing_known(client):
    assert await rs.market_context() == ""


@pytest.mark.asyncio
async def test_research_api(auth_client, monkeypatch):
    await rs.save("trends", summary="через api")

    r = await auth_client.get("/api/research", params={"kind": "trends"})
    assert r.status_code == 200
    assert r.json()["items"][0]["summary"] == "через api"

    r2 = await auth_client.get("/api/research/stats")
    assert r2.json()["total"] >= 1

    async def fake_fetch(platform, handle, n=12):
        return {"ok": True, "followers": 777, "posts_count": 5, "top_posts": []}

    import core.social_intel as si
    monkeypatch.setattr(si, "_fetch_channel", fake_fetch)

    r3 = await auth_client.post("/api/research/competitors",
                                json={"platform": "tiktok", "handle": "rival"})
    assert r3.json()["followers"] == 777

    r4 = await auth_client.get("/api/research/competitors")
    assert len(r4.json()["competitors"]) == 1

    r5 = await auth_client.delete("/api/research/competitors/tiktok/rival")
    assert r5.json()["stopped"] == 1


@pytest.mark.asyncio
async def test_api_failure_falls_back_to_free_path(client, monkeypatch):
    """Найдено утечкой окружения между тестами: при заданном, но нерабочем токене
    исключение из основного API обрывало разбор, и бесплатный запасной путь —
    ради которого код и написан — не пробовался вовсе."""
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "протухший")
    monkeypatch.setenv("INSTAGRAM_ACCOUNT_ID", "1784140")

    async def broken(handle):
        raise RuntimeError("403 Forbidden")

    async def free_path(handle):
        return {"ok": True, "followers": 500, "posts_count": 10,
                "top_posts": [{"likes": 50, "comments": 5}]}

    import core.instagram_reader as ir
    import core.social_intel as si
    monkeypatch.setattr(ir, "analyze_competitor", broken)
    monkeypatch.setattr(si, "_fetch_instagram", free_path)

    res = await rs.track_competitor("instagram", "rival")
    assert res["ok"] is True
    assert res["followers"] == 500
