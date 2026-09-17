"""Модель Soul подбирается по стилю, а не по имени.

Платформа отвечала «400 Unavailable model» на тело, которое её же схему
проходит (на негодное качество она отвечает 422 с перечнем допустимых
значений). У Soul модель задаёт style_id, и без него у аккаунта не остаётся
умолчания. Проверяем: такой отказ приводит к запросу каталога стилей и
повтору — а не к молчаливому «не генерируется».
"""
import pytest

from core import higgsfield as hf

UUID_A = "3f8c1a2b-4d5e-6f70-8192-a3b4c5d6e7f8"
SECRET = "8f" * 32
STYLE = "11111111-2222-3333-4444-555555555555"


@pytest.fixture(autouse=True)
def creds(monkeypatch):
    monkeypatch.setenv("HIGGSFIELD_API_KEY", UUID_A)
    monkeypatch.setenv("HIGGSFIELD_SECRET", SECRET)
    monkeypatch.delenv("HIGGSFIELD_STYLE_ID", raising=False)
    hf._styles_cache = []
    hf._working_image_params = {}


def _fake(monkeypatch, posts, styles_status=200,
          styles_payload=None):
    """posts — очередь ответов на POST: (status, payload)."""
    sent: list = []

    class _R:
        def __init__(self, status, payload):
            self.status_code = status
            self._p = payload

        def json(self):
            return self._p

        @property
        def text(self):
            return str(self._p)

    class _C:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            sent.append(dict(json["params"]))  # копия: тело потом дополняется
            status, payload = posts.pop(0)
            return _R(status, payload)

        async def get(self, url, headers=None):
            return _R(styles_status,
                      styles_payload
                      if styles_payload is not None
                      else {"items": [{"id": STYLE, "name": "Editorial"}]})

    monkeypatch.setattr("httpx.AsyncClient", _C)
    return sent


@pytest.mark.asyncio
async def test_unavailable_model_retries_with_style(monkeypatch):
    sent = _fake(monkeypatch, [(400, {"detail": "Unavailable model"}),
                               (200, {"id": "job-7"})])
    res = await hf.create_image("кадр")
    assert res["ok"] is True and res["job_id"] == "job-7"
    assert "style_id" not in sent[0], "первый запрос — без выдуманного стиля"
    assert sent[1]["style_id"] == STYLE, "повтор должен нести стиль из каталога"


@pytest.mark.asyncio
async def test_style_from_env_wins_and_needs_no_catalog(monkeypatch):
    monkeypatch.setenv("HIGGSFIELD_STYLE_ID", "мой-стиль")
    sent = _fake(monkeypatch, [(200, {"id": "job-8"})])
    res = await hf.create_image("кадр")
    assert res["ok"] is True
    assert sent[0]["style_id"] == "мой-стиль"


@pytest.mark.asyncio
async def test_catalog_failure_keeps_the_real_reason(monkeypatch):
    """Если стилей нет, человек должен увидеть отказ платформы, а не наш."""
    _fake(monkeypatch, [(400, {"detail": "Unavailable model"}),
                        (400, {"detail": "Unavailable model"})],
          styles_status=403)
    res = await hf.create_image("кадр")
    assert res["ok"] is False
    assert "Unavailable model" in res["error"]


@pytest.mark.asyncio
async def test_styles_are_cached(monkeypatch):
    _fake(monkeypatch, [(400, {"detail": "Unavailable model"}),
                        (200, {"id": "job-9"})])
    first = await hf.soul_styles()
    assert first["ok"] and first["items"][0]["id"] == STYLE
    second = await hf.soul_styles()
    assert second.get("cached") is True


@pytest.mark.asyncio
async def test_empty_catalog_is_not_silent(monkeypatch):
    _fake(monkeypatch, [(400, {"detail": "Unavailable model"})],
          styles_payload={"items": []})
    res = await hf.soul_styles()
    assert res["ok"] is False and "стил" in res["error"].lower()
