"""В статусе должно быть видно, переживут ли данные деплой.

Разница между Postgres и файлом в контейнере решающая: во втором случае
каждый деплой стирает ключи, память и вход в Higgsfield, и система
«ломается сама по себе». В вебе это было видно, в Telegram — нет.
"""
from agents import reporter


def test_postgres_is_reported_as_persistent(monkeypatch):
    monkeypatch.setattr("database.db.storage_info",
                        lambda: {"kind": "postgresql", "persistent": True,
                                 "warning": ""})
    line = reporter._storage_line()
    assert "postgresql" in line and "переживает" in line


def test_file_storage_names_the_missing_variable(monkeypatch):
    monkeypatch.setattr("database.db.storage_info",
                        lambda: {"kind": "sqlite", "persistent": False,
                                 "warning": "..."})
    line = reporter._storage_line()
    assert "сотрутся" in line and "DATABASE_URL" in line


def test_broken_check_does_not_break_status(monkeypatch):
    def boom():
        raise RuntimeError("нет базы")
    monkeypatch.setattr("database.db.storage_info", boom)
    assert "не определено" in reporter._storage_line()
