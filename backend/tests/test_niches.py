import pytest

from api import routes_niche

pytestmark = pytest.mark.asyncio


async def _wait_called(calls, expected, tries=50):
    """Пайплайн теперь запускается фоновой задачей — даём ей дойти до вызова."""
    import asyncio
    for _ in range(tries):
        if calls == expected:
            return True
        await asyncio.sleep(0.02)
    return calls == expected


@pytest.fixture(autouse=True)
def _no_pipeline(monkeypatch):
    """Создание ниши стартует полный AI-пайплайн в фоне — в тестах глушим."""
    calls = []

    async def fake(niche_id):
        calls.append(niche_id)

    monkeypatch.setattr(routes_niche.nexus_core, "run_full_pipeline", fake)
    return calls


async def _create(client, **over):
    body = {"name": "Доставка еды", "city": "Ташкент", "platforms": ["telegram"]}
    body.update(over)
    r = await client.post("/api/niches", json=body)
    assert r.status_code == 200, r.text
    return r.json()


async def test_create_niche_defaults(auth_client):
    n = await _create(auth_client)
    assert n["name"] == "Доставка еды"
    assert n["city"] == "Ташкент"
    assert n["goal"] == "subscribers"
    assert n["posts_per_day"] == 1
    assert n["status"] == "active"
    assert n["platforms"] == ["telegram"]
    assert n["id"] and n["created_at"]


async def test_create_triggers_pipeline(auth_client, _no_pipeline):
    n = await _create(auth_client)
    assert await _wait_called(_no_pipeline, [n["id"]])


async def test_get_and_list(auth_client):
    n = await _create(auth_client, name="Барбершоп")
    r = await auth_client.get(f"/api/niches/{n['id']}")
    assert r.status_code == 200
    assert r.json()["name"] == "Барбершоп"

    ids = [x["id"] for x in (await auth_client.get("/api/niches")).json()]
    assert n["id"] in ids


async def test_get_missing_niche_404(auth_client):
    r = await auth_client.get("/api/niches/no-such-id")
    assert r.status_code == 404


async def test_patch_updates_only_given_fields(auth_client):
    n = await _create(auth_client, posts_per_day=3)
    r = await auth_client.patch(f"/api/niches/{n['id']}", json={"status": "paused"})
    assert r.status_code == 200
    upd = r.json()
    assert upd["status"] == "paused"
    assert upd["posts_per_day"] == 3  # не затёрлось


async def test_patch_missing_404(auth_client):
    r = await auth_client.patch("/api/niches/nope", json={"status": "paused"})
    assert r.status_code == 404


async def test_delete_niche(auth_client):
    n = await _create(auth_client)
    assert (await auth_client.delete(f"/api/niches/{n['id']}")).status_code == 200
    assert (await auth_client.get(f"/api/niches/{n['id']}")).status_code == 404


async def test_delete_missing_is_idempotent(auth_client):
    r = await auth_client.delete("/api/niches/nope")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


async def test_plan_empty_for_new_niche(auth_client):
    n = await _create(auth_client)
    r = await auth_client.get(f"/api/niches/{n['id']}/plan")
    assert r.status_code == 200
    assert r.json() == []


async def test_plan_regenerate_endpoint(auth_client, _no_pipeline):
    n = await _create(auth_client)
    # Дожидаемся фоновой задачи от создания ниши, иначе она допишется уже
    # после clear() и исказит проверку.
    await _wait_called(_no_pipeline, [n["id"]])
    _no_pipeline.clear()
    r = await auth_client.post(f"/api/niches/{n['id']}/plan")
    assert r.status_code == 200
    assert await _wait_called(_no_pipeline, [n["id"]])
