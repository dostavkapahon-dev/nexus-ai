"""
Память агента: скиллы, находки и улучшения, которые накапливаются со временем.

Зачем: агент раз за разом заново «изобретает» подход, потому что ничего не помнит
между запусками. Здесь он сохраняет то, что сработало (и что провалилось), и
подмешивает это в следующие задачи — результат растёт, а токены экономятся:
не нужно каждый раз переоткрывать одно и то же.

Хранилище — JSON-файл `data/skills.json`, чтобы правки были видимы человеку
и переживали перезапуск. Формат записи:
    {"id", "kind", "title", "body", "tags", "score", "used", "created_at"}

kind:
  hook      — рабочая формула хука
  format    — удачный формат/структура ролика
  visual    — приём в кадре, стиль, промпт
  audience  — факт о своей аудитории
  mistake   — что НЕ сработало (чтобы не повторять)
  rule      — правило бренда/подачи
"""
import os
import json
import uuid
from datetime import datetime

SKILLS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "skills.json")

KINDS = ("hook", "format", "visual", "audience", "mistake", "rule")


def _load() -> list[dict]:
    if not os.path.exists(SKILLS_FILE):
        return []
    try:
        with open(SKILLS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save(items: list[dict]) -> None:
    os.makedirs(os.path.dirname(SKILLS_FILE), exist_ok=True)
    with open(SKILLS_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    # Накопленный опыт нельзя держать только на диске контейнера: деплой вернул бы
    # файл к версии из git и стёр всё, чему агент научился после неё.
    from core import file_state
    file_state.mark_dirty("skills")


def list_skills(kind: str = None, limit: int = 200) -> list[dict]:
    """Все скиллы, самые полезные сверху (по score, затем по свежести)."""
    items = _load()
    if kind:
        items = [i for i in items if i.get("kind") == kind]
    items.sort(key=lambda i: (i.get("score", 0), i.get("created_at", "")), reverse=True)
    return items[:limit]


def add_skill(kind: str, title: str, body: str = "", tags: list = None,
              score: int = 1) -> dict:
    """Добавляет находку. Дубликат по заголовку не плодим — поднимаем ему score."""
    kind = kind if kind in KINDS else "rule"
    items = _load()
    norm = (title or "").strip().lower()
    for it in items:
        if it.get("title", "").strip().lower() == norm and it.get("kind") == kind:
            it["score"] = it.get("score", 1) + 1
            if body and len(body) > len(it.get("body", "")):
                it["body"] = body
            _save(items)
            return it
    item = {
        "id": uuid.uuid4().hex[:8],
        "kind": kind,
        "title": (title or "").strip()[:200],
        "body": (body or "").strip()[:2000],
        "tags": tags or [],
        "score": score,
        "used": 0,
        "created_at": datetime.utcnow().isoformat(timespec="seconds"),
    }
    items.append(item)
    _save(items)
    return item


def delete_skill(skill_id: str) -> bool:
    items = _load()
    rest = [i for i in items if i.get("id") != skill_id]
    if len(rest) == len(items):
        return False
    _save(rest)
    return True


def vote(skill_id: str, delta: int = 1) -> dict | None:
    """Поднять/понизить полезность: сработало в бою → выше в подсказках."""
    items = _load()
    for it in items:
        if it.get("id") == skill_id:
            it["score"] = it.get("score", 1) + delta
            _save(items)
            return it
    return None


def context_for(task: str = "", kinds: tuple = None, limit: int = 12) -> str:
    """Готовый блок памяти для промпта агента.

    Берём самые полезные записи; ошибки выносим отдельно — модели важно явно
    видеть, чего НЕ делать. Пустая память → пустая строка (промпт не мусорим).
    """
    kinds = kinds or KINDS
    items = [i for i in list_skills() if i.get("kind") in kinds][:limit]
    if not items:
        return ""

    good = [i for i in items if i.get("kind") != "mistake"]
    bad = [i for i in items if i.get("kind") == "mistake"]

    lines = []
    if good:
        lines.append("ЧТО УЖЕ РАБОТАЛО (используй):")
        for i in good:
            body = f" — {i['body'][:180]}" if i.get("body") else ""
            lines.append(f"• [{i['kind']}] {i['title']}{body}")
    if bad:
        lines.append("")
        lines.append("ЧТО НЕ СРАБОТАЛО (не повторяй):")
        for i in bad:
            lines.append(f"• {i['title']}")
    return "\n".join(lines)


async def learn_from(text: str, source: str = "") -> list[dict]:
    """Достаёт из текста (разбор ролика, отчёт, фидбек) переиспользуемые уроки.

    Дешёвая модель, короткий ответ — вызов стоит копейки, а память растёт сама.
    """
    if not (text or "").strip():
        return []
    from core.ai_router import ai_router, ECONOMY_MODELS

    system = ("Ты — память SMM-агента. Из текста выдели ПЕРЕИСПОЛЬЗУЕМЫЕ уроки: "
              "рабочие хуки, форматы, визуальные приёмы, факты об аудитории, "
              "и отдельно — что НЕ сработало. Только то, что пригодится в будущих "
              "роликах. Отвечай СТРОГО JSON, максимум 5 записей, коротко.")
    prompt = (f"Источник: {source or 'без источника'}\n\nТекст:\n{text[:4000]}\n\n"
              'JSON: {"skills":[{"kind":"hook|format|visual|audience|mistake|rule",'
              '"title":"суть одной строкой","body":"деталь, как применять"}]}')
    model = ECONOMY_MODELS.get("reviewer", "gemini-2.0-flash-lite")
    try:
        res = await ai_router.call(model, system, prompt)
        t = res.get("text", "")
        data = json.loads(t[t.find("{"):t.rfind("}") + 1])
        saved = []
        for s in data.get("skills", [])[:5]:
            if s.get("title"):
                saved.append(add_skill(s.get("kind", "rule"), s["title"],
                                       s.get("body", ""), tags=[source] if source else []))
        return saved
    except Exception:
        return []


def stats() -> dict:
    items = _load()
    by_kind = {}
    for i in items:
        by_kind[i.get("kind", "rule")] = by_kind.get(i.get("kind", "rule"), 0) + 1
    return {"total": len(items), "by_kind": by_kind}
