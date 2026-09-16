"""Созданное не должно зависеть от доставки.

Прежний порядок — «сгенерировали и сразу отправили» — терял результат целиком,
если отправка не прошла: ссылка провайдера живёт недолго, а кредиты уже
списаны. Правильный порядок: генерация → артефакт → хранилище → Telegram.
"""
import pytest

from core import artifacts


@pytest.fixture(autouse=True)
def kv(monkeypatch):
    store = {}

    async def fake_get(key):
        return store.get(key, "")

    async def fake_set(key, value):
        store[key] = value

    monkeypatch.setattr(artifacts, "_kv_get", fake_get)
    monkeypatch.setattr(artifacts, "_kv_set", fake_set)
    return store


@pytest.mark.asyncio
async def test_saved_artifact_can_be_found_again():
    art = await artifacts.save("https://cdn/x.png", "image", provider="higgsfield",
                               model="soul_2", prompt="шашлык")
    row = await artifacts.get(art)
    assert row["url"] == "https://cdn/x.png"
    assert row["model"] == "soul_2" and row["kind"] == "image"


@pytest.mark.asyncio
async def test_delivery_is_recorded_separately():
    art = await artifacts.save("https://cdn/x.png", "image")
    assert (await artifacts.get(art))["telegram"] == ""
    await artifacts.mark(art, telegram="доставлено")
    assert (await artifacts.get(art))["telegram"] == "доставлено"


@pytest.mark.asyncio
async def test_undelivered_are_findable():
    """Главное: то, что не дошло, не пропадает молча."""
    ok = await artifacts.save("https://cdn/ok.png", "image")
    await artifacts.mark(ok, telegram="доставлено")
    await artifacts.save("https://cdn/lost.png", "image")
    lost = await artifacts.undelivered()
    assert [r["url"] for r in lost] == ["https://cdn/lost.png"]


@pytest.mark.asyncio
async def test_recent_is_newest_first():
    first = await artifacts.save("https://cdn/1.png", "image")
    second = await artifacts.save("https://cdn/2.png", "image")
    rows = await artifacts.recent(limit=2)
    assert [r["id"] for r in rows] == [second, first]


@pytest.mark.asyncio
async def test_storage_failure_does_not_break_generation(monkeypatch):
    """Учёт не имеет права уронить саму работу."""
    async def boom(key, value):
        raise RuntimeError("БД недоступна")

    monkeypatch.setattr(artifacts, "_kv_set", boom)
    art = await artifacts.save("https://cdn/x.png", "image")
    assert art.startswith("ART-"), "идентификатор выдаётся даже при сбое записи"


@pytest.mark.asyncio
async def test_generation_creates_the_artifact_first(monkeypatch):
    from core import hixiit, capabilities, model_registry
    order = []

    async def fake_raw(task, kind="auto", ratio=None, image_url=None,
                       allow_free=True, force=False):
        return {"ok": True, "url": "https://cdn/x.png", "kind": "image",
                "model": "soul_2", "provider": "higgsfield_api"}

    async def fake_save(**kw):
        order.append("artifact")
        return "ART-1"

    async def noop(*a, **k):
        return None

    monkeypatch.setattr(hixiit, "_generate_once_raw", fake_raw)
    monkeypatch.setattr(capabilities, "record", noop)
    monkeypatch.setattr(model_registry, "mark_result", noop)
    monkeypatch.setattr(artifacts, "save", fake_save)
    res = await hixiit._generate_once("кадр")
    assert res["artifact_id"] == "ART-1"
    assert order == ["artifact"], "артефакт создаётся до всякой доставки"


@pytest.mark.asyncio
async def test_failed_generation_creates_no_artifact(monkeypatch):
    from core import hixiit, capabilities

    async def fake_raw(task, kind="auto", ratio=None, image_url=None,
                       allow_free=True, force=False):
        return {"ok": False, "error": "все пути отказали"}

    async def must_not_run(**kw):
        raise AssertionError("сохранять нечего")

    async def noop(*a, **k):
        return None

    monkeypatch.setattr(hixiit, "_generate_once_raw", fake_raw)
    monkeypatch.setattr(capabilities, "record", noop)
    monkeypatch.setattr(artifacts, "save", must_not_run)
    res = await hixiit._generate_once("кадр")
    assert "artifact_id" not in res


@pytest.mark.asyncio
async def test_text_marks_what_never_arrived():
    art = await artifacts.save("https://cdn/lost.png", "video")
    text = artifacts.as_text(await artifacts.recent())
    assert "не доставлен" in text and art in text


@pytest.mark.asyncio
async def test_two_results_in_the_same_millisecond_do_not_collide():
    """Два кадра одной задачи создаются в одну миллисекунду.

    Без случайного хвоста второй затирал первый — ровно та потеря результата,
    от которой этот модуль и защищает.
    """
    a = await artifacts.save("https://cdn/1.png", "image")
    b = await artifacts.save("https://cdn/2.png", "image")
    assert a != b
    assert (await artifacts.get(a))["url"] == "https://cdn/1.png"
    assert (await artifacts.get(b))["url"] == "https://cdn/2.png"
