"""Качество картинки: значения REST-эндпоинта и перебор по 422.

Живой отказ: «Higgsfield отверг параметры (422): Input should be '720p' or
'1080p'». Два дефекта сразу. Первый — слали «2k», это значение из каталога MCP,
у REST свой набор. Второй — перебор наборов шёл только по 400, а 422 обрывал
его сразу, поэтому второй вариант не пробовался никогда.

При этом 422 про заголовок — это отказ по ключу, и перебирать модели там
бессмысленно: он только сожжёт запросы и спрячет причину.
"""
import pytest

from core import higgsfield as hf


def test_qualities_are_rest_values():
    assert hf.IMAGE_QUALITIES == ("1080p", "720p")
    assert "2k" not in hf.IMAGE_QUALITIES


def test_422_about_params_continues_search():
    assert hf._params_rejected("Higgsfield отверг параметры (422): "
                               "Input should be '720p' or '1080p'")


def test_400_still_continues_search():
    assert hf._params_rejected("Higgsfield вернул 400: Unavailable model")


def test_422_about_header_stops_search():
    """Ключ не чинится перебором моделей."""
    assert not hf._params_rejected(
        '422: {"detail":[{"type":"uuid_parsing","loc":["header","hf-api-key"]}]}')


def test_401_stops_search():
    assert not hf._params_rejected("Higgsfield вернул 401: Invalid credentials")


@pytest.mark.asyncio
async def test_second_quality_is_tried_after_422(monkeypatch):
    """Главный дефект: после 422 на первом наборе второй не пробовался."""
    seen = []

    async def fake_post(path, body):
        seen.append(body["quality"])
        if body["quality"] == "1080p":
            return {"ok": False, "error": "Higgsfield отверг параметры (422): "
                                          "Input should be '720p'"}
        return {"ok": True, "job_set_id": "abc"}

    monkeypatch.setattr(hf, "_post", fake_post)
    monkeypatch.setattr(hf, "_working_image_params", {})
    res = await hf.create_image("шашлык")
    assert res["ok"]
    assert len(seen) >= 2


@pytest.mark.asyncio
async def test_bad_key_does_not_burn_requests(monkeypatch):
    calls = []

    async def fake_post(path, body):
        calls.append(body)
        return {"ok": False, "error": '422: loc: ["header","hf-api-key"]'}

    monkeypatch.setattr(hf, "_post", fake_post)
    monkeypatch.setattr(hf, "_working_image_params", {})
    res = await hf.create_image("шашлык")
    assert not res["ok"]
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_working_set_is_remembered(monkeypatch):
    async def fake_post(path, body):
        if body["quality"] == "1080p":
            return {"ok": False, "error": "422: Input should be '720p'"}
        return {"ok": True, "job_set_id": "abc"}

    monkeypatch.setattr(hf, "_post", fake_post)
    monkeypatch.setattr(hf, "_working_image_params", {})
    await hf.create_image("шашлык")
    assert hf._working_image_params.get("quality") == "720p"
