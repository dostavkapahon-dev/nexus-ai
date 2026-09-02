"""Общие фикстуры тестов.

Приложение поднимается без lifespan: планировщик и Telegram-polling в тестах
не нужны, а БД — временный SQLite-файл на каждый прогон.
"""
import os
import sys
import pathlib
import tempfile

import pytest
import pytest_asyncio

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

TEST_PASSWORD = "test-password"
os.environ["ADMIN_PASSWORD"] = TEST_PASSWORD
_DB_FILE = pathlib.Path(tempfile.mkdtemp(prefix="nexus-test-")) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB_FILE}"
# Ключи площадок не должны подтягиваться из окружения разработчика.
for _k in ("TELEGRAM_BOT_TOKEN", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
    os.environ.pop(_k, None)

from httpx import ASGITransport, AsyncClient  # noqa: E402

import main  # noqa: E402
from core import auth as auth_mod  # noqa: E402
from database.db import init_db, engine  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    """Middleware режет >60 запросов в минуту с одного IP — тесты не должны
    ловить 429 друг от друга."""
    auth_mod._rate.clear()
    yield
    auth_mod._rate.clear()


@pytest.fixture(autouse=True)
def _reset_escrow():
    """«Этого запроса ждёт человек» — пометка одного запроса, а не режим системы.
    Без сброса она протекала в следующий тест, и фоновый сбой уходил в очередь к
    Клоду вместо честного падения."""
    from core import ai_escrow
    ai_escrow.reset()
    yield
    ai_escrow.reset()


class OutboundBlocked(RuntimeError):
    """Тест попытался сходить в интернет."""


@pytest.fixture(autouse=True)
def _no_outbound_network(monkeypatch):
    """Тесты не ходят в сеть — и падают, если попробуют.

    Дважды подряд живой запрос протекал в тесты (проверка сгенерированной
    картинки, затем полный прогон фабрики). Прогон при этом оставался зелёным,
    поэтому заметить это можно было только по времени CI: 1 м 30 с → 5 м 54 с →
    3 м 09 с. Такая ошибка должна падать сразу и громко, а не превращаться в
    медленный прогон, зависящий от чужого сервиса.

    Блокируется только настоящий транспорт httpx. ASGITransport, через который
    тесты стучатся в само приложение, работает как раньше.
    """
    import httpx

    def blocked(self, request, *a, **kw):
        raise OutboundBlocked(
            f"Тест пошёл в сеть: {request.method} {request.url}. "
            "Подмените вызов заглушкой — прогон не должен зависеть от чужого "
            "сервиса (см. _no_outbound_network в conftest)."
        )

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", blocked)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)

    # httpx — не единственная дверь наружу: yt-dlp ходит через urllib, а
    # Google SDK через свой транспорт. Поэтому дополнительно закрыт сам сокет.
    # Локальные адреса оставлены: на них держатся служебные пары сокетов
    # внутри asyncio, и их запрет сломал бы сам прогон.
    import socket

    real_connect = socket.socket.connect

    def guarded_connect(self, address, *a, **kw):
        host = address[0] if isinstance(address, tuple) else address
        if isinstance(host, str) and host not in ("127.0.0.1", "::1", "localhost"):
            raise OutboundBlocked(
                f"Тест открыл сокет наружу: {host}. Подмените вызов заглушкой "
                "(см. _no_outbound_network в conftest)."
            )
        return real_connect(self, address, *a, **kw)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    yield


@pytest.fixture(autouse=True)
def _no_live_image_check(monkeypatch):
    """Проверка сгенерированной картинки ходит в интернет — в тестах не должна.

    Иначе прогон зависит от стороннего сервиса: он же определяет и время
    (на CI это было +2 минуты на каждый вызов фабрики), и — если сервис ляжет —
    результат. Тестам, которым важно именно поведение проверки, она
    подменяется своей заглушкой, и та побеждает эту.
    """
    async def offline(url, attempts=2):
        return True, ""

    monkeypatch.setattr("core.media_generator._image_responds", offline)
    yield


@pytest_asyncio.fixture
async def client():
    await init_db()
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    # У каждого теста свой цикл событий, а движок один на весь прогон. Соединение,
    # пережившее свой цикл, остаётся с незакрытой транзакцией, и следующий тест
    # получает «database is locked». Закрываем соединения вместе с циклом.
    await engine.dispose()


@pytest_asyncio.fixture
async def token(client):
    r = await client.post("/api/auth/login", json={"password": TEST_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest_asyncio.fixture
async def auth_client(client, token):
    client.headers["Authorization"] = f"Bearer {token}"
    yield client


def pytest_sessionfinish(session, exitstatus):
    import asyncio

    try:
        asyncio.run(engine.dispose())
    except Exception:
        pass
