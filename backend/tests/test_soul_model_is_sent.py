"""
`400: Unavailable model` — модель не передавалась вовсе.

С живого сервера: `REST: Higgsfield вернул 400: Unavailable model`. Запрос к
/v1/text2image/soul уходил без поля `model`, платформа брала умолчание, а в
каталоге аккаунта такой модели нет: там soul_2 / soul_v2 / soul_cinematic, но
НЕ «soul». Значения quality у Soul тоже свои — 1.5k/2k, а не 720p/1080p.
"""
import pytest

from core import higgsfield as hf

UUID_A = "3f8c1a2b-4d5e-6f70-8192-a3b4c5d6e7f8"
SECRET = "8f" * 32


@pytest.fixture(autouse=True)
def creds(monkeypatch):
    for k in ("HF_KEY", "HF_API_KEY", "HF_SECRET", "HF_API_SECRET",
              "HIGGSFIELD_IMAGE_MODEL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("HIGGSFIELD_API_KEY", UUID_A)
    monkeypatch.setenv("HIGGSFIELD_SECRET", SECRET)
    hf._working_image_params = {}


def _post_recorder(monkeypatch, results):
    sent = []

    async def fake_post(path, params):
        sent.append(params)
        return results[min(len(sent) - 1, len(results) - 1)]

    monkeypatch.setattr(hf, "_post", fake_post)
    return sent


@pytest.mark.asyncio
async def test_model_is_always_sent(monkeypatch):
    sent = _post_recorder(monkeypatch, [{"ok": True, "job_id": "j1"}])

    await hf.create_image("шашлык", ratio="9:16")

    assert sent[0]["model"] in hf.IMAGE_MODELS_REST, \
        "без модели платформа отвечает Unavailable model"


@pytest.mark.asyncio
async def test_unavailable_model_falls_through_to_the_next(monkeypatch):
    sent = _post_recorder(monkeypatch, [
        {"ok": False, "error": "Higgsfield вернул 400: Unavailable model"},
        {"ok": True, "job_id": "j2"},
    ])

    res = await hf.create_image("шашлык")

    assert res["ok"] is True
    assert len(sent) == 2, "второй набор параметров должен быть испробован"
    assert sent[0] != sent[1]


@pytest.mark.asyncio
async def test_working_set_is_remembered(monkeypatch):
    _post_recorder(monkeypatch, [
        {"ok": False, "error": "400: Unavailable model"},
        {"ok": True, "job_id": "j2"},
    ])
    await hf.create_image("первый кадр")
    working = dict(hf._working_image_params)

    sent = _post_recorder(monkeypatch, [{"ok": True, "job_id": "j3"}])
    await hf.create_image("второй кадр")

    assert len(sent) == 1, "перебор повторять незачем"
    assert sent[0]["model"] == working["model"]


@pytest.mark.asyncio
async def test_non_400_error_stops_the_search(monkeypatch):
    """401 или 500 перебором параметров не лечится — только лишние запросы."""
    sent = _post_recorder(monkeypatch, [
        {"ok": False, "error": "Higgsfield не принял ключ (401)"},
    ])

    res = await hf.create_image("шашлык")

    assert res["ok"] is False
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_explicit_env_model_wins(monkeypatch):
    monkeypatch.setenv("HIGGSFIELD_IMAGE_MODEL", "soul_cinematic")
    sent = _post_recorder(monkeypatch, [{"ok": True, "job_id": "j1"}])

    await hf.create_image("кинокадр")

    assert sent[0]["model"] == "soul_cinematic", "явная настройка важнее перебора"


@pytest.mark.asyncio
async def test_soul_is_never_sent(monkeypatch):
    """Именно этот id и вызывал отказ: в каталоге аккаунта его нет."""
    sent = _post_recorder(monkeypatch, [
        {"ok": False, "error": "400: Unavailable model"}] * 5)

    await hf.create_image("шашлык")

    assert all(p["model"] != "soul" for p in sent)
