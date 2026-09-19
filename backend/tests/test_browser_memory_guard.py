"""Chromium, которому не хватает памяти, убивает ВЕСЬ процесс.

Это не ошибка запуска, которую можно поймать: ядро снимает сервис целиком —
вместе с ботом и задачами. Снаружи видно «Сервер перезапустился», задача
возобновляется, снова доходит до браузера, и сервис падает по кругу.
Поэтому память проверяется ДО запуска, а канал честно отказывает.
"""
import pytest

from core import server_browser as sb


def test_available_memory_is_measured():
    got = sb.available_mb()
    assert got is None or got > 0


def test_cgroup_limit_wins_over_host_memory(monkeypatch, tmp_path):
    """Хост может быть просторным, а контейнеру отведено 512 МБ."""
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemAvailable:   16000000 kB\n")
    limit = tmp_path / "memory.max"
    limit.write_text(str(512 * 1024 * 1024))
    used = tmp_path / "memory.current"
    used.write_text(str(400 * 1024 * 1024))

    real_open = open

    def fake_open(path, *a, **k):
        mapping = {"/proc/meminfo": meminfo,
                   "/sys/fs/cgroup/memory.max": limit,
                   "/sys/fs/cgroup/memory.current": used}
        return real_open(mapping.get(str(path), path), *a, **k)

    monkeypatch.setattr("builtins.open", fake_open)
    got = sb.available_mb()
    assert got is not None and 100 < got < 130, got


@pytest.mark.asyncio
async def test_launch_refuses_instead_of_killing_the_service(monkeypatch):
    monkeypatch.delenv("NEXUS_BROWSER_CDP", raising=False)
    monkeypatch.setattr(sb, "available_mb", lambda: 120.0)
    monkeypatch.setattr(sb, "MIN_FREE_MB", 300.0)

    with pytest.raises(RuntimeError) as e:
        await sb.ensure_browser()
    text = str(e.value)
    assert "памяти" in text and "120" in text
    assert "NEXUS_BROWSER_CDP" in text, "отказ обязан называть выход"


@pytest.mark.asyncio
async def test_unmeasurable_memory_does_not_block(monkeypatch):
    """Измерить нечем — не мешаем работе: на VPS браузер обязан запускаться."""
    monkeypatch.setattr(sb, "available_mb", lambda: None)
    monkeypatch.setattr(sb, "MIN_FREE_MB", 300.0)
    # До реального запуска дело дойдёт, значит проверка памяти пропущена.
    with pytest.raises(BaseException) as e:
        await sb.ensure_browser()
    assert "памяти" not in str(e.value)
