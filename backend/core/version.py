"""
Какая версия кода реально запущена.

Зачем: несколько раз подряд ошибка на проде оказывалась уже исправленной в
репозитории — просто Render крутил старую сборку, а понять это было нечем.
Гадать «доехал ли фикс» дорого: каждая итерация стоит круга переписки.

Render сам кладёт коммит в `RENDER_GIT_COMMIT`. Если переменной нет (локальный
запуск), спрашиваем git. Не удалось ни то, ни другое — честно говорим «неизвестно»,
а не выдумываем номер.
"""
import os
import subprocess
from datetime import datetime

_cached: dict | None = None


def _from_env() -> str:
    for key in ("RENDER_GIT_COMMIT", "GIT_COMMIT", "SOURCE_VERSION", "HEROKU_SLUG_COMMIT"):
        value = os.getenv(key, "").strip()
        if value:
            return value[:12]
    return ""


def _from_git() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"],
                             capture_output=True, text=True, timeout=5,
                             cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def migration_status() -> str:
    """Прошли ли миграции при старте.

    Раньше `alembic upgrade head && uvicorn` означал, что при неудаче миграции
    сервис не поднимался вовсе, и причину было видно только в логах Render.
    Теперь старт продолжается, а результат виден снаружи.
    """
    try:
        with open("/tmp/nexus_migration") as f:
            return "ok" if f.read().strip() == "ok" else "ошибка миграции"
    except FileNotFoundError:
        return "неизвестно"      # локальный запуск без startCommand
    except Exception:
        return "неизвестно"


def browser_ready() -> bool:
    """Установлен ли Chromium: без него браузерный путь публикации не работает."""
    try:
        from playwright._impl._driver import compute_driver_executable  # noqa: F401
        import glob
        base = os.getenv("PLAYWRIGHT_BROWSERS_PATH", "") or os.path.expanduser("~/.cache/ms-playwright")
        return bool(glob.glob(os.path.join(base, "chromium*")))
    except Exception:
        return False


def build_info() -> dict:
    """Коммит, ветка и время старта процесса. Считается один раз."""
    global _cached
    if _cached is None:
        commit = _from_env() or _from_git()
        _cached = {
            "commit": commit or "неизвестно",
            "branch": os.getenv("RENDER_GIT_BRANCH", "").strip() or "—",
            "started_at": datetime.utcnow().isoformat(timespec="seconds"),
        }
    # Эти два меняются от запуска к запуску — считаем каждый раз.
    return {**_cached, "migration": migration_status(),
            "browser_installed": browser_ready()}
