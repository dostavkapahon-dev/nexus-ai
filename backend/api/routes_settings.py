import os
import asyncio
import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from database.db import get_db
from database.models import Connection, AgentLog, ContentPlan, GeneratedContent, Publication
from pydantic import BaseModel
from typing import Optional

router = APIRouter(tags=["settings"])

def mask(value):
    if not value or len(value) < 8:
        return ""
    return value[:4] + "****" + value[-4:]

class ConnectionsBody(BaseModel):
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    perplexity_api_key: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    telegram_post_chat_id: Optional[str] = None
    instagram_access_token: Optional[str] = None
    instagram_account_id: Optional[str] = None
    # Приложение Meta для подключения Instagram в один клик. Без этих трёх полей
    # OAuth-кнопка не работала, а вписать их в дашборде было некуда — оставался
    # только ручной путь через Graph API Explorer.
    facebook_app_id: Optional[str] = None
    facebook_app_secret: Optional[str] = None
    nexus_public_url: Optional[str] = None
    # Cookies площадок для публикации через браузер без API-ключей. Принимается
    # как экспорт расширения (массив), так и storage_state Playwright.
    instagram_verify_token: Optional[str] = None   # подтверждение подписки на вебхуки
    # В приложении без Facebook секрет для подписи вебхуков называется
    # Instagram app secret — отдельное поле, чтобы не заставлять заполнять «facebook».
    instagram_app_secret: Optional[str] = None
    instagram_token_type: Optional[str] = None     # facebook | instagram — способ продления
    nexus_browser_storage_state: Optional[str] = None
    nexus_publish_mode: Optional[str] = None
    nexus_browser_cdp: Optional[str] = None
    tiktok_access_token: Optional[str] = None
    brightdata_api_key: Optional[str] = None
    ig_handle: Optional[str] = None
    tiktok_handle: Optional[str] = None
    youtube_handle: Optional[str] = None
    google_service_account_json: Optional[str] = None
    youtube_api_key: Optional[str] = None
    deepseek_api_key: Optional[str] = None
    nvidia_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    cerebras_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    mistral_api_key: Optional[str] = None
    github_models_token: Optional[str] = None
    vk_access_token: Optional[str] = None
    vk_group_id: Optional[str] = None
    threads_access_token: Optional[str] = None
    threads_user_id: Optional[str] = None
    heygen_api_key: Optional[str] = None
    heygen_avatar_id: Optional[str] = None
    heygen_voice_id: Optional[str] = None
    higgsfield_api_key: Optional[str] = None
    higgsfield_secret: Optional[str] = None
    higgsfield_model: Optional[str] = None
    runway_api_key: Optional[str] = None
    elevenlabs_api_key: Optional[str] = None
    nexus_token: Optional[str] = None

@router.get("/api/connections")
async def get_connections(db: AsyncSession = Depends(get_db)):
    """Возвращает сохранённые ключи в МАСКИРОВАННОМ виде.

    Источник — БД и переменные окружения (Render env). Это позволяет ключам
    «сохраняться» даже на бесплатном Render, где файловая БД обнуляется при
    перезапуске: достаточно задать их в Render → Environment.
    """
    result = await db.execute(select(Connection))
    db_map = {c.key_name: c.key_value for c in result.scalars()}

    out = {}
    known = list(ConnectionsBody.model_fields.keys())
    for key in known:
        val = db_map.get(key) or os.getenv(key.upper(), "")
        if val:
            out[key] = mask(val)
    # Любые прочие ключи из БД, не описанные явно
    for key, val in db_map.items():
        if key not in out and val:
            out[key] = mask(val)
    return out

@router.post("/api/connections")
async def save_connections(body: ConnectionsBody, db: AsyncSession = Depends(get_db)):
    data = body.model_dump(exclude_none=True)

    # Токен из панели Meta переносится по строкам, и вместе с ним копируются
    # пробелы и переводы строк — Meta на такой строке отвечает «Cannot parse
    # access token». Раньше чистил только путь «Подключить по токену», а этот —
    # нет, и один и тот же ключ вёл себя по-разному на двух страницах.
    if data.get("instagram_access_token"):
        from core.ig_connect import clean_token
        token = clean_token(data["instagram_access_token"])
        data["instagram_access_token"] = token
        # От типа зависит и адрес API, и способ продления через 60 дней.
        # Без этого прошлый сохранённый тип молча применялся к новому токену.
        if "****" not in token:
            data["instagram_token_type"] = "instagram" if token.startswith("IGAA") else "facebook"

    for key_name, key_value in data.items():
        if not key_value or "****" in key_value:
            continue
        result = await db.execute(select(Connection).where(Connection.key_name == key_name))
        conn = result.scalar_one_or_none()
        if conn:
            conn.key_value = key_value
        else:
            db.add(Connection(key_name=key_name, key_value=key_value))
        os.environ[key_name.upper()] = key_value
    await db.commit()
    return {"ok": True}

@router.post("/api/connections/test")
async def test_connections(body: ConnectionsBody, db: AsyncSession = Depends(get_db)):
    results = {}
    data = body.model_dump(exclude_none=True)
    db_result = await db.execute(select(Connection))
    db_map = {c.key_name: c.key_value for c in db_result.scalars()}

    def resolve(key):
        val = data.get(key, "")
        if val and "****" not in val:
            return val
        return db_map.get(key)

    if key := resolve("anthropic_api_key"):
        try:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=key)
            await client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=10, messages=[{"role":"user","content":"hi"}])
            results["anthropic_api_key"] = {"ok": True, "message": "Claude подключён ✓"}
        except Exception as e:
            results["anthropic_api_key"] = {"ok": False, "message": str(e)[:120]}

    # Бесплатные OpenAI-совместимые провайдеры проверяются одинаково — запросом
    # к их каталогу моделей: ключ живой, если каталог отдался.
    from core.ai_router import FREE_PROVIDERS
    for _pname, _spec in FREE_PROVIDERS.items():
        field = _spec["key_env"].lower()
        if not (k := resolve(field)):
            continue
        try:
            url = _spec["base_url"] + _spec.get("models_path", "/models")
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.get(url, headers={"Authorization": f"Bearer {k}"})
            if r.status_code == 200:
                payload = r.json()
                raw = payload.get("data") if isinstance(payload, dict) else payload
                results[field] = {"ok": True,
                                  "message": f"{_spec['title']} подключён ✓ ({len(raw or [])} моделей)"}
            else:
                results[field] = {"ok": False, "message": f"HTTP {r.status_code}: {r.text[:80]}"}
        except Exception as e:
            results[field] = {"ok": False, "message": str(e)[:120]}

    if key := resolve("openai_api_key"):
        try:
            import openai
            client = openai.AsyncOpenAI(api_key=key)
            await client.models.list()
            results["openai_api_key"] = {"ok": True, "message": "OpenAI подключён ✓"}
        except Exception as e:
            results["openai_api_key"] = {"ok": False, "message": str(e)[:120]}

    if key := resolve("gemini_api_key"):
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={key}")
                if r.status_code == 200:
                    results["gemini_api_key"] = {"ok": True, "message": "Gemini подключён ✓"}
                else:
                    results["gemini_api_key"] = {"ok": False, "message": r.json().get("error",{}).get("message","Ошибка")}
        except Exception as e:
            results["gemini_api_key"] = {"ok": False, "message": str(e)[:120]}

    if key := resolve("telegram_bot_token"):
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"https://api.telegram.org/bot{key}/getMe")
                d = r.json()
                if d.get("ok"):
                    results["telegram_bot_token"] = {"ok": True, "message": f"@{d['result']['username']} ✓"}
                else:
                    results["telegram_bot_token"] = {"ok": False, "message": d.get("description","Неверный токен")}
        except Exception as e:
            results["telegram_bot_token"] = {"ok": False, "message": str(e)[:120]}

    if key := resolve("instagram_access_token"):
        # У Meta два несовместимых API, и токен живёт только в своём. Токен
        # Instagram Login (IGAA…) на graph.facebook.com — не токен, а просто
        # строка, и Facebook отвечает «Cannot parse access token». Рабочий ключ
        # выглядел сломанным, потому что проверялся не на том сервере.
        from core.ig_connect import clean_token
        key = clean_token(key)
        is_ig = key.startswith("IGAA")
        endpoint = ("https://graph.instagram.com/v21.0/me" if is_ig
                    else "https://graph.facebook.com/v19.0/me")
        fields = "id,username" if is_ig else "id,name"
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(endpoint, params={"access_token": key, "fields": fields})
                d = r.json()
                if "error" in d:
                    results["instagram_access_token"] = {"ok": False, "message": d["error"]["message"][:120]}
                else:
                    name = d.get("username") or d.get("name") or d.get("id")
                    results["instagram_access_token"] = {"ok": True, "message": f"Аккаунт: {name} ✓"}
        except Exception as e:
            results["instagram_access_token"] = {"ok": False, "message": str(e)[:120]}

    if key := resolve("brightdata_api_key"):
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.post(
                    "https://api.brightdata.com/request",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={"zone": os.getenv("BRIGHTDATA_ZONE", "web_unlocker1"),
                          "url": "https://geo.brdtest.com/welcome.txt", "format": "raw"},
                )
                if r.status_code == 200:
                    results["brightdata_api_key"] = {"ok": True, "message": "Bright Data подключён ✓"}
                else:
                    results["brightdata_api_key"] = {"ok": False, "message": f"HTTP {r.status_code}: {r.text[:100]}"}
        except Exception as e:
            results["brightdata_api_key"] = {"ok": False, "message": str(e)[:120]}

    return results

@router.get("/api/social/accounts")
async def social_accounts():
    """Какие аккаунты доступны для бесплатного анализа (по заданным никам)."""
    from core.social_intel import is_configured, get_user
    if not await is_configured():
        return {"configured": False, "accounts": []}
    try:
        d = await get_user()
        return {"configured": True, "accounts": d.get("activeSocialAccounts", []), "raw": d}
    except Exception as e:
        return {"configured": True, "error": str(e)[:200]}


class SocialAnalyticsBody(BaseModel):
    platforms: list[str] = ["instagram"]
    post_id: Optional[str] = None
    last_records: Optional[int] = 20


@router.post("/api/social/analytics/profile")
async def social_profile_analytics(body: SocialAnalyticsBody):
    """Аналитика профиля/шапки: подписчики + топ роликов (бесплатно, yt-dlp/Bright Data)."""
    from core.social_intel import is_configured, get_profile_analytics
    if not await is_configured():
        return {"error": "Укажите ники (IG_HANDLE/TIKTOK_HANDLE/YOUTUBE_HANDLE) или BRIGHTDATA_API_KEY"}
    try:
        return await get_profile_analytics(body.platforms)
    except Exception as e:
        return {"error": str(e)[:200]}


@router.post("/api/social/analytics/post")
async def social_post_analytics(body: SocialAnalyticsBody):
    """Аналитика ролика по ссылке (post_id = URL): просмотры, лайки, длительность."""
    from core.social_intel import get_post_analytics
    try:
        return await get_post_analytics(body.post_id, body.platforms)
    except Exception as e:
        return {"error": str(e)[:200]}


@router.post("/api/social/history")
async def social_history(body: SocialAnalyticsBody):
    """Последние ролики аккаунтов (бесплатно, по заданным никам)."""
    from core.social_intel import is_configured, get_recent_posts
    if not await is_configured():
        return {"error": "Укажите ники (IG_HANDLE/TIKTOK_HANDLE/YOUTUBE_HANDLE)"}
    try:
        return await get_recent_posts(body.platforms, body.last_records or 20)
    except Exception as e:
        return {"error": str(e)[:200]}


@router.post("/api/social/intelligence")
async def social_intelligence(body: SocialAnalyticsBody):
    """Досье аккаунта: профиль + топ роликов по вовлечённости — бесплатно (yt-dlp +
    опц. Bright Data), чтобы бот делал Reels на основе реальных данных, а не вслепую."""
    from core.social_intel import is_configured, get_account_intelligence
    if not await is_configured():
        return {"error": "Укажите ники (IG_HANDLE/TIKTOK_HANDLE/YOUTUBE_HANDLE) или BRIGHTDATA_API_KEY"}
    try:
        return await get_account_intelligence(body.platforms)
    except Exception as e:
        return {"error": str(e)[:200]}


def _probe_openai_compatible(base_url: str, key: str, models_path: str = "/models") -> dict:
    """Дёргает каталог моделей у OpenAI-совместимого провайдера."""
    try:
        r = httpx.get(base_url.rstrip("/") + models_path,
                      headers={"Authorization": f"Bearer {key}"}, timeout=20)
        if r.status_code == 200:
            return {"ok": True}
        body = r.text[:150]
        low = body.lower()
        if "quota" in low or r.status_code == 429:
            return {"ok": False, "error": "квота исчерпана"}
        return {"ok": False, "error": f"HTTP {r.status_code}: {body[:100]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


@router.get("/api/ai/providers")
async def ai_providers(db: AsyncSession = Depends(get_db)):
    """Живой статус всех ИИ-провайдеров: у кого есть ключ и кто реально отвечает.

    Показывает и платных, и бесплатных (Groq, Cerebras, NVIDIA и др.) —
    со ссылками на регистрацию и описанием лимитов у тех, где ключа нет.
    """
    # Подтягиваем ключи из БД: сохранённые через дашборд должны учитываться сразу.
    result = await db.execute(select(Connection))
    for c in result.scalars():
        if c.key_value and "****" not in (c.key_value or ""):
            os.environ.setdefault(c.key_name.upper(), c.key_value)

    from core.ai_router import (FREE_PROVIDERS, resolve_free_model,
                                resolve_gemini_model)
    out = []

    # ── Платные / основные ───────────────────────────────────────────────
    gem_key = os.getenv("GEMINI_API_KEY", "")
    gem = {"name": "Google Gemini", "key_env": "GEMINI_API_KEY", "free": False,
           "has_key": bool(gem_key), "ok": False, "model": None,
           "limits": "бесплатный тариф с суточным лимитом",
           "signup": "https://aistudio.google.com/apikey", "error": None}
    if gem_key:
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.get("https://generativelanguage.googleapis.com/v1beta/models",
                                params={"key": gem_key})
            if r.status_code == 200:
                gem["ok"] = True
                gem["model"] = resolve_gemini_model()
            else:
                gem["error"] = r.json().get("error", {}).get("message", "ошибка")[:120]
        except Exception as e:
            gem["error"] = str(e)[:120]
    out.append(gem)

    oa_key = os.getenv("OPENAI_API_KEY", "")
    oa = {"name": "OpenAI", "key_env": "OPENAI_API_KEY", "free": False,
          "has_key": bool(oa_key), "ok": False, "model": "gpt-4o-mini",
          "limits": "платный, по балансу", "signup": "https://platform.openai.com/api-keys",
          "error": None}
    if oa_key:
        probe = await asyncio.to_thread(_probe_openai_compatible,
                                        "https://api.openai.com/v1", oa_key)
        oa["ok"] = probe["ok"]
        oa["error"] = probe.get("error")
    out.append(oa)

    for title, env, url, signup, limits in (
        ("Anthropic Claude", "ANTHROPIC_API_KEY", None,
         "https://console.anthropic.com/settings/keys", "платный, по балансу"),
        ("DeepSeek", "DEEPSEEK_API_KEY", "https://api.deepseek.com",
         "https://platform.deepseek.com", "очень дёшево, центы за сотни запросов"),
        ("Perplexity", "PERPLEXITY_API_KEY", None,
         "https://www.perplexity.ai/settings/api", "платный — поиск трендов в реальном времени"),
    ):
        key = os.getenv(env, "")
        item = {"name": title, "key_env": env, "free": False, "has_key": bool(key),
                "ok": False, "model": None, "limits": limits, "signup": signup, "error": None}
        if key and url:
            probe = await asyncio.to_thread(_probe_openai_compatible, url, key)
            item["ok"] = probe["ok"]
            item["error"] = probe.get("error")
        elif key:
            item["ok"] = True  # ключ есть, отдельная проверка не нужна
        out.append(item)

    # ── Бесплатные (реестр из ai_router) ─────────────────────────────────
    for name, spec in FREE_PROVIDERS.items():
        key = os.getenv(spec["key_env"], "")
        item = {"name": spec["title"], "key_env": spec["key_env"], "free": True,
                "has_key": bool(key), "ok": False, "model": None,
                "limits": spec.get("limits", ""), "signup": spec.get("signup", ""),
                "error": None}
        if key:
            probe = await asyncio.to_thread(
                _probe_openai_compatible, spec["base_url"], key,
                spec.get("models_path", "/models"))
            item["ok"] = probe["ok"]
            item["error"] = probe.get("error")
            if item["ok"]:
                item["model"] = await asyncio.to_thread(resolve_free_model, name)
        out.append(item)

    working = [p["name"] for p in out if p["ok"]]
    return {"providers": out, "working": working,
            "ready": bool(working),
            "agents": ["niche_analyst", "viral_hunter", "strategist", "copywriter",
                       "reviewer", "voice_adapter", "visual_creator", "adapter",
                       "trend_analyst", "funnel_agent", "reporter"]}


class SkillBody(BaseModel):
    kind: Optional[str] = "rule"
    title: Optional[str] = None
    body: Optional[str] = None


@router.get("/api/agent/skills")
async def agent_skills():
    """Память агента: что уже сработало и чего он избегает."""
    from core.skills_store import list_skills, stats, KINDS
    return {"skills": list_skills(), "stats": stats(), "kinds": list(KINDS)}


@router.post("/api/agent/skills")
async def agent_skill_add(body: SkillBody):
    from core.skills_store import add_skill
    if not (body.title or "").strip():
        return {"ok": False, "error": "нужен заголовок"}
    return {"ok": True, "skill": add_skill(body.kind or "rule", body.title, body.body or "")}


@router.delete("/api/agent/skills/{skill_id}")
async def agent_skill_delete(skill_id: str):
    from core.skills_store import delete_skill
    return {"ok": delete_skill(skill_id)}


class AgentConfigBody(BaseModel):
    brand_voice: Optional[str] = None


@router.get("/api/agent/config")
async def agent_config():
    """Специфика агента: голос бренда + текущее состояние возможностей."""
    from core.brand import get_brand_voice, BRAND, PLATFORM_SPECS
    from core.skills_store import stats
    try:
        from api.routes_desktop import desktop_connected
        from core import server_browser
        pc = desktop_connected() or server_browser.enabled()
    except Exception:
        pc = False
    return {
        "brand_voice": get_brand_voice(),
        "brand": {"name": BRAND.get("name"), "colors": BRAND.get("colors")},
        "platforms": list(PLATFORM_SPECS.keys()),
        "skills": stats(),
        "capabilities": {
            "pc_control": pc,
            "web_search": True,
            "vision": bool(os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY")
                           or os.getenv("ANTHROPIC_API_KEY")),
            # Публиковать можно и без API — через браузер (ПК-агент или серверный).
            "social": bool(os.getenv("INSTAGRAM_ACCESS_TOKEN") or os.getenv("TIKTOK_ACCESS_TOKEN")
                           or os.getenv("VK_ACCESS_TOKEN") or os.getenv("THREADS_ACCESS_TOKEN")) or pc,
            "analysis": bool(os.getenv("IG_HANDLE") or os.getenv("TIKTOK_HANDLE")
                             or os.getenv("YOUTUBE_HANDLE") or os.getenv("BRIGHTDATA_API_KEY")),
            "telegram": bool(os.getenv("TELEGRAM_BOT_TOKEN")),
            "montage": True,
        },
    }


@router.post("/api/agent/config")
async def agent_config_save(body: AgentConfigBody):
    from core.brand import set_brand_voice
    if body.brand_voice is not None:
        set_brand_voice(body.brand_voice)
    return {"ok": True}


@router.get("/api/bot/status")
async def bot_status(db: AsyncSession = Depends(get_db)):
    """Статус Telegram-бота: имя, задан ли админ-чат и группа постов."""
    db_result = await db.execute(select(Connection))
    db_map = {c.key_name: c.key_value for c in db_result.scalars()}
    token = db_map.get("telegram_bot_token") or os.getenv("TELEGRAM_BOT_TOKEN", "")
    admin = db_map.get("telegram_chat_id") or os.getenv("TELEGRAM_CHAT_ID", "")
    group = db_map.get("telegram_post_chat_id") or os.getenv("TELEGRAM_POST_CHAT_ID", "")
    out = {"has_token": bool(token), "admin_chat_id": bool(admin),
           "post_chat_id": group or "", "username": None, "ok": False}
    if not token:
        return out
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"https://api.telegram.org/bot{token}/getMe")
            d = r.json()
            if d.get("ok"):
                out["ok"] = True
                out["username"] = d["result"].get("username")
    except Exception as e:
        out["error"] = str(e)[:120]
    return out


class BotTestBody(BaseModel):
    chat_id: Optional[str] = None


@router.post("/api/bot/test-post")
async def bot_test_post(body: BotTestBody, db: AsyncSession = Depends(get_db)):
    """Отправляет тестовое сообщение в группу постов (или указанный chat_id)."""
    db_result = await db.execute(select(Connection))
    db_map = {c.key_name: c.key_value for c in db_result.scalars()}
    token = db_map.get("telegram_bot_token") or os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = body.chat_id or db_map.get("telegram_post_chat_id") or os.getenv("TELEGRAM_POST_CHAT_ID", "") \
        or db_map.get("telegram_chat_id") or os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return {"ok": False, "message": "Не задан токен бота или chat_id группы"}
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"https://api.telegram.org/bot{token}/sendMessage",
                             json={"chat_id": chat, "text": "✅ NEXUS AI: группа подключена — сюда будут приходить посты."})
            d = r.json()
            if d.get("ok"):
                return {"ok": True, "message": "Отправлено ✓ Проверь группу"}
            return {"ok": False, "message": d.get("description", "Ошибка")[:150]}
    except Exception as e:
        return {"ok": False, "message": str(e)[:150]}


@router.get("/api/analytics/{niche_id}")
async def get_analytics(niche_id: str, db: AsyncSession = Depends(get_db)):
    total_planned = await db.scalar(select(func.count(ContentPlan.id)).where(ContentPlan.niche_id == niche_id))
    total_generated = await db.scalar(select(func.count(ContentPlan.id)).where(ContentPlan.niche_id == niche_id, ContentPlan.status == 'generated'))
    total_published = await db.scalar(select(func.count(ContentPlan.id)).where(ContentPlan.niche_id == niche_id, ContentPlan.status == 'published'))
    total_tokens = await db.scalar(select(func.sum(AgentLog.tokens_used)).where(AgentLog.niche_id == niche_id)) or 0
    total_cost = await db.scalar(select(func.sum(AgentLog.cost_usd)).where(AgentLog.niche_id == niche_id)) or 0
    logs_result = await db.execute(select(AgentLog).where(AgentLog.niche_id == niche_id).order_by(AgentLog.created_at.desc()).limit(20))
    logs = [{"agent_name": l.agent_name, "status": l.status, "model_used": l.model_used, "tokens_used": l.tokens_used, "duration_sec": l.duration_sec} for l in logs_result.scalars()]
    return {"total_planned": total_planned, "total_generated": total_generated, "total_published": total_published, "total_tokens": total_tokens, "total_cost": round(total_cost, 4), "recent_logs": logs}
