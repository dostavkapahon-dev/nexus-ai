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
