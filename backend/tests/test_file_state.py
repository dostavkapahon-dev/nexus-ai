"""Память агента переживает перезапуск.

Файлы `backend/data/*` лежат на эфемерном диске: деплой возвращал skills.json и
brand_voice.txt к версии из git, а hook_history.json стирал совсем. Здесь
проверяется, что база стала источником правды, а файл — рабочей копией.
"""
import json

import pytest

from core import file_state
from database.db import init_db


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    """Своя папка данных на тест — чтобы не трогать реальные backend/data/*."""
    monkeypatch.setattr(file_state, "BASE", str(tmp_path))
    (tmp_path / "data").mkdir()
    file_state._dirty.clear()
    yield tmp_path
    file_state._dirty.clear()


@pytest.mark.asyncio
async def test_first_start_seeds_db_from_file(state_dir):
    """Первый запуск: в базе пусто — туда уезжает то, что приехало из git."""
    await init_db()
    (state_dir / "data" / "brand_voice.txt").write_text("голос из git", encoding="utf-8")

    res = await file_state.restore_all()

    assert "brand_voice" in res["seeded"]
    assert await file_state._db_get("brand_voice") == "голос из git"


@pytest.mark.asyncio
async def test_restore_beats_file_from_build(state_dir):
    """Деплой принёс старый файл, а в базе — то, чему агент научился после.
    Побеждать должна база, иначе накопленный опыт откатывается каждым релизом."""
    await init_db()
    await file_state._db_set("skills", json.dumps([{"title": "выученное"}]))
    (state_dir / "data" / "skills.json").write_text("[]", encoding="utf-8")

    res = await file_state.restore_all()

    assert "skills" in res["restored"]
    on_disk = json.loads((state_dir / "data" / "skills.json").read_text(encoding="utf-8"))
    assert on_disk == [{"title": "выученное"}]


@pytest.mark.asyncio
async def test_flush_saves_dirty_file(state_dir):
    await init_db()
    (state_dir / "data" / "hook_history.json").write_text('[{"type": "боль"}]', encoding="utf-8")

    file_state.mark_dirty("hook_history")
    res = await file_state.flush()

    assert res["saved"] == ["hook_history"] and res["pending"] == []
    assert json.loads(await file_state._db_get("hook_history")) == [{"type": "боль"}]


@pytest.mark.asyncio
async def test_failed_save_stays_in_queue(state_dir, monkeypatch):
    """Обрыв связи с базой не должен стоить агенту памяти: имя возвращается
    в очередь и уедет следующим заходом."""
    await init_db()
    (state_dir / "data" / "skills.json").write_text("[]", encoding="utf-8")

    async def boom(name, text):
        raise RuntimeError("база недоступна")

    monkeypatch.setattr(file_state, "_db_set", boom)
    file_state.mark_dirty("skills")
    res = await file_state.flush()

    assert res["saved"] == [] and res["pending"] == ["skills"]


@pytest.mark.asyncio
async def test_unknown_name_ignored(state_dir):
    file_state.mark_dirty("нет-такого")
    assert file_state._dirty == set()


@pytest.mark.asyncio
async def test_writers_mark_their_state_dirty(state_dir, monkeypatch):
    """Сквозная проверка: запись через обычные точки входа ставит состояние
    в очередь на сохранение — без этого связка «файл → база» разорвана."""
    await init_db()
    from core import brand, hooks, skills_store

    monkeypatch.setattr(skills_store, "SKILLS_FILE", str(state_dir / "data" / "skills.json"))
    monkeypatch.setattr(hooks, "HISTORY_PATH", str(state_dir / "data" / "hook_history.json"))
    monkeypatch.setattr(brand, "BRAND_VOICE_PATH", str(state_dir / "data" / "brand_voice.txt"))

    skills_store.add_skill("hook", "хук про доставку")
    hooks.record("боль", "b_roll", "тема")
    brand.set_brand_voice("новый голос")

    assert file_state._dirty == {"skills", "hook_history", "brand_voice"}

    res = await file_state.flush()
    assert sorted(res["saved"]) == ["brand_voice", "hook_history", "skills"]
    assert await file_state._db_get("brand_voice") == "новый голос"
