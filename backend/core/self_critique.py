"""
Самопроверка агентов перед дорогой задачей.

Дешёвая модель заранее смотрит на задание: хватает ли данных, что уточнить,
и как сформулировать точнее. Это экономит токены (не гоняем дорогую модель
вслепую) и повышает качество результата.

Правило: самопроверка ВСЕГДА на дешёвой модели и коротким ответом.
"""
import json
from core.ai_router import ai_router, ECONOMY_MODELS

CHECK_SYSTEM = (
    "Ты — контролёр качества AI-агентов. Тебе дают задачу агента и доступные данные. "
    "Оцени, хватит ли данных для хорошего результата, что критично уточнить, "
    "и как переформулировать задачу точнее. Отвечай СТРОГО JSON, очень кратко."
)

CHECK_TEMPLATE = """Агент: {agent}
Задача: {task}
Доступные данные: {context}

JSON:
{{"ready": true/false,
  "missing": ["чего не хватает", ...],
  "questions": ["вопрос пользователю", ...],
  "improved_task": "уточнённая формулировка задачи",
  "skip_reason": "если задачу лучше не запускать — почему, иначе пусто"}}"""


async def pre_check(agent: str, task: str, context: str = "", model: str = None) -> dict:
    """Дешёвая самопроверка перед запуском агента.

    Возвращает {checked, ready, missing, questions, improved_task, skip_reason}.
    При любой ошибке — считаем, что можно работать (не блокируем конвейер),
    но `checked=False` честно говорит, что проверки не было: иначе отчёт
    показывает «готов к работе» там, где просто не отвечает ИИ.
    """
    model = model or ECONOMY_MODELS.get("reviewer", "gemini-2.0-flash")
    prompt = CHECK_TEMPLATE.format(agent=agent, task=task[:1500],
                                   context=(context or "нет")[:3000])
    try:
        res = await ai_router.call(model, CHECK_SYSTEM, prompt)
        text = res.get("text", "")
        s, e = text.find("{"), text.rfind("}") + 1
        data = json.loads(text[s:e])
        data.setdefault("ready", True)
        data.setdefault("questions", [])
        data.setdefault("improved_task", task)
        data["checked"] = True
        return data
    except Exception as e:
        return {"checked": False, "error": str(e)[:200], "ready": True,
                "missing": [], "questions": [], "improved_task": task,
                "skip_reason": ""}
