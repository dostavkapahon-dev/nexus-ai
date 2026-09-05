"""Higgsfield REST: настоящие адреса, тело запроса и опрос задачи.

Раньше модуль стучался в выдуманные `/v1/text2video` и `/v1/jobs/{id}` — генерация
не работала ни при каких ключах. Здесь это закреплено: адреса и форма запроса
сверены с официальным SDK @higgsfield/client.
"""
import json
import pytest
import httpx

from core import higgsfield as hf


@pytest.fixture(autouse=True)
def _creds(monkeypatch):
    for var in ("HF_KEY", "HF_API_KEY", "HF_API_SECRET", "HF_SECRET",
                "HIGGSFIELD_API_BASE", "HIGGSFIELD_MODEL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "k")
    monkeypatch.setenv("HIGGSFIELD_SECRET", "s")


class _Fake:
    """Подменяет httpx.AsyncClient и записывает, что именно ушло в сеть."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, *a, **kw):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def _respond(self, method, url, json_body=None):
        self.calls.append({"method": method, "url": url, "json": json_body})
        for path, resp in self.routes.items():
            if path in url:
                status, payload = resp
                return httpx.Response(status, json=payload,
                                      request=httpx.Request(method, url))
        raise AssertionError(f"неожиданный адрес: {url}")

    async def post(self, url, headers=None, json=None):
        self.headers = headers
        return self._respond("POST", url, json)

    async def get(self, url, headers=None):
        self.headers = headers
        return self._respond("GET", url)


def _install(monkeypatch, routes):
    fake = _Fake(routes)
    monkeypatch.setattr(httpx, "AsyncClient", fake)
    return fake


DONE = {"id": "js1", "jobs": [{"id": "j1", "status": "completed",
                               "results": {"raw": {"url": "https://cdn/x.png"}}}]}


@pytest.mark.asyncio
async def test_image_goes_to_the_real_soul_endpoint(monkeypatch):
    fake = _install(monkeypatch, {"/v1/text2image/soul": (200, {"id": "js1"}),
                                  "/v1/job-sets/js1": (200, DONE)})

    res = await hf.generate_image("кофе на рассвете", ratio="9:16")

    assert res == {"ok": True, "url": "https://cdn/x.png"}
    post = fake.calls[0]
    assert post["url"] == "https://platform.higgsfield.ai/v1/text2image/soul"
    # Тело — {"params": {...}}, а размер именно разрешением: «9:16» платформа
    # не принимает.
    assert post["json"]["params"]["width_and_height"] == "1152x2048"
    assert post["json"]["params"]["prompt"] == "кофе на рассвете"
    assert fake.calls[1]["url"].endswith("/v1/job-sets/js1")


@pytest.mark.asyncio
async def test_text_to_video_draws_a_frame_first(monkeypatch):
    """DoP — это image2video: без кадра он работать не может, и раньше именно
    здесь цепочка обрывалась. Кадр рисует Soul, затем DoP его оживляет."""
    video = {"id": "js2", "jobs": [{"status": "completed",
                                    "results": {"raw": {"url": "https://cdn/v.mp4"}}}]}
    fake = _install(monkeypatch, {"/v1/text2image/soul": (200, {"id": "js1"}),
                                  "/v1/job-sets/js1": (200, DONE),
                                  "/v1/image2video/dop": (200, {"id": "js2"}),
                                  "/v1/job-sets/js2": (200, video)})

    res = await hf.generate_video("ролик про доставку")

    assert res["ok"] and res["url"] == "https://cdn/v.mp4"
    assert res["preview_image"] == "https://cdn/x.png"
    dop = [c for c in fake.calls if "image2video" in c["url"]][0]
    assert dop["json"]["params"]["model"] == "dop-turbo"
    assert dop["json"]["params"]["input_images"] == [
        {"type": "image_url", "image_url": "https://cdn/x.png"}]


@pytest.mark.asyncio
async def test_rejected_key_says_what_to_fix(monkeypatch):
    _install(monkeypatch, {"/v1/text2image/soul": (401, {"detail": "bad key"})})

    res = await hf.generate_image("кот")

    assert res["ok"] is False
    assert "401" in res["error"] and "ключ" in res["error"].lower()


@pytest.mark.asyncio
async def test_no_credits_is_not_reported_as_success(monkeypatch):
    _install(monkeypatch, {"/v1/text2image/soul": (403, {"detail": "no credits"})})

    res = await hf.generate_image("кот")
    assert res["ok"] is False and "кредит" in res["error"]


@pytest.mark.asyncio
async def test_failed_job_stops_polling(monkeypatch):
    failed = {"id": "js1", "jobs": [{"status": "failed"}]}
    _install(monkeypatch, {"/v1/text2image/soul": (200, {"id": "js1"}),
                           "/v1/job-sets/js1": (200, failed)})

    res = await hf.generate_image("кот")
    assert res["ok"] is False and "не удалась" in res["error"]


@pytest.mark.asyncio
async def test_live_check_uses_a_real_request(monkeypatch):
    """§29: Connected должно означать «запрос прошёл», а не «ключ вписан»."""
    _install(monkeypatch, {"/v1/text2image/soul-styles": (200, [{"id": "s1"}])})
    assert (await hf.check())["ok"] is True

    _install(monkeypatch, {"/v1/text2image/soul-styles": (401, {"detail": "nope"})})
    bad = await hf.check()
    assert bad["ok"] is False and "401" in bad["error"]


@pytest.mark.asyncio
async def test_hixiit_uses_higgsfield_for_images(monkeypatch):
    """§14: картинка должна идти через Higgsfield, а не сразу на бесплатный путь."""
    from core import hixiit

    monkeypatch.delenv("HIGGSFIELD_MCP_URL", raising=False)
    _install(monkeypatch, {"/v1/text2image/soul": (200, {"id": "js1"}),
                           "/v1/job-sets/js1": (200, DONE)})

    res = await hixiit.generate("обложка про кофе", kind="image")

    assert res["ok"] and res["provider"] == "higgsfield_api"
    assert res["url"] == "https://cdn/x.png"
    assert res["model"] == "soul"
