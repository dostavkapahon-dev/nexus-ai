"""Архив в Google Drive: подключение доказывается кругом запись→чтение→удаление.

Прежний статус писал «Google Drive ✓» по факту наличия токена. Это неправда
дважды: пользовательский OAuth-токен живёт около часа и refresh-токена рядом не
хранится, а у папки может не быть доступа. Здесь зелёным считается только
пройденный круг.
"""
import json

import pytest

from core import drive_store as ds

SA = json.dumps({"client_email": "nexus@project.iam.gserviceaccount.com",
                 "private_key": "x", "type": "service_account"})


def test_missing_key_is_named(monkeypatch):
    monkeypatch.delenv(ds.SA_ENV, raising=False)
    res = ds.configured()
    assert res["ok"] is False and ds.SA_ENV in res["why"]


def test_missing_folder_explains_why_it_is_needed(monkeypatch):
    monkeypatch.setenv(ds.SA_ENV, SA)
    monkeypatch.delenv(ds.ROOT_ENV, raising=False)
    res = ds.configured()
    assert res["ok"] is False
    assert "нет своего места" in res["why"], "иначе непонятно, зачем папка"


def test_account_email_is_shown(monkeypatch):
    """Этот адрес человек вставляет в доступ к папке — без него не подключиться."""
    monkeypatch.setenv(ds.SA_ENV, SA)
    assert ds.account_email() == "nexus@project.iam.gserviceaccount.com"


def test_folders_are_separated_by_kind():
    assert ds.FOLDERS["image"] == ("Generated", "Images")
    assert ds.FOLDERS["video"] == ("Generated", "Videos")
    assert ds.FOLDERS["image"] != ds.FOLDERS["video"]


@pytest.mark.asyncio
async def test_quota_error_explains_the_real_cause(monkeypatch):
    """«storageQuotaExceeded» непонятно; причина — папка не расшарена."""
    monkeypatch.setenv(ds.SA_ENV, SA)
    monkeypatch.setenv(ds.ROOT_ENV, "folder-1")

    async def fake_service():
        return object()

    async def fake_upload(data, name, kind="image", mime=""):
        return {"ok": False, "error": "HttpError: storageQuotaExceeded"}

    monkeypatch.setattr(ds, "_service", fake_service)
    monkeypatch.setattr(ds, "upload_bytes", fake_upload)
    res = await ds.check()
    assert res["ok"] is False
    assert "расшарена" in res["error"] and "nexus@project" in res["error"]


@pytest.mark.asyncio
async def test_check_is_green_only_after_reading_back(monkeypatch):
    monkeypatch.setenv(ds.SA_ENV, SA)
    monkeypatch.setenv(ds.ROOT_ENV, "folder-1")
    deleted = []

    class _Files:
        def create(self, **kw):
            raise AssertionError("не используется в этом тесте")

        def get(self, fileId, fields=""):
            class _R:
                def execute(self_inner):
                    return {"id": fileId, "name": "nexus_check.txt"}
            return _R()

        def delete(self, fileId):
            deleted.append(fileId)

            class _R:
                def execute(self_inner):
                    return {}
            return _R()

    class _Service:
        def files(self):
            return _Files()

    async def fake_service():
        return _Service()

    async def fake_upload(data, name, kind="image", mime=""):
        return {"ok": True, "id": "file-1", "link": "https://drive/file-1"}

    monkeypatch.setattr(ds, "_service", fake_service)
    monkeypatch.setattr(ds, "upload_bytes", fake_upload)
    res = await ds.check()
    assert res["ok"] is True and res["stage"] == "готово"
    assert deleted == ["file-1"], "проверочный файл не должен оставаться в архиве"


@pytest.mark.asyncio
async def test_download_failure_is_named(monkeypatch):
    monkeypatch.setenv(ds.SA_ENV, SA)
    monkeypatch.setenv(ds.ROOT_ENV, "folder-1")

    class _R:
        status_code = 404
        content = b""
        headers = {}

    class _C:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            return _R()

    monkeypatch.setattr("httpx.AsyncClient", _C)
    res = await ds.upload_url("https://cdn/x.png", "x.png", "image")
    assert res["ok"] is False and "404" in res["error"]


@pytest.mark.asyncio
async def test_generation_survives_a_broken_archive(monkeypatch):
    """Архив — это учёт. Его отказ не имеет права отменить готовый результат."""
    from core import hixiit

    async def boom(url, name, kind="image"):
        raise RuntimeError("Drive недоступен")

    monkeypatch.setattr(ds, "configured", lambda: {"ok": True, "why": ""})
    monkeypatch.setattr(ds, "upload_url", boom)
    res = {"ok": True, "url": "https://cdn/x.png", "kind": "image",
           "artifact_id": "ART-1"}
    await hixiit._archive(res)
    assert res["ok"] is True and "drive_link" not in res


@pytest.mark.asyncio
async def test_archive_is_skipped_when_not_configured(monkeypatch):
    from core import hixiit

    async def must_not_run(*a, **k):
        raise AssertionError("без настройки в Drive не ходим")

    monkeypatch.setattr(ds, "configured", lambda: {"ok": False, "why": "нет ключа"})
    monkeypatch.setattr(ds, "upload_url", must_not_run)
    await hixiit._archive({"ok": True, "url": "https://cdn/x.png", "kind": "image"})
