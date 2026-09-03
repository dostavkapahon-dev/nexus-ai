import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from .models import Base

def _database_url() -> str:
    """URL базы. Postgres (постоянная память) при наличии DATABASE_URL, иначе SQLite.

    ВАЖНО: SQLite-файл на Render эфемерен — вся память стирается при рестарте.
    Для постоянной памяти задай DATABASE_URL на Postgres; синхронные схемы
    (postgres:// и postgresql://) приводятся к асинхронному драйверу автоматически.
    NEXUS_DB_PATH позволяет положить SQLite-файл на примонтированный диск.
    """
    url = os.getenv('DATABASE_URL', '').strip()
    if url:
        if url.startswith('postgres://'):
            url = url.replace('postgres://', 'postgresql+asyncpg://', 1)
        elif url.startswith('postgresql://'):
            url = url.replace('postgresql://', 'postgresql+asyncpg://', 1)
        return url
    return f"sqlite+aiosqlite:///{os.getenv('NEXUS_DB_PATH', './nexus.db')}"


DATABASE_URL = _database_url()

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
