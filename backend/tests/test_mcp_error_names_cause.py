"""MCPError печатается как «Server returned an error response» — по такому
тексту нельзя понять ничего. Код, сообщение сервера и data обязаны доезжать.
"""
import asyncio

import pytest

from core.hixiit import _why


def _mcp_error(code=-32603, message="Server returned an error response", data=None):
    from mcp.shared.exceptions import MCPError

    return MCPError(code=code, message=message, data=data)


def test_mcp_error_shows_code():
    assert "code=-32603" in _why(_mcp_error(), 300)


def test_mcp_error_shows_server_data():
    text = _why(_mcp_error(data={"status": 401, "detail": "unauthorized"}), 300)
    assert "401" in text and "unauthorized" in text


def test_mcp_error_keeps_its_message():
    assert "Server returned an error response" in _why(_mcp_error(), 300)


def test_server_message_is_not_duplicated():
    """message и str(err) — это одно и то же, печатать дважды незачем."""
    text = _why(_mcp_error(message="boom"), 300)
    assert text.count("boom") == 1


def test_mcp_error_inside_taskgroup_is_unwrapped():
    async def run():
        async with asyncio.TaskGroup() as tg:
            tg.create_task(_raise())

    async def _raise():
        raise _mcp_error(data={"status": 403})

    with pytest.raises(BaseException) as exc:
        asyncio.run(run())

    text = _why(exc.value, 300)
    assert "ExceptionGroup" not in text
    assert "403" in text


def test_http_status_error_shows_status_and_body():
    httpx = pytest.importorskip("httpx")
    request = httpx.Request("POST", "https://example.test/x")
    response = httpx.Response(401, text="Invalid credentials", request=request)
    err = httpx.HTTPStatusError("bad", request=request, response=response)

    text = _why(err, 300)
    assert "HTTP 401" in text and "Invalid credentials" in text


def test_plain_exception_has_no_parentheses_noise():
    assert _why(RuntimeError("простая ошибка"), 300) == "RuntimeError: простая ошибка"
