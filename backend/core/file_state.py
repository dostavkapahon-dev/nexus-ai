"""
Память агента переживает перезапуск.

Проблема: накопленный опыт агента лежал только в файлах `backend/data/*` —
`skills.json` (что сработало и что нет), `brand_voice.txt` (голос бренда),
`hook_history.json` (ротация хуков, он ещё и в `.gitignore`). На Render диск
контейнера эфемерный, поэтому каждый деплой откатывал первые два к версии из git,
а третий стирал начисто. Снаружи это выглядело так: агент «забывал» всё, чему
научился за неделю, и снова предлагал тот же хук, что и вчера.

Решение: файл остаётся рабочей копией (её по-прежнему видно и можно править
руками), а источником правды становится строка в таблице `agent_state`.

  • при старте  — `restore_all()` разворачивает сохранённое обратно на диск;
  • при записи  — писатель зовёт `mark_dirty(...)`, и содержимое уезжает в БД;
  • подстраховка — `flush()` в планировщике: запись из потока без событийного
    цикла не смогла бы сохраниться сама и иначе дождалась бы только рестарта.

Ничего из этого не секретно (голос бренда, приёмы, история хуков), поэтому
хранится как есть, без шифрования — в отличие от доступов в `core/credentials.py`.
"""
import asyncio
import os

BASE = os.path.dirname(os.path.dirname(__file__))

# Имя состояния → путь файла относительно `backend/`.
FILES = {
    "skills": "data/skills.json",
    "brand_voice": "data/brand_voice.txt",
    "hook_history": "data/hook_history.json",
}

_dirty: set[str] = set()
_flush_scheduled = False


def _path(name: str) -> str:
    return os.path.join(BASE, FILES[name])


def _read_file(name: str) -> str | None:
    try:
        with open(_path(name), encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None
    except Exception:
        return None


def _write_file(name: str, text: str) -> None:
    path = _path(name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


async def _db_get(name: str) -> str | None:
    from sqlalchemy import select
    from database.db import AsyncSessionLocal
    from database.models import AgentState
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(AgentState).where(AgentState.key == name))
        row = r.scalar_one_or_none()
    return row.value if row else None


async def _db_set(name: str, text: str) -> None:
    from sqlalchemy import select
    from database.db import AsyncSessionLocal
    from database.models import AgentState
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(AgentState).where(AgentState.key == name))
        row = r.scalar_one_or_none()
        if row:
            if row.value == text:
                return                      # нечего писать — не трогаем updated_at
            row.value = text
        else:
            db.add(AgentState(key=name, value=text))
        await db.commit()


def mark_dirty(name: str) -> None:
    """Файл изменился — поставить его в очередь на сохранение в БД.

    Зовётся из обычного (синхронного) кода писателей, поэтому сама запись
    откладывается в событийный цикл. Цикла нет (тест, скрипт, фоновый поток) —
    имя остаётся в очереди, и его подберёт ближайший `flush()`.
    """
    global _flush_scheduled
    if name not in FILES:
        return
    _dirty.add(name)
    if _flush_scheduled:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    _flush_scheduled = True
    loop.create_task(_flush_soon())


async def _flush_soon() -> None:
    global _flush_scheduled
    try:
        await flush()
    finally:
        _flush_scheduled = False


async def flush() -> dict:
    """Сохраняет в БД всё, что накопилось в очереди.

    Неудача записи не теряет изменение: имя возвращается в очередь и уедет
    следующим заходом — иначе один обрыв связи с базой стоил бы агенту памяти.
    """
    names, _dirty_now = sorted(_dirty), set(_dirty)
    _dirty.difference_update(_dirty_now)
    saved = []
    for name in names:
        text = _read_file(name)
        if text is None:
            continue
        try:
            await _db_set(name, text)
            saved.append(name)
        except Exception as e:
            _dirty.add(name)
            print(f"[NEXUS] память «{name}» не сохранена в базу "
                  f"({type(e).__name__}: {e}) — попробуем позже", flush=True)
    return {"saved": saved, "pending": sorted(_dirty)}


async def restore_all() -> dict:
    """Разворачивает сохранённую память на диск. Зовётся один раз при старте.

    База побеждает файл: файл приезжает из образа сборки и не знает ничего о том,
    что агент выучил после деплоя. Если же в базе записи ещё нет (первый запуск),
    в неё уходит текущее содержимое файла — так значения из git становятся
    начальной точкой, а не теряются.
    """
    restored, seeded = [], []
    for name in FILES:
        try:
            stored = await _db_get(name)
            if stored:
                if _read_file(name) != stored:
                    _write_file(name, stored)
                restored.append(name)
            else:
                text = _read_file(name)
                if text:
                    await _db_set(name, text)
                    seeded.append(name)
        except Exception as e:
            print(f"[NEXUS] память «{name}» не восстановлена "
                  f"({type(e).__name__}: {e})", flush=True)
    return {"restored": restored, "seeded": seeded}


async def snapshot_all() -> dict:
    """Принудительно сохранить всё содержимое файлов в базу."""
    _dirty.update(FILES)
    return await flush()
