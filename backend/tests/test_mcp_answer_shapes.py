"""Ответ MCP приходит в разных формах — и ни одна не должна ронять генерацию.

С сервера пришло: `AttributeError: 'str' object has no attribute 'get'`. Код
читал ответ инструмента как словарь безусловно, а платформа отвечала строкой.
Ошибка вылетала из середины генерации и не говорила ничего: ни какой инструмент
ответил, ни что именно он сказал.
"""
import pytest

from core import hixiit


def test_dict_passes_through():
    assert hixiit._as_dict({"jobs": []}) == {"jobs": []}


def test_json_string_is_parsed():
    assert hixiit._as_dict('{"items": [1]}') == {"items": [1]}


def test_plain_text_is_not_a_crash():
    assert hixiit._as_dict("платформа недоступна") == {}
    assert hixiit._as_dict(None) == {}
    assert hixiit._as_dict([1, 2]) == {}


def test_result_envelope_is_unwrapped():
    """Платформа иногда кладёт нагрузку строкой внутрь {"result": ...}."""
    assert hixiit._as_dict({"result": '{"items": [1]}'}) == {"items": [1]}


@pytest.mark.asyncio
async def test_text_answer_names_itself_instead_of_AttributeError(monkeypatch):
    async def text_answer(tool, args, timeout=600.0):
        if tool == "models_explore":
            return {"items": [{"id": "soul_2"}], "unlim": {"available": False}}
        return "Rate limit exceeded, try again later"

    async def picked(*a, **kw):
        return {"id": "soul_2"}

    monkeypatch.setattr(hixiit, "mcp_configured", lambda: True)
    monkeypatch.setattr(hixiit, "_mcp_call", text_answer)
    monkeypatch.setattr(hixiit, "pick_model", picked)

    with pytest.raises(RuntimeError, match="Rate limit"):
        await hixiit._generate_via_mcp_inner("шашлык", "image", "9:16")


@pytest.mark.asyncio
async def test_unlim_survives_a_text_answer(monkeypatch):
    async def text_answer(tool, args, timeout=600.0):
        return "сервис перегружен"

    monkeypatch.setattr(hixiit, "mcp_configured", lambda: True)
    monkeypatch.setattr(hixiit, "_mcp_call", text_answer)
    out = await hixiit.unlim_status()
    assert out["available"] is False        # но не падение


@pytest.mark.asyncio
async def test_job_polling_survives_a_text_answer(monkeypatch):
    async def text_answer(tool, args, timeout=600.0):
        return "job is queued"

    monkeypatch.setattr(hixiit, "mcp_configured", lambda: True)
    monkeypatch.setattr(hixiit, "_mcp_call", text_answer)
    monkeypatch.setattr(hixiit, "JOB_POLL_ATTEMPTS", 2)
    with pytest.raises(RuntimeError, match="не отдал результат"):
        await hixiit._wait_job("job-1", attempts=2)


def test_model_list_reads_a_json_string():
    assert hixiit._as_model_list('{"items": [{"id": "soul_2"}]}') == [
        {"id": "soul_2", "name": "soul_2"}]
