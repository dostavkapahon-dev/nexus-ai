"""
Реестр агентов: понятный список ролей вместо россыпи классов и модулей.

Что было. Одиннадцать классов в `backend/agents/` инстанцировались прямым
импортом в `core/orchestrator.py`, порядок их вызова был зашит в код, а дирижёр
про них вообще не знал: его `delegate` уходил не к агентам, а к LLM-провайдерам.
Роли из ТЗ — Research, Instagram, TikTok, Telegram, Publisher — существовали
только на словах: их работа была размазана по `connectors/`, `publishers/`,
`core/telegram_bot.py`, `core/viral_research.py`.

Что здесь. Роли объявлены явно, с описанием, требуемыми доступами и признаком
доступности. Существующие классы не переписываются — роль ссылается на то, что
уже работает. Запуск роли идёт через `run()`, и он ничего не публикует и не
меняет настройки: агенты выполняют работу, а решения о публикации принимает
дирижёр через очередь с режимом из `core/autopublish.py`.
"""
import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentSpec:
    key: str
    title: str
    role: str                       # чем занимается, одной фразой
    does: tuple[str, ...] = ()      # что умеет конкретно
    requires: tuple[str, ...] = ()  # переменные окружения, без которых роль мертва
    backed_by: tuple[str, ...] = () # где живёт реальная реализация
    system: str = ""                # роль для LLM, если своей реализации нет
    orchestrated: bool = True       # задачи ставит дирижёр, а не агент сам


REGISTRY: dict[str, AgentSpec] = {
    "director": AgentSpec(
        key="director", title="Дирижёр", role="главный управляющий агент",
        does=("разбирает цель на шаги", "выбирает исполнителей", "отвечает за итог"),
        backed_by=("core/marketing_director.py",),
    ),
    "research": AgentSpec(
        key="research", title="Исследователь", role="исследование интернета",
        does=("поиск тем и трендов", "анализ конкурентов", "референсы и факты"),
        backed_by=("core/websearch.py", "core/viral_research.py", "agents/trend_analyst.py"),
        system="Ты аналитик-исследователь. Опираешься на факты и источники, без домыслов.",
    ),
    "instagram": AgentSpec(
        key="instagram", title="Instagram", role="работа с Instagram",
        does=("чтение профиля и постов", "публикация", "метрики"),
        requires=("INSTAGRAM_ACCESS_TOKEN",),
        backed_by=("connectors/instagram.py", "core/instagram_reader.py"),
    ),
    "tiktok": AgentSpec(
        key="tiktok", title="TikTok", role="работа с TikTok",
        does=("публикация", "чтение метрик роликов"),
        requires=("TIKTOK_ACCESS_TOKEN",),
        backed_by=("connectors/tiktok.py",),
    ),
    "telegram": AgentSpec(
        key="telegram", title="Telegram", role="работа с Telegram",
        does=("публикация в канал", "сообщения", "приём команд"),
        requires=("TELEGRAM_BOT_TOKEN",),
        backed_by=("core/telegram_channels.py", "connectors/telegram.py",
                   "core/telegram_bot.py"),
    ),
    "content_strategist": AgentSpec(
        key="content_strategist", title="Контент-стратег", role="контентная стратегия",
        does=("разбор ниши и аудитории", "контент-план", "рубрики и форматы"),
        backed_by=("agents/strategist.py", "agents/niche_analyst.py"),
        system="Ты контент-стратег. Мыслишь планом и рубриками, а не отдельными постами.",
    ),
    "script": AgentSpec(
        key="script", title="Сценарист", role="сценарии роликов",
        does=("хуки", "раскадровка", "текст под озвучку"),
        backed_by=("core/creative_director.py",),
        system="Ты сценарист коротких видео. Первые три секунды решают всё.",
    ),
    "video": AgentSpec(
        key="video", title="Видео", role="видео и Reels",
        does=("генерация видео", "обложки", "монтаж и субтитры"),
        backed_by=("core/media_generator.py", "core/montage.py", "core/video_assembly.py"),
    ),
    "copywriter": AgentSpec(
        key="copywriter", title="Копирайтер", role="тексты",
        does=("посты", "адаптация под площадки", "голос бренда"),
        backed_by=("agents/copywriter.py", "agents/voice_adapter.py", "agents/adapter.py"),
        system="Ты копирайтер. Пишешь живым языком, конкретно, без клише.",
    ),
    "analytics": AgentSpec(
        key="analytics", title="Аналитик", role="аналитика",
        does=("метрики публикаций", "что сработало", "отчёты"),
        backed_by=("core/post_analytics.py", "agents/reporter.py"),
        system="Ты аналитик. Выводы делаешь только из цифр, которые видишь.",
    ),
    "publisher": AgentSpec(
        key="publisher", title="Публикатор", role="публикация",
        does=("очередь публикаций", "повторы при сбоях", "режимы автопубликации"),
        backed_by=("core/publish_queue.py", "core/autopublish.py", "publishers/"),
    ),
}

ORDER = tuple(REGISTRY)


def get(key: str) -> AgentSpec | None:
    return REGISTRY.get((key or "").strip().lower())


def missing_keys(spec: AgentSpec) -> list[str]:
    return [env for env in spec.requires if not os.getenv(env)]


def available() -> list[str]:
    """Роли, которые сейчас реально могут работать.

    Агент без доступов — не «выключенный», а нерабочий: предлагать его дирижёру
    значит тратить шаг на заведомо провальный вызов.
    """
    return [k for k, spec in REGISTRY.items() if not missing_keys(spec)]


def describe() -> list[dict]:
    """Список ролей для интерфейса и для системного промпта дирижёра."""
    out = []
    for spec in REGISTRY.values():
        missing = missing_keys(spec)
        out.append({
            "key": spec.key, "title": spec.title, "role": spec.role,
            "does": list(spec.does), "requires": list(spec.requires),
            "backed_by": list(spec.backed_by), "missing": missing,
            "ready": not missing,
        })
    return out


def agents_doc() -> str:
    """Блок для системного промпта: кому что можно поручить.

    Дирижёр должен видеть роли рядом с исполнителями-моделями — иначе он и
    дальше будет отдавать всё подряд «дешёвой нейросети», не различая задач.
    """
    lines = []
    for spec in REGISTRY.values():
        if spec.key == "director" or missing_keys(spec):
            continue
        lines.append(f"- {spec.key}: {spec.role} ({', '.join(spec.does)})")
    if not lines:
        return ""
    return ("--- АГЕНТЫ ДЛЯ delegate (специализации; можно указывать вместо модели) ---\n"
            + "\n".join(lines))


async def run(key: str, task: str, context: str = "") -> dict:
    """Выполнить задачу ролью.

    Роль — это специализация: у неё либо есть свой исполнитель, либо своя роль
    для модели. Публикацией и настройками роли не занимаются: это решение
    дирижёра, иначе агенты начнут управлять системой сами.
    """
    spec = get(key)
    if not spec:
        return {"ok": False, "error": f"нет такого агента: {key}"}
    missing = missing_keys(spec)
    if missing:
        return {"ok": False, "agent": spec.key,
                "error": f"агенту {spec.title} не хватает доступов: {', '.join(missing)}"}

    if spec.key == "research":
        from core.websearch import deep_research
        res = await deep_research(task)
        if res.get("ok"):
            return {"ok": True, "agent": spec.key,
                    "text": res.get("summary") or "", "sources": res.get("sources", [])}
        return {"ok": False, "agent": spec.key, "error": res.get("error")}

    from core.dispatch import cheapest_available, delegate
    executor = cheapest_available()
    if not executor:
        return {"ok": False, "agent": spec.key,
                "error": "нет ни одного ключа ИИ — выполнять задачу нечем"}
    res = await delegate(executor, task, system=spec.system or spec.role, context=context)
    return {**res, "agent": spec.key}
