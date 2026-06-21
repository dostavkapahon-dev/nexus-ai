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
    video_url = Column(String)
    image_prompt = Column(Text)
    score = Column(Float)
    platform_versions = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

class Publication(Base):
    __tablename__ = 'publications'
    id = Column(String, primary_key=True, default=gen_id)
    plan_id = Column(String)
    platform = Column(String)
    published_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default='published')
    external_id = Column(String)

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
    updated_at = Column(DateTime, default=datetime.utcnow)

class UserProfile(Base):
    """Global user profile — product description, brand style, strategy settings."""
    __tablename__ = 'user_profile'
    id = Column(String, primary_key=True, default=gen_id)
    product_description = Column(Text, default='')
    brand_style = Column(Text, default='')
    strategy_focus = Column(String, default='subscribers')   # subscribers / sales / engagement
    strategy_duration = Column(Integer, default=30)          # 30 / 60 / 90 days
    ai_mode = Column(String, default='economy')              # economy / premium
    active_ai = Column(String, default='claude')             # claude / gpt4o / deepseek / gemini / sonar
    google_drive_folder_id = Column(String, default='')
    google_drive_access_token = Column(Text, default='')     # OAuth token from Google Sign-In
    updated_at = Column(DateTime, default=datetime.utcnow)

class AutomationConfig(Base):
    """Singleton automation settings — master switch, schedule and content options."""
    __tablename__ = 'automation_config'
    id = Column(Integer, primary_key=True, default=1)
    enabled = Column(Boolean, default=False)            # master on/off
    autopilot = Column(Boolean, default=True)           # auto-create plans for active niches
    auto_video = Column(Boolean, default=False)         # generate a video clip per post
    video_provider = Column(String, default='auto')     # auto / heygen / higgsfield / runway
    schedule_trends = Column(Integer, default=9)        # hour (UTC) for trend analysis
    schedule_generate = Column(Integer, default=12)     # hour (UTC) for content generation
    schedule_publish = Column(Integer, default=18)      # hour (UTC) for publishing
    schedule_report = Column(Integer, default=23)       # hour (UTC) for daily report
    batch_size = Column(Integer, default=10)            # max items per generate/publish run
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class NicheAnalysisCache(Base):
    """Cached niche analysis stored on Google Drive — avoid re-analysis."""
    __tablename__ = 'niche_analysis_cache'
    id = Column(String, primary_key=True, default=gen_id)
    niche_key = Column(String, unique=True, nullable=False)  # "{name}:{city}" lowercased
    drive_file_id = Column(String)
    drive_url = Column(String)
    analysis_data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
