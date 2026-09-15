"""Запрос картинки собирается по официальной схеме, а не по догадке.

История ошибки — важнее самой проверки. «400: Unavailable model» дважды
объясняли неверно: сперва решили, что модель не передаётся вовсе и её надо
добавить; потом — что каталог аккаунта сменился и имена устарели. Обе версии
были догадками, и обе не работали.

Официальная схема SDK Higgsfield (`SoulText2ImageInput`) поля `model` не
содержит: там prompt, width_and_height, quality ('720p'|'1080p'), batch_size
(1|4) и необязательные style_id / style_strength / seed / enhance_prompt.
Платформа отвечала «Unavailable model» именно потому, что мы слали лишнее поле.
Стиль здесь задаётся style_id из /v1/text2image/soul-styles, а не именем модели.
"""
import pytest

from core import higgsfield as hf

UUID_A = "3f8c1a2b-4d5e-6f70-8192-a3b4c5d6e7f8"
SECRET = "8f" * 32


@pytest.fixture(autouse=True)
def creds(monkeypatch):
    for k in ("HF_KEY", "HF_API_KEY", "HF_SECRET", "HF_API_SECRET",
              "HIGGSFIELD_IMAGE_MODEL", "HIGGSFIELD_STYLE_ID"):
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
async def test_model_field_is_never_sent(monkeypatch):
    """Именно это поле и вызывало «Unavailable model»."""
    sent = _post_recorder(monkeypatch, [{"ok": True, "job_id": "j1"}])
    await hf.create_image("шашлык", ratio="9:16")
    assert "model" not in sent[0]


@pytest.mark.asyncio
async def test_required_fields_match_the_sdk_schema(monkeypatch):
    sent = _post_recorder(monkeypatch, [{"ok": True, "job_id": "j1"}])
    await hf.create_image("шашлык", ratio="9:16")
    body = sent[0]
    assert set(body) <= {"prompt", "width_and_height", "quality", "batch_size",
                         "style_id", "style_strength", "seed", "enhance_prompt"}
    assert body["prompt"] and body["width_and_height"]
    assert body["quality"] in ("720p", "1080p")
    assert body["batch_size"] in (1, 4)


@pytest.mark.asyncio
async def test_quality_values_are_the_endpoint_ones(monkeypatch):
    """У модели в каталоге качество зовётся 1.5k/2k — у эндпоинта иначе."""
    sent = _post_recorder(monkeypatch, [
        {"ok": False, "error": "Higgsfield отверг параметры (422): "
                               "Input should be '720p' or '1080p'"},
        {"ok": True, "job_id": "j2"},
    ])
    res = await hf.create_image("шашлык")
    assert res["ok"] is True
    assert {s["quality"] for s in sent} <= {"720p", "1080p"}
    assert sent[0]["quality"] != sent[1]["quality"]


@pytest.mark.asyncio
async def test_style_is_sent_only_when_asked_for(monkeypatch):
    sent = _post_recorder(monkeypatch, [{"ok": True, "job_id": "j1"}])
    await hf.create_image("шашлык")
    assert "style_id" not in sent[0]

    monkeypatch.setenv("HIGGSFIELD_STYLE_ID", "style-123")
    hf._working_image_params = {}
    sent2 = _post_recorder(monkeypatch, [{"ok": True, "job_id": "j2"}])
    await hf.create_image("шашлык")
    assert sent2[0]["style_id"] == "style-123"


@pytest.mark.asyncio
async def test_working_params_are_tried_first_next_time(monkeypatch):
    sent = _post_recorder(monkeypatch, [
        {"ok": False, "error": "Higgsfield отверг параметры (422)"},
        {"ok": True, "job_id": "j2"},
    ])
    await hf.create_image("первый кадр")
    worked = sent[-1]["quality"]

    sent2 = _post_recorder(monkeypatch, [{"ok": True, "job_id": "j3"}])
    await hf.create_image("второй кадр")
    assert sent2[0]["quality"] == worked, "рабочий набор должен идти первым"


@pytest.mark.asyncio
async def test_rejection_that_is_not_about_params_stops_the_sweep(monkeypatch):
    """Отказ по ключу перебором не лечится — он только прячет причину."""
    sent = _post_recorder(monkeypatch, [
        {"ok": False, "error": "Higgsfield: неверный ключ (401)"},
        {"ok": True, "job_id": "j2"},
    ])
    res = await hf.create_image("шашлык")
    assert res["ok"] is False and len(sent) == 1
