from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database.models import CustomPrompt

DEFAULT_PROMPTS = {
    "niche_analyst": {
        "system": "You are NicheAnalyst, an expert in social media niche research. Always respond in JSON.",
        "template": "Analyze this niche for social media content creation:\nNiche: {niche}\nCity: {city}\nGoal: {goal}\nTone: {tone}\n\nRespond with JSON: {\"audience\": {...}, \"pain_points\": [...], \"content_pillars\": [...], \"competitors\": [...], \"best_times\": [...]}",
        "model": "claude-sonnet-4-20250514"
    },
    "viral_hunter": {
        "system": "You are ViralHunter, expert at identifying viral content patterns. Respond in JSON.",
        "template": "Find viral content patterns for niche: {niche}\nPlatforms: {platforms}\nAudience: {audience}\n\nRespond with JSON: {\"viral_topics\": [...], \"hooks\": [...], \"formats\": [...], \"hashtags\": [...]}",
        "model": "claude-sonnet-4-20250514"
    },
    "strategist": {
        "system": "You are ContentStrategist. Create detailed 30-day content plans. Respond in JSON array.",
        "template": "Create a 30-day content plan for:\nNiche: {niche}\nPlatforms: {platforms}\nGoal: {goal}\nPosts/day: {posts_per_day}\nViral patterns: {viral_data}\n\nRespond with JSON array of 30 items: [{\"day\": 1, \"platform\": \"telegram\", \"topic\": \"...\", \"hook\": \"...\", \"format\": \"post\"}]",
        "model": "claude-sonnet-4-20250514"
    },
    "copywriter": {
        "system": "You are an expert copywriter for social media. Write engaging, viral posts.",
        "template": "Write a social media post:\nNiche: {niche}\nTopic: {topic}\nHook: {hook}\nTone: {tone}\nPlatform: {platform}\nGoal: {goal}\n\nWrite the full post text only, no explanations.",
        "model": "gpt-4o"
    },
    "reviewer": {
        "system": "You are ContentReviewer. Evaluate and improve social media posts. Respond in JSON.",
        "template": "Review this post for {platform}:\n\n{text}\n\nNiche: {niche}, Goal: {goal}\n\nRespond with JSON: {\"text_reviewed\": \"improved text\", \"score\": 8.5, \"improvements\": [...]}",
        "model": "claude-sonnet-4-20250514"
    },
    "visual_creator": {
        "system": "You are VisualCreator. Generate image prompts for social media posts.",
        "template": "Create an image generation prompt for this post:\nTopic: {topic}\nNiche: {niche}\nPlatform: {platform}\nPost text: {text}\n\nWrite only the image prompt, detailed and visual, in English.",
        "model": "gpt-4o"
    },
    "voice_adapter": {
        "system": "You are VoiceAdapter. Adapt content to match the user's personal writing style.",
        "template": "Adapt this post to match the user's voice:\n\nOriginal post:\n{text}\n\nAbout the user: {about_user}\nTone: {tone}\n\nRewrite maintaining the same message but in their authentic voice.",
        "model": "claude-sonnet-4-20250514"
    },
    "adapter": {
        "system": "You are PlatformAdapter. Optimize content for specific social media platforms. Respond in JSON.",
        "template": "Adapt this post for multiple platforms:\n\nPost: {text}\nNiche: {niche}\n\nRespond with JSON: {\"telegram\": \"...\", \"instagram\": \"...\", \"tiktok\": \"...\"}. Respect character limits and platform norms.",
        "model": "gpt-4o-mini"
    }
}

async def get_prompt(db: AsyncSession, agent_name: str) -> dict:
    result = await db.execute(select(CustomPrompt).where(CustomPrompt.agent_name == agent_name))
    custom = result.scalar_one_or_none()
    default = DEFAULT_PROMPTS.get(agent_name, {})
    if custom:
        return {
            "system": custom.system_prompt or default.get("system", ""),
            "template": custom.user_prompt_template or default.get("template", ""),
            "model": custom.ai_model or default.get("model", "claude-sonnet-4-20250514")
        }
    return default

async def save_prompt(db: AsyncSession, agent_name: str, system_prompt: str, user_prompt_template: str, ai_model: str):
    result = await db.execute(select(CustomPrompt).where(CustomPrompt.agent_name == agent_name))
    custom = result.scalar_one_or_none()
    if custom:
        custom.system_prompt = system_prompt
        custom.user_prompt_template = user_prompt_template
        custom.ai_model = ai_model
        custom.updated_at = datetime.utcnow()
    else:
        db.add(CustomPrompt(
            agent_name=agent_name,
            system_prompt=system_prompt,
            user_prompt_template=user_prompt_template,
            ai_model=ai_model
        ))
    await db.commit()

async def reset_prompt(db: AsyncSession, agent_name: str):
    result = await db.execute(select(CustomPrompt).where(CustomPrompt.agent_name == agent_name))
    custom = result.scalar_one_or_none()
    if custom:
        await db.delete(custom)
        await db.commit()
    return DEFAULT_PROMPTS.get(agent_name, {})
