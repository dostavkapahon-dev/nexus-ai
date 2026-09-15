"""MCP Higgsfield авторизует пользователя, а не ключ — и это надо говорить.

С живого сервера дважды приходило молчание: сперва `-32603`, затем
`ConnectTimeout`. Оба раза совет звучал как «проверьте HIGGSFIELD_MCP_URL», хотя
чинится это не ключом: официальный mcp.higgsfield.ai требует OAuth-входа
пользователя, а таймаут означает, что адрес вообще не отвечает с хостинга.
"""
import pytest

from core import hixiit


def test_missing_url_names_the_official_one(monkeypatch):
    monkeypatch.delenv("HIGGSFIELD_MCP_URL", raising=False)
    note = hixiit.mcp_address_note()
    assert hixiit.OFFICIAL_MCP_URL in note
    assert "OAuth" in note


def test_foreign_address_is_pointed_out(monkeypatch):
    monkeypatch.setenv("HIGGSFIELD_MCP_URL", "https://example.test/mcp")
    note = hixiit.mcp_address_note()
    assert "example.test" in note and hixiit.OFFICIAL_MCP_URL in note


def test_official_address_has_no_complaints(monkeypatch):
    monkeypatch.setenv("HIGGSFIELD_MCP_URL", hixiit.OFFICIAL_MCP_URL + "/")
    assert hixiit.mcp_address_note() == ""


def test_timeout_verdict_does_not_blame_the_key(monkeypatch):
    monkeypatch.setenv("HIGGSFIELD_MCP_URL", hixiit.OFFICIAL_MCP_URL)
    verdict = hixiit.probe_verdict(
        {"ok": False, "stage": "connect", "error": "ConnectTimeout: "})
    assert "не отвечает" in verdict
    assert "не зависит" in verdict, "генерация не должна выглядеть заблокированной"


def test_timeout_with_foreign_address_names_it(monkeypatch):
    monkeypatch.setenv("HIGGSFIELD_MCP_URL", "https://old.test/mcp")
    verdict = hixiit.probe_verdict(
        {"ok": False, "stage": "connect", "error": "ConnectTimeout: "})
    assert "old.test" in verdict


def test_oauth_verdict_is_kept_for_internal_error(monkeypatch):
    verdict = hixiit.probe_verdict(
        {"ok": False, "stage": "balance", "error": "code=-32603",
         "tools": ["balance"]})
    assert "OAuth" in verdict
