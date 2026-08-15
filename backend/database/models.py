import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, JSON
from sqlalchemy.orm import DeclarativeBase

def gen_id():
    return str(uuid.uuid4())

class Base(DeclarativeBase):
    pass

class Niche(Base):
    __tablename__ = 'niches'
    id = Column(String, primary_key=True, default=gen_id)
    name = Column(String, nullable=False)
    city = Column(String, default='')
    goal = Column(String, default='subscribers')
    budget_usd = Column(Float, default=0)
    posts_per_day = Column(Integer, default=1)
    platforms = Column(JSON, default=list)
    tone_of_voice = Column(String, default='neutral')
    about_user = Column(Text, default='')
    status = Column(String, default='active')
    created_at = Column(DateTime, default=datetime.utcnow)

class ContentPlan(Base):
    __tablename__ = 'content_plans'
    id = Column(String, primary_key=True, default=gen_id)
    niche_id = Column(String, nullable=False)
    day_number = Column(Integer)
    platform = Column(String)
    topic = Column(String)
    hook = Column(Text)
    format = Column(String, default='post')
    status = Column(String, default='pending')
    created_at = Column(DateTime, default=datetime.utcnow)

class GeneratedContent(Base):
    __tablename__ = 'generated_content'
    id = Column(String, primary_key=True, default=gen_id)
    plan_id = Column(String, nullable=False)
    text = Column(Text)
    text_reviewed = Column(Text)
    image_url = Column(String)
    image_prompt = Column(Text)
    score = Column(Float)
    platform_versions = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

class Publication(Base):
    """Факт публикации + её реальные метрики.

    Раньше хранился только факт («опубликовано»), поэтому сравнить «до/после» и
    учиться на результатах было невозможно. Теперь метрики собираются джобом и
    ложатся сюда — на них опирается память агента и стратегия.
    """
    __tablename__ = 'publications'
    id = Column(String, primary_key=True, default=gen_id)
    plan_id = Column(String, index=True)
    niche_id = Column(String, index=True)
    platform = Column(String)
    published_at = Column(DateTime, default=datetime.utcnow, index=True)
    status = Column(String, default='published')
    external_id = Column(String)
    post_url = Column(String)
    # Реальные метрики площадки
    views = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    saves = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    reach = Column(Integer, default=0)
    engagement_rate = Column(Float, default=0.0)     # (лайки+комменты+сохр.)/охват, %
    metrics_updated_at = Column(DateTime)
    # Что именно опубликовали — чтобы связать результат с приёмом
    topic = Column(String)
    hook = Column(Text)
    content_format = Column(String)
    # Под какой стратегией вышел пост — без этого нельзя сравнить их результативность
    strategy_id = Column(String, index=True)
    # Очередь и повторы: публикация — сетевая операция, и разовый сбой не должен
    # означать потерянный пост. Состояние живёт в БД, поэтому переживает рестарт.
    # status: scheduled | retrying | published | failed | blocked | cancelled
    scheduled_at = Column(DateTime, index=True)   # когда публиковать (очередь расписания)
    next_retry_at = Column(DateTime, index=True)  # когда следующая попытка
    attempts = Column(Integer, default=0)
    last_error = Column(Text)
    text = Column(Text)                           # что публикуем — иначе повтор невозможен
    image_url = Column(Text)
    # Видео публикуется тем же путём, что и картинка: без своего поля повтор
    # упавшего ролика превращался в повтор голого текста.
    video_url = Column(Text)
    task_id = Column(String, index=True)

class AgentLog(Base):
    __tablename__ = 'agent_logs'
    id = Column(String, primary_key=True, default=gen_id)
    niche_id = Column(String)
    agent_name = Column(String)
    status = Column(String)
    model_used = Column(String)
    tokens_used = Column(Integer, default=0)
    cost_usd = Column(Float, default=0)
    duration_sec = Column(Float, default=0)
    error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

class CustomPrompt(Base):
    __tablename__ = 'custom_prompts'
    id = Column(String, primary_key=True, default=gen_id)
    agent_name = Column(String, unique=True, nullable=False)
    system_prompt = Column(Text)
    user_prompt_template = Column(Text)
    ai_model = Column(String)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Connection(Base):
    __tablename__ = 'connections'
    id = Column(String, primary_key=True, default=gen_id)
    key_name = Column(String, unique=True, nullable=False)
    key_value = Column(Text)
    # Когда подключение появилось и когда его меняли — без этого в интерфейсе
    # нельзя ответить на вопрос «когда я это подключал».
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Результат последней проверки связи: чтобы страница подключений показывала
    # состояние сразу, а не дёргала провайдера при каждом открытии.
    last_check_at = Column(DateTime)
    last_check_ok = Column(Boolean)
    last_check_error = Column(String)

class UserProfile(Base):
    """Global user profile — product description, brand style, strategy settings."""
    __tablename__ = 'user_profile'
    id = Column(String, primary_key=True, default=gen_id)
    product_description = Column(Text, default='')
    brand_style = Column(Text, default='')
    strategy_focus = Column(String, default='subscribers')   # subscribers / sales / engagement
    strategy_duration = Column(Integer, default=30)          # 30 / 60 / 90 days
    ai_mode = Column(String, default='economy')              # economy / premium
    budget_usd_day = Column(Float, default=0.0)              # 0 = берём из AI_BUDGET_USD_DAY
    active_ai = Column(String, default='claude')             # claude / gpt4o / deepseek / gemini / sonar
    google_drive_folder_id = Column(String, default='')
    google_drive_access_token = Column(Text, default='')     # OAuth token from Google Sign-In
    updated_at = Column(DateTime, default=datetime.utcnow)

class NicheAnalysisCache(Base):
    """Cached niche analysis stored on Google Drive — avoid re-analysis."""
    __tablename__ = 'niche_analysis_cache'
    id = Column(String, primary_key=True, default=gen_id)
    niche_key = Column(String, unique=True, nullable=False)  # "{name}:{city}" lowercased
    drive_file_id = Column(String)
    drive_url = Column(String)
    analysis_data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

class Task(Base):
    """Единица фоновой работы: запуск конвейера, фабрики, публикации, дирижёра.

    Даёт то, чего раньше не было: у каждой работы есть идентификатор, статус,
    журнал шагов, расход и текст ошибки — упавшая задача больше не исчезает бесследно.
    """
    __tablename__ = 'tasks'
    id = Column(String, primary_key=True)          # TASK-2026-000001
    source = Column(String, default='api')         # telegram | dashboard | scheduler | api | agent
    kind = Column(String, nullable=False)          # pipeline | factory | publish | generate | director | trends
    goal = Column(Text, default='')                # что просили, словами
    status = Column(String, default='CREATED', index=True)
    ref_id = Column(String, default='')            # niche_id / plan_id, если применимо
    steps = Column(JSON, default=list)             # [{ts, agent, action, ok, error}]
    agents = Column(JSON, default=list)
    models = Column(JSON, default=list)
    tokens = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    attempts = Column(Integer, default=0)
    error = Column(Text)
    result = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    duration_sec = Column(Float, default=0.0)


class Research(Base):
    """История исследований: тренды, разбор чужих роликов, анализ конкурентов.

    Раньше результат жил в одном KV-ключе `viral_recipe` и перезатирался при каждом
    запуске — сравнить «что менялось в нише» и вернуться к прошлым выводам было нельзя.
    """
    __tablename__ = 'research'
    id = Column(String, primary_key=True, default=gen_id)
    niche_id = Column(String, index=True)
    task_id = Column(String, index=True)          # какая задача это породила
    kind = Column(String, index=True)             # trends | viral | competitor | market
    query = Column(String)                        # ниша/запрос/ссылки
    summary = Column(Text)                        # краткий вывод для человека
    findings = Column(JSON)                       # структурированный результат
    sources = Column(JSON)                        # откуда взято (ссылки, аккаунты)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class Competitor(Base):
    """Отслеживаемый конкурент: срез метрик на дату.

    Строк на один аккаунт много — это история, по ней видно динамику
    (рост подписчиков, изменение вовлечённости), а не только «снимок сегодня».
    """
    __tablename__ = 'competitors'
    id = Column(String, primary_key=True, default=gen_id)
    niche_id = Column(String, index=True)
    platform = Column(String, index=True)
    handle = Column(String, index=True)
    followers = Column(Integer, default=0)
    posts_count = Column(Integer, default=0)
    avg_engagement = Column(Float, default=0.0)
    top_posts = Column(JSON)                      # что у них зашло
    checked_at = Column(DateTime, default=datetime.utcnow, index=True)
    active = Column(Boolean, default=True)        # следим ли за ним сейчас


class Strategy(Base):
    """Версия контент-стратегии с привязкой к нише и периодом действия.

    Раньше стратегия лежала в KV-ключах `last_strategy_options` / `chosen_strategy`:
    при выборе новой прошлая терялась, и нельзя было сравнить, какая работала лучше.
    Теперь у стратегий есть версии, период действия и измеримый результат.
    """
    __tablename__ = 'strategies'
    id = Column(String, primary_key=True, default=gen_id)
    niche_id = Column(String, index=True)
    version = Column(Integer, default=1)
    title = Column(String)
    angle = Column(Text)                 # угол подачи
    why = Column(Text)                   # почему сработает
    plan = Column(Text)                  # план на неделю
    pillars = Column(JSON)               # рубрики/контент-пиллары
    status = Column(String, default='draft', index=True)   # draft | active | archived
    source = Column(String, default='auto')                # auto | manual
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    activated_at = Column(DateTime)
    archived_at = Column(DateTime)
