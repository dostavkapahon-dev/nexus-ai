"""
«Вроде настроил» — а ключ не той формы, и этого не видно.

В панели хостинга значение скрыто точками, поэтому лишний пробел, ключ не из
того раздела кабинета или перепутанные местами ключ и секрет выглядят точно так
же, как правильные. `/hixiit` показывал только «задан» и последние 4 символа —
по этому не понять ничего.

Здесь проверяется, что длина и форма значения видны, а само значение — нет.
"""
import pytest

from core import hixiit
from core import telegram_bot as tb

UUID = "3f8c1a2b-4d5e-6f70-8192-a3b4c5d6e7f8"


async def _say(st, monkeypatch):
    sent = []

    async def fake_send(chat_id, text, **kw):
        sent.append(text)
        return {}

    async def fake_status():
        return st

    monkeypatch.setattr(tb, "send_message", fake_send)
    monkeypatch.setattr("core.hixiit.status", fake_status)
    await tb._handle_command("940", "/hixiit")
    return "\n".join(sent)


def _sources(key_len_value, secret_value=UUID):
    from core.higgsfield import _looks_like_uuid
    out = []
    for human, value in (("ключ", key_len_value), ("секрет", secret_value)):
        out.append({"name": human, "env": "X", "filled": bool(value),
                    "source": "переменная хостинга",
                    "tail": value[-4:] if len(value) > 4 else "",
                    "length": len(value), "shape_ok": _looks_like_uuid(value)})
    return out


@pytest.mark.asyncio
async def test_wrong_length_is_spelled_out(client, monkeypatch):
    bad = "sk-live-abcdefgh1234"          # 20 символов
    st = {"mcp_configured": False, "api_key": True, "default_model": "auto",
          "browser_agent": False, "key_sources": _sources(bad)}

    text = await _say(st, monkeypatch)

    assert "20 символов вместо 36" in text
    assert "xxxxxxxx-xxxx" in text, "человеку нужен образец правильного вида"


@pytest.mark.asyncio
async def test_correct_key_gets_no_warning(client, monkeypatch):
    st = {"mcp_configured": False, "api_key": True, "default_model": "auto",
          "browser_agent": False, "key_sources": _sources(UUID)}

    text = await _say(st, monkeypatch)

    assert "вместо 36" not in text, "верный ключ тревожить нельзя"


@pytest.mark.asyncio
async def test_secret_value_never_leaks(client, monkeypatch):
    secret = "01234567-89ab-cdef-0123-456789abcdef"
    st = {"mcp_configured": False, "api_key": True, "default_model": "auto",
          "browser_agent": False, "key_sources": _sources(UUID, secret)}

    text = await _say(st, monkeypatch)

    assert secret not in text
    assert UUID not in text, "целое значение ключа в чат попадать не должно"


@pytest.mark.asyncio
async def test_status_reports_shape_for_every_half(client, monkeypatch):
    """И ключ, и секрет: перепутанные местами ловятся только так."""
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "short")
    monkeypatch.setenv("HIGGSFIELD_SECRET", UUID)

    sources = await hixiit._key_sources()

    by_name = {s["name"]: s for s in sources}
    assert by_name["ключ"]["shape_ok"] is False
    assert by_name["ключ"]["length"] == 5
    assert by_name["секрет"]["shape_ok"] is True
