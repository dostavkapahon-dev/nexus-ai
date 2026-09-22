"""Повторная отправка не должна упираться в истёкшую ссылку провайдера.

§50 ТЗ: Telegram — интерфейс, а не хранилище; сбой доставки не повод
генерировать заново. Но повторная отправка шла по ссылке провайдера, а она
живёт часы. Через сутки — ровно тогда, когда повтор и нужен — Telegram отвечал
отказом, и «результат сохранён» оказывалось неправдой при живой копии в архиве.
"""
import pytest

from core import artifacts, drive_store
from publishers import telegram_pub


@pytest.fixture
def kv(monkeypatch):
    store = {}

    async def _get(key):
        return store.get(key, "")

    async def _set(key, value):
        store[key] = value

    monkeypatch.setattr(artifacts, "_kv_get", _get)
    monkeypatch.setattr(artifacts, "_kv_set", _set)
    return store


@pytest.mark.asyncio
async def test_expired_link_falls_back_to_archive(kv, monkeypatch):
    art_id = await artifacts.save(url="https://cdn.example/dead.png", kind="image",
                                  provider="higgsfield", model="gpt_image_2_5",
                                  prompt="шашлык на мангале")
    await artifacts.mark(art_id, storage="https://drive.example/file/d/FID/view",
                         storage_id="FID")

    async def dead_photo(chat_id, photo, caption="", **kw):
        return {"ok": False, "error": "wrong file identifier/HTTP URL specified"}

    sent = {}

    async def fake_download(file_id):
        assert file_id == "FID"
        return {"ok": True, "data": b"PNG-BYTES"}

    async def fake_send_file(chat_id, data, kind="image", caption="", **kw):
        sent.update({"chat": chat_id, "data": data, "kind": kind})
        return {"ok": True}

    monkeypatch.setattr(telegram_pub, "send_photo", dead_photo)
    monkeypatch.setattr(drive_store, "download", fake_download)
    monkeypatch.setattr(telegram_pub, "send_file", fake_send_file)

    res = await artifacts.redeliver(art_id, "123")
    assert res["ok"], res
    assert res.get("from_archive"), "отправить должна была копия из архива"
    assert sent["data"] == b"PNG-BYTES"
    row = await artifacts.get(art_id)
    assert row["telegram"] == "доставлено повторно из архива"


@pytest.mark.asyncio
async def test_no_copy_says_so_and_never_regenerates(kv, monkeypatch):
    art_id = await artifacts.save(url="https://cdn.example/dead.png", kind="image")

    async def dead_photo(chat_id, photo, caption="", **kw):
        return {"ok": False, "error": "wrong file identifier"}

    monkeypatch.setattr(telegram_pub, "send_photo", dead_photo)
    res = await artifacts.redeliver(art_id, "123")
    assert not res["ok"]
    assert "архив" in res["error"], res["error"]


@pytest.mark.asyncio
async def test_working_link_is_used_as_before(kv, monkeypatch):
    art_id = await artifacts.save(url="https://cdn.example/live.png", kind="image")
    calls = []

    async def ok_photo(chat_id, photo, caption="", **kw):
        calls.append(photo)
        return {"ok": True}

    async def never(*a, **k):
        raise AssertionError("живая ссылка не должна трогать архив")

    monkeypatch.setattr(telegram_pub, "send_photo", ok_photo)
    monkeypatch.setattr(drive_store, "download", never)
    res = await artifacts.redeliver(art_id, "123")
    assert res["ok"] and calls == ["https://cdn.example/live.png"]
