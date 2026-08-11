import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from .models import Base


def normalize_db_url(url: str) -> str:
    """Приводит строку подключения к async-драйверу.

    Supabase/Heroku отдают `postgres://…` или `postgresql://…` — синхронный формат,
    с которым create_async_engine падает. Переписываем на asyncpg. SQLite оставляем как есть.
    """
    url = (url or "").strip()
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://"):]
    return url


DATABASE_URL = normalize_db_url(os.getenv('DATABASE_URL', '') or 'sqlite+aiosqlite:///./nexus.db')

# pool_pre_ping спасает от «протухших» соединений: бесплатные Postgres (Supabase)
# закрывают простаивающие коннекты, а инстанс Render засыпает между запросами.
_engine_opts = {"echo": False}
if DATABASE_URL.startswith("postgresql"):
    _engine_opts.update(pool_pre_ping=True, pool_recycle=300)

engine = create_async_engine(DATABASE_URL, **_engine_opts)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
