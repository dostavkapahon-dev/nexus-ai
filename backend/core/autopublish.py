"""
Режим публикации по площадкам: вручную / с подтверждением / автоматически.

Одна общая настройка «автопубликация ON/OFF» и отдельный режим на каждую
площадку. Смысл режимов:

  manual   — публикуем только по прямой команде пользователя;
  confirm  — система готовит пост и ставит его на подтверждение;
  auto     — публикуем по расписанию без участия человека.

Глобальный выключатель сильнее площадки: при `enabled: false` любой `auto`
трактуется как `confirm` — то есть контент готовится, но не уходит наружу.
Так «выключить автопостинг» действительно останавливает выход постов, а не
оставляет площадку, про которую забыли.
"""
import json

from sqlalchemy import select

from core import kv
from database.db import AsyncSessionLocal
from database.models import Connection

KEY = "autopublish_settings"

MANUAL, CONFIRM, AUTO = "manual", "confirm", "auto"
MODES = (MANUAL, CONFIRM, AUTO)

# По умолчанию Telegram — свой бот, там ревью площадки нет и риск минимальный,
# поэтому автоматически. Остальные площадки модерируются и наказывают за
# неудачный пост охватом — их безопаснее держать на подтверждении.
DEFAULTS = {
    "telegram": AUTO,
    "instagram": CONFIRM,
    "tiktok": CONFIRM,
    "youtube": CONFIRM,
    "vk": CONFIRM,
    "threads": CONFIRM,
}


async def _load(db) -> dict:
    r = await db.execute(select(Connection).where(Connection.key_name == KEY))
    c = r.scalar_one_or_none()
    if not (c and c.key_value):
        return {}
    try:
        data = json.loads(c.key_value)
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


async def get_settings() -> dict:
    async with AsyncSessionLocal() as db:
        saved = await _load(db)
    platforms = {**DEFAULTS, **(saved.get("platforms") or {})}
    platforms = {p: (m if m in MODES else DEFAULTS.get(p, CONFIRM))
                 for p, m in platforms.items()}
    return {"enabled": bool(saved.get("enabled", True)), "platforms": platforms}


async def set_settings(enabled: bool | None = None,
                       platforms: dict | None = None) -> dict:
    """Правит настройки под замком: рубильник из Telegram и режим площадки из
    веба приходят одновременно, а раньше каждый писал свою копию целиком —
    вторая правка отменяла первую."""
    for platform, mode in (platforms or {}).items():
        if mode not in MODES:
            return {"ok": False, "error": f"{platform}: режим должен быть один из {MODES}"}

    async with kv.update(KEY, {}) as saved:
        merged = {**DEFAULTS, **(saved.get("platforms") or {})}
        merged.update(platforms or {})
        saved["platforms"] = {p: (m if m in MODES else DEFAULTS.get(p, CONFIRM))
                              for p, m in merged.items()}
        saved["enabled"] = bool(enabled) if enabled is not None \
            else bool(saved.get("enabled", True))
        current = {"enabled": saved["enabled"], "platforms": dict(saved["platforms"])}
    return {"ok": True, **current}


async def mode_for(platform: str) -> str:
    s = await get_settings()
    mode = s["platforms"].get(platform, DEFAULTS.get(platform, CONFIRM))
    if not s["enabled"] and mode == AUTO:
        return CONFIRM
    return mode


async def may_autopublish(platform: str) -> bool:
    """Можно ли выпустить пост без человека — единственный вопрос планировщика."""
    return await mode_for(platform) == AUTO
