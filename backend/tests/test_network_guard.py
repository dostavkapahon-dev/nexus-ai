"""Тесты не ходят в интернет — и падают, если попробуют.

Дважды подряд живой запрос протекал в прогон: сперва проверка сгенерированной
картинки, потом полный запуск фабрики из теста. Оба раза прогон оставался
зелёным, поэтому заметить это можно было только по времени CI — 1 м 30 с →
5 м 54 с → 3 м 09 с. Сторож превращает такую ошибку в громкое падение.
"""
import socket

import httpx
import pytest

from conftest import OutboundBlocked


@pytest.mark.asyncio
async def test_async_request_is_blocked():
    with pytest.raises(OutboundBlocked):
        async with httpx.AsyncClient(timeout=1) as c:
            await c.get("https://example.com")


def test_sync_request_is_blocked():
    with pytest.raises(OutboundBlocked):
        httpx.get("https://example.com", timeout=1)


def test_raw_socket_is_blocked():
    """httpx — не единственная дверь наружу: yt-dlp ходит через urllib,
    Google SDK через свой транспорт. Закрыт сам сокет."""
    with pytest.raises(OutboundBlocked):
        socket.socket().connect(("example.com", 443))


def test_loopback_stays_open():
    """Служебные пары сокетов внутри asyncio живут на локальном адресе —
    их запрет сломал бы сам прогон."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    try:
        client = socket.socket()
        client.settimeout(2)
        client.connect(("127.0.0.1", server.getsockname()[1]))
        client.close()
    finally:
        server.close()


@pytest.mark.asyncio
async def test_app_client_still_works(auth_client):
    """Приложение тесты по-прежнему опрашивают: ASGITransport не сеть."""
    r = await auth_client.get("/api/health")
    assert r.status_code == 200
