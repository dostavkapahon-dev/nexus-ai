import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from .models import Base


def normalize_db_url(url: str) -> str:
    """Приводит строку подключения к async-драйверу.

    Supabase/Heroku отдают `postgres://…` или `postgresql://…` — синхронный формат,
    с которым create_async_engine падает. Переписываем на asyncpg. SQLite оставляем как есть.

    Отдельно чиним параметры строки: Supabase добавляет `?sslmode=require`, а пулер —
    `?pgbouncer=true`. SQLAlchemy передаёт их прямо в `asyncpg.connect()`, который таких
    аргументов не знает и падает с TypeError — то есть деплой ложится на первом же
    подключении. `sslmode` переводим в понятный asyncpg `ssl`, остальное убираем.
    """
    url = (url or "").strip()
    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]

    if not url.startswith("postgresql+asyncpg://") or "?" not in url:
        return url

    base, _, query = url.partition("?")
    keep = []
    for part in query.split("&"):
        if not part:
            continue
        key, _, value = part.partition("=")
        key_low = key.lower()
        if key_low == "sslmode":
            # disable/allow → без шифрования; require и строже → с шифрованием.
            if value.lower() not in ("disable", "allow"):
                keep.append("ssl=require")
        elif key_low in ("pgbouncer", "options", "target_session_attrs",
                         "connect_timeout", "application_name"):
            continue          # asyncpg их не принимает в таком виде
        else:
            keep.append(part)
    return base + ("?" + "&".join(keep) if keep else "")


DATABASE_URL = normalize_db_url(os.getenv('DATABASE_URL', '') or 'sqlite+aiosqlite:///./nexus.db')

# Постоянное ли хранилище. На Render диск контейнера эфемерный: без внешней БД
# любой redeploy стирает ключи, память и проекты. Раньше система молча садилась
# на файл SQLite, и «настройки сбрасываются сами» выглядело мистикой — теперь
# это состояние видно в логе, в /api/health, в вебе и в боте.
PERSISTENT = DATABASE_URL.startswith("postgresql")

EPHEMERAL_WARNING = (
    "Постоянная база не подключена: данные лежат в файле внутри контейнера и "
    "будут стёрты при следующем перезапуске или деплое — вместе с ключами, "
    "памятью и проектами. Подключите Postgres (например бесплатный Supabase) "
    "и задайте DATABASE_URL в Render → Environment."
)


def storage_info() -> dict:
    """Чем хранит система и переживёт ли это перезапуск."""
    kind = "postgresql" if PERSISTENT else (
        "sqlite" if DATABASE_URL.startswith("sqlite") else DATABASE_URL.split(":")[0])
    return {"kind": kind, "persistent": PERSISTENT,
            "warning": "" if PERSISTENT else EPHEMERAL_WARNING}

# pool_pre_ping спасает от «протухших» соединений: бесплатные Postgres (Supabase)
# закрывают простаивающие коннекты, а инстанс Render засыпает между запросами.
_engine_opts = {"echo": False}
if DATABASE_URL.startswith("postgresql"):
    _engine_opts.update(pool_pre_ping=True, pool_recycle=300)
elif DATABASE_URL.startswith("sqlite"):
    # У SQLite одна пишущая транзакция за раз, а фоновые задачи пишут в базу
    # параллельно с запросами. По умолчанию соседний писатель получает
    # «database is locked» мгновенно — с ожиданием он просто дожидается очереди.
    _engine_opts["connect_args"] = {"timeout": 30}

engine = create_async_engine(DATABASE_URL, **_engine_opts)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
