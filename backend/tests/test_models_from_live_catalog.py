"""Модели берутся из живого каталога аккаунта, а не из памяти.

Живой отказ повторялся после починки: «400: Unavailable model». Проверка
каталога аккаунта показала, что soul_2 и soul_v2 из него исчезли — код слал
модели, которых у аккаунта больше нет. Доступны recraft_v4_1, z_image,
soul_location и soul_cast (последний только 16:9 и требует персонажа).

Каталог меняется и дальше, поэтому отказ обязан сам объяснять, что делать.
"""
import pytest

from core import higgsfield as hf


def test_retired_models_are_gone():
    """Главный дефект: слали модели, которых у аккаунта нет."""
    assert "soul_2" not in hf.IMAGE_MODELS_REST
    assert "soul_v2" not in hf.IMAGE_MODELS_REST


def test_models_are_from_the_live_catalog():
    for model in hf.IMAGE_MODELS_REST:
        assert model in ("recraft_v4_1", "z_image", "soul_location")


def test_photoreal_model_goes_first():
    """Для соцсетей фотореализм важнее скорости."""
    assert hf.IMAGE_MODELS_REST[0] == "recraft_v4_1"


def test_portrait_only_model_is_excluded():
    """soul_cast умеет только 16:9 — вертикальный кадр им не сделать."""
    assert "soul_cast" not in hf.IMAGE_MODELS_REST


@pytest.mark.asyncio
async def test_all_models_unavailable_explains_what_to_do(monkeypatch):
    async def fake_post(path, body):
        return {"ok": False, "error": "Higgsfield вернул 400: Unavailable model"}

    monkeypatch.setattr(hf, "_post", fake_post)
    monkeypatch.setattr(hf, "_working_image_params", {})
    res = await hf.create_image("шашлык")
    assert not res["ok"]
    assert "HIGGSFIELD_IMAGE_MODEL" in res["error"]
    assert "каталог" in res["error"].lower()


@pytest.mark.asyncio
async def test_other_failures_are_not_dressed_up(monkeypatch):
    """Подсказка про каталог уместна только для своего отказа."""
    async def fake_post(path, body):
        return {"ok": False, "error": "Higgsfield вернул 401: Invalid credentials"}

    monkeypatch.setattr(hf, "_post", fake_post)
    monkeypatch.setattr(hf, "_working_image_params", {})
    res = await hf.create_image("шашлык")
    assert "HIGGSFIELD_IMAGE_MODEL" not in res["error"]


@pytest.mark.asyncio
async def test_override_still_wins(monkeypatch):
    seen = []

    async def fake_post(path, body):
        seen.append(body["model"])
        return {"ok": True, "job_set_id": "x"}

    monkeypatch.setattr(hf, "_post", fake_post)
    monkeypatch.setattr(hf, "_working_image_params", {})
    monkeypatch.setenv("HIGGSFIELD_IMAGE_MODEL", "моя_модель")
    await hf.create_image("шашлык")
    assert seen == ["моя_модель"]
