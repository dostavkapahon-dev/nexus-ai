import React, { useState, useEffect } from 'react'
import { Plug, Save, CheckCircle, XCircle, Loader, Eye, EyeOff, ExternalLink, ChevronDown, ChevronUp, Trash2 } from 'lucide-react'
import { connections as connectionsApi } from '../lib/api'

const PROVIDERS = [
  {
    id: 'openrouter', name: 'OpenRouter (сотни ИИ)', icon: '🌐', color: 'from-purple-500 to-indigo-500',
    description: 'Один ключ — доступ к сотням моделей: Llama, Qwen, Grok, Gemini, GPT, DeepSeek и др.',
    fields: [{ key: 'openrouter_api_key', label: 'API Key', placeholder: 'sk-or-v1-...', secret: true }],
    steps: [
      { text: 'Откройте', link: 'https://openrouter.ai/keys', linkText: 'openrouter.ai/keys' },
      { text: 'Create Key → скопируйте (начинается с sk-or-)' },
      { text: 'В промптах агентов укажите модель в формате vendor/model, напр. meta-llama/llama-3.1-70b-instruct' },
      { text: 'Любая модель с «/» в имени автоматически идёт через OpenRouter' },
    ],
    models: ['vendor/model', 'qwen/qwen-2.5-72b', 'x-ai/grok-2'],
  },
  {
    id: 'custom_ai', name: 'Свой ИИ / локальная LLM', icon: '🧩', color: 'from-gray-500 to-slate-600',
    description: 'Любой OpenAI-совместимый endpoint: Ollama, LM Studio, vLLM, корпоративный шлюз',
    fields: [
      { key: 'custom_ai_base_url', label: 'Base URL', placeholder: 'http://localhost:11434/v1', secret: false },
      { key: 'custom_ai_api_key', label: 'API Key (опц.)', placeholder: 'sk-... или любой', secret: true },
    ],
    steps: [
      { text: 'Укажите base_url вашего OpenAI-совместимого сервера' },
      { text: 'Модели, не известные системе, при заданном Base URL идут сюда' },
      { text: 'Пример для Ollama: http://localhost:11434/v1, модель — llama3.1' },
    ],
    models: [],
  },
  {
    id: 'xai', name: 'xAI Grok', icon: '𝕏', color: 'from-neutral-600 to-black',
    description: 'Модели Grok от xAI (OpenAI-совместимый API)',
    fields: [{ key: 'xai_api_key', label: 'API Key', placeholder: 'xai-...', secret: true }],
    steps: [
      { text: 'Откройте', link: 'https://console.x.ai', linkText: 'console.x.ai' },
      { text: 'API Keys → Create → скопируйте ключ' },
      { text: 'Используйте модели grok-2-latest, grok-beta' },
    ],
    models: ['grok-2-latest', 'grok-beta'],
  },
  {
    id: 'mistral', name: 'Mistral AI', icon: '🐝', color: 'from-orange-400 to-amber-500',
    description: 'Европейские модели Mistral (OpenAI-совместимый API)',
    fields: [{ key: 'mistral_api_key', label: 'API Key', placeholder: '...', secret: true }],
    steps: [
      { text: 'Откройте', link: 'https://console.mistral.ai/api-keys', linkText: 'console.mistral.ai' },
      { text: 'Create new key → скопируйте' },
      { text: 'Модели: mistral-large-latest, mistral-small-latest' },
    ],
    models: ['mistral-large-latest', 'mistral-small-latest'],
  },
  {
    id: 'claude', name: 'Anthropic Claude', icon: '🤖', color: 'from-orange-500 to-red-500',
    description: 'Главный AI для анализа и рецензии контента',
    fields: [{ key: 'anthropic_api_key', label: 'API Key', placeholder: 'sk-ant-api03-...', secret: true }],
    steps: [
      { text: 'Откройте', link: 'https://console.anthropic.com', linkText: 'console.anthropic.com' },
      { text: 'Войдите или создайте аккаунт' },
      { text: 'Перейдите в API Keys → Create Key' },
      { text: 'Скопируйте ключ (начинается с sk-ant-)' },
    ],
    models: ['claude-sonnet-4-6', 'claude-haiku-4-5'],
  },
  {
    id: 'openai', name: 'OpenAI GPT-4o', icon: '⚡', color: 'from-green-500 to-emerald-500',
    description: 'Основной копирайтер — пишет тексты постов',
    fields: [{ key: 'openai_api_key', label: 'API Key', placeholder: 'sk-proj-...', secret: true }],
    steps: [
      { text: 'Откройте', link: 'https://platform.openai.com/api-keys', linkText: 'platform.openai.com/api-keys' },
      { text: 'Нажмите Create new secret key' },
      { text: 'Скопируйте ключ — показывается только один раз!' },
      { text: 'Убедитесь что на аккаунте есть баланс (минимум $5)' },
    ],
    models: ['gpt-4o', 'gpt-4o-mini'],
  },
  {
    id: 'gemini', name: 'Google Gemini', icon: '💎', color: 'from-blue-500 to-cyan-500',
    description: 'Резервный AI, используется при недоступности других',
    fields: [{ key: 'gemini_api_key', label: 'API Key', placeholder: 'AIzaSy...', secret: true }],
    steps: [
      { text: 'Откройте', link: 'https://aistudio.google.com/apikey', linkText: 'aistudio.google.com/apikey' },
      { text: 'Нажмите Create API Key' },
      { text: 'Выберите проект Google Cloud (или создайте новый)' },
      { text: 'Скопируйте ключ (начинается с AIza)' },
      { text: 'Бесплатный тариф: 1500 запросов/день' },
    ],
    models: ['gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-1.5-pro'],
  },
  {
    id: 'heygen', name: 'HeyGen AI', icon: '🎭', color: 'from-violet-500 to-fuchsia-500',
    description: 'AI-аватары: говорящие видео для Reels / Shorts / TikTok',
    fields: [
      { key: 'heygen_api_key', label: 'API Key', placeholder: 'XXXXXXXX...', secret: true },
      { key: 'heygen_avatar_id', label: 'Avatar ID (опц.)', placeholder: 'Daisy-inskirt-...', secret: false },
      { key: 'heygen_voice_id', label: 'Voice ID (опц.)', placeholder: '1bd001e7...', secret: false },
    ],
    steps: [
      { text: 'Откройте', link: 'https://app.heygen.com', linkText: 'app.heygen.com' },
      { text: 'Settings → API → Create API Token → скопируйте ключ' },
      { text: 'Выберите аватар и голос, скопируйте их ID (опционально)' },
      { text: 'Используется дирижёром и генератором видео для озвученных роликов' },
    ],
    models: [],
  },
  {
    id: 'higgsfield', name: 'HiggsField AI', icon: '🌌', color: 'from-amber-500 to-orange-600',
    description: 'Много AI-моделей видео: DoP, Soul, Kling, MiniMax, Seedance, Veo-3 и др.',
    fields: [
      { key: 'higgsfield_api_key', label: 'API Key', placeholder: 'hf_...', secret: true },
      { key: 'higgsfield_secret', label: 'Secret (опц.)', placeholder: '...', secret: true },
      { key: 'higgsfield_model', label: 'Модель по умолчанию', placeholder: 'higgsfield-dop', secret: false },
    ],
    steps: [
      { text: 'Откройте', link: 'https://higgsfield.ai', linkText: 'higgsfield.ai' },
      { text: 'Перейдите в раздел разработчика / API и создайте ключ' },
      { text: 'Вставьте ключ — он используется генератором видео (provider=higgsfield)' },
      { text: 'Модель можно менять на лету в запросе генерации видео' },
    ],
    models: ['dop', 'soul', 'kling-2.1', 'minimax', 'seedance', 'veo-3'],
  },
  {
    id: 'vk', name: 'ВКонтакте', icon: '🅥', color: 'from-blue-600 to-indigo-600',
    description: 'Публикация постов на стену сообщества ВКонтакте',
    fields: [
      { key: 'vk_access_token', label: 'Access Token', placeholder: 'vk1.a...', secret: true },
      { key: 'vk_group_id', label: 'Group ID', placeholder: '123456789', secret: false },
    ],
    steps: [
      { text: 'Создайте сообщество ВК и Standalone-приложение', link: 'https://dev.vk.com', linkText: 'dev.vk.com' },
      { text: 'Получите токен сообщества со scope: wall, photos, manage' },
      { text: 'Group ID — числовой id вашего сообщества (без знака минус)' },
    ],
    models: [],
  },
  {
    id: 'youtube', name: 'YouTube', icon: '▶️', color: 'from-red-500 to-rose-600',
    description: 'Поиск трендов + загрузка Shorts (через браузерного агента)',
    fields: [
      { key: 'youtube_api_key', label: 'API Key', placeholder: 'AIza...', secret: true },
    ],
    steps: [
      { text: 'Откройте', link: 'https://console.cloud.google.com', linkText: 'console.cloud.google.com' },
      { text: 'Включите YouTube Data API v3 → создайте API Key' },
      { text: 'Загрузка Shorts выполняется браузерным агентом в YouTube Studio' },
    ],
    models: [],
  },
  {
    id: 'desktop_agent', name: 'Браузерный агент', icon: '🖥️', color: 'from-slate-500 to-gray-600',
    description: 'Автономный агент на вашем ПК: видит браузер и сам выполняет задачи',
    fields: [
      { key: 'nexus_token', label: 'Agent Token', placeholder: 'любая секретная строка', secret: true },
    ],
    steps: [
      { text: 'На ПК: pip install websockets playwright && playwright install chromium' },
      { text: 'Запустите: python desktop_agent.py --server <URL_сервера> --token <ваш токен>' },
      { text: 'Войдите в нужные аккаунты (Instagram/VK/OLX) в открывшемся браузере' },
      { text: 'Теперь дирижёр и публикации могут управлять браузером как fallback' },
    ],
    models: [],
  },
  {
    id: 'telegram', name: 'Telegram Bot', icon: '✈️', color: 'from-sky-500 to-blue-500',
    description: 'Публикация постов в Telegram-канал или группу',
    fields: [
      { key: 'telegram_bot_token', label: 'Bot Token', placeholder: '123456789:ABCdef...', secret: true },
      { key: 'telegram_chat_id', label: 'Chat ID', placeholder: '-1001234567890', secret: false },
    ],
    steps: [
      { text: 'Найдите в Telegram', link: 'https://t.me/BotFather', linkText: '@BotFather' },
      { text: 'Отправьте /newbot → задайте имя и username бота' },
      { text: 'Скопируйте токен бота' },
      { text: 'Добавьте бота в канал как администратора' },
      { text: 'Chat ID: перешлите сообщение из канала боту', link: 'https://t.me/userinfobot', linkText: '@userinfobot' },
    ],
    models: [],
  },
  {
    id: 'analysis', name: 'Анализ аккаунтов (бесплатно)', icon: '📊', color: 'from-fuchsia-500 to-pink-600',
    description: 'Ники ваших (или конкурентных) аккаунтов — бот бесплатно тянет метрики и топ роликов через yt-dlp. Instagram — опционально через Bright Data.',
    fields: [
      { key: 'ig_handle', label: 'Instagram ник', placeholder: 'pakhon.studio', secret: false },
      { key: 'tiktok_handle', label: 'TikTok ник', placeholder: 'pakhon.studio', secret: false },
      { key: 'youtube_handle', label: 'YouTube @handle', placeholder: 'pakhonstudio', secret: false },
      { key: 'brightdata_api_key', label: 'Bright Data API Key (опц., для Instagram)', placeholder: 'bd_...', secret: true },
    ],
    steps: [
      { text: 'Укажите ники аккаунтов, которые нужно анализировать (свои или конкурентов) — без @' },
      { text: 'YouTube и TikTok анализируются бесплатно сразу, без ключей' },
      { text: 'Для Instagram (требует обхода логина) заведите ключ на', link: 'https://brightdata.com', linkText: 'Bright Data' },
      { text: 'Bright Data → Web Unlocker → скопируйте API Key и вставьте сюда' },
    ],
    models: [],
  },
  {
    id: 'browser_session', name: 'Браузерная сессия (без ключей API)', icon: '🍪',
    color: 'from-amber-500 to-orange-500',
    description: 'Публикация через обычный веб-интерфейс площадки, когда приложение Meta ' +
                 'создать не получается. Работает на сервере — компьютер держать включённым не нужно.',
    fields: [
      { key: 'nexus_browser_storage_state', label: 'Cookies площадки (вставьте как есть)', placeholder: '[{"domain":".instagram.com","name":"sessionid",...}]', secret: true },
      { key: 'nexus_publish_mode', label: 'Режим публикации: auto / browser / api', placeholder: 'browser', secret: false },
    ],
    steps: [
      { text: 'Войдите в Instagram в обычном браузере на своём компьютере' },
      { text: 'Поставьте расширение', link: 'https://cookie-editor.com', linkText: 'Cookie-Editor' },
      { text: 'На вкладке с Instagram: расширение → Export → Export as JSON (скопируется в буфер)' },
      { text: 'Вставьте скопированное в поле выше и сохраните — формат приводится автоматически' },
      { text: 'Режим публикации поставьте browser, если ключей Meta нет совсем' },
      { text: 'Проверка: страница «Площадки» → «Проверить сессию». Cookies живут неделями, ' +
              'при истечении система скажет об этом прямо, а не «не смог опубликовать»' },
    ],
    models: [],
  },
  {
    id: 'instagram', name: 'Instagram', icon: '📸', color: 'from-pink-500 to-purple-500',
    description: 'Прямое подключение через Instagram Login. Страница Facebook не нужна — достаточно токена IGAA…',
    fields: [
      { key: 'instagram_access_token', label: 'Instagram User Access Token (IGAA…)', placeholder: 'IGAAxxxxxxxx...', secret: true },
      { key: 'instagram_account_id', label: 'Account ID (заполнится сам)', placeholder: '17841400...', secret: false },
      { key: 'instagram_app_secret', label: 'Instagram app secret (только для вебхуков)', placeholder: 'a1b2c3...', secret: true },
      { key: 'instagram_verify_token', label: 'Токен подтверждения вебхука (придумайте сами)', placeholder: 'nexus-webhook-2026', secret: true },
      { key: 'nexus_public_url', label: 'Публичный адрес сервиса', placeholder: 'https://nexus-ai.onrender.com', secret: false },
    ],
    steps: [
      { text: 'Приложение Meta → Instagram → «API setup with Instagram login» → шаг 2 «Generate token» → кнопкой Copy скопируйте токен IGAA…' },
      { text: 'Вставьте токен в поле выше и сохраните — Account ID, тип токена и продление настроятся сами' },
      { text: 'Проверьте кнопкой «Проверить» — должно ответить «Аккаунт: ваш_логин ✓»' },
      { text: 'Комментарии в реальном времени (необязательно): там же Instagram app secret → поле выше' },
      { text: 'Webhooks → Callback URL: <ваш адрес>/api/social/webhook/instagram, Verify token — тот, что вписали выше' },
    ],
    models: [],
  },
  {
    id: 'facebook_optional', name: 'Facebook (необязательно)', icon: '🔗', color: 'from-blue-600 to-indigo-700',
    description: 'Нужен только для анализа чужих аккаунтов через Business Discovery. Для публикации и комментариев не требуется',
    fields: [
      { key: 'facebook_app_id', label: 'App ID приложения Meta', placeholder: '1234567890', secret: false },
      { key: 'facebook_app_secret', label: 'App Secret', placeholder: 'a1b2c3...', secret: true },
    ],
    steps: [
      { text: 'Заполнять не нужно, если работаете по токену IGAA… — конкуренты разбираются бесплатным путём через браузер' },
      { text: 'Business Discovery работает только через Страницу Facebook — это ограничение Meta, не наше' },
    ],
    models: [],
  },
  {
    id: 'perplexity', name: 'Perplexity AI', icon: '🔍', color: 'from-teal-500 to-cyan-500',
    description: 'Поиск актуальных трендов и вирусных тем в реальном времени',
    fields: [{ key: 'perplexity_api_key', label: 'API Key', placeholder: 'pplx-...', secret: true }],
    steps: [
      { text: 'Откройте', link: 'https://www.perplexity.ai/settings/api', linkText: 'perplexity.ai/settings/api' },
      { text: 'Нажмите Generate → скопируйте ключ (начинается с pplx-)' },
      { text: 'Бесплатно: 5 запросов/мин. Pro: неограниченно' },
      { text: 'Используется агентами NicheAnalyst и ViralHunter в Premium режиме' },
    ],
    models: ['sonar', 'sonar-pro', 'sonar-reasoning-pro'],
  },
  {
    id: 'nvidia', name: 'NVIDIA NIM', icon: '🟩', color: 'from-green-500 to-emerald-600',
    description: 'Бесплатные открытые модели (Llama, Nemotron, Qwen, DeepSeek-R1) на GPU NVIDIA',
    fields: [{ key: 'nvidia_api_key', label: 'API Key', placeholder: 'nvapi-...', secret: true }],
    steps: [
      { text: 'Откройте', link: 'https://build.nvidia.com/settings/api-keys', linkText: 'build.nvidia.com/settings/api-keys' },
      { text: 'Войдите (нужен только email, карта не требуется) → Generate API Key' },
      { text: 'Скопируйте ключ — он начинается с nvapi- и действует 6 месяцев' },
      { text: 'Бесплатно: 1000 кредитов при регистрации, лимит 40 запросов/мин' },
      { text: 'Дирижёр берёт NVIDIA первым исполнителем, пока квота не кончится' },
    ],
    models: ['nvidia-free (модель подбирается автоматически)'],
  },
  {
    id: 'groq', name: 'Groq', icon: '⚡', color: 'from-orange-500 to-red-500',
    description: 'Самая быстрая бесплатная выдача — Llama 3.3 70B на чипах LPU',
    fields: [{ key: 'groq_api_key', label: 'API Key', placeholder: 'gsk_...', secret: true }],
    steps: [
      { text: 'Откройте', link: 'https://console.groq.com/keys', linkText: 'console.groq.com/keys' },
      { text: 'Войдите через Google/GitHub → Create API Key (карта не нужна)' },
      { text: 'Бесплатно: 30 запросов/мин, 1000 в сутки' },
      { text: 'Лучший выбор, когда важна скорость ответа' },
    ],
    models: ['groq-free (модель подбирается автоматически)'],
  },
  {
    id: 'cerebras', name: 'Cerebras', icon: '🧩', color: 'from-amber-500 to-orange-600',
    description: 'Около 1 млн токенов в сутки бесплатно — для пакетной генерации',
    fields: [{ key: 'cerebras_api_key', label: 'API Key', placeholder: 'csk-...', secret: true }],
    steps: [
      { text: 'Откройте', link: 'https://cloud.cerebras.ai', linkText: 'cloud.cerebras.ai' },
      { text: 'Зарегистрируйтесь → API Keys → Create Key' },
      { text: 'Бесплатно: ~1 млн токенов в сутки' },
      { text: 'Берите, когда нужно много текста за раз (месячный контент-план)' },
    ],
    models: ['cerebras-free (модель подбирается автоматически)'],
  },
  {
    id: 'openrouter', name: 'OpenRouter', icon: '🔀', color: 'from-sky-500 to-indigo-600',
    description: 'Около 30 бесплатных моделей разных вендоров через один API',
    fields: [{ key: 'openrouter_api_key', label: 'API Key', placeholder: 'sk-or-v1-...', secret: true }],
    steps: [
      { text: 'Откройте', link: 'https://openrouter.ai/keys', linkText: 'openrouter.ai/keys' },
      { text: 'Войдите → Create Key' },
      { text: 'Бесплатно: 20 запросов/мин, 50 в сутки на моделях с меткой :free' },
      { text: 'Система берёт ТОЛЬКО модели с суффиксом :free — платные не трогает' },
    ],
    models: ['openrouter-free (только модели :free)'],
  },
  {
    id: 'mistral', name: 'Mistral', icon: '🌬️', color: 'from-yellow-500 to-orange-500',
    description: 'Бесплатный тариф на все модели Mistral, включая крупные',
    fields: [{ key: 'mistral_api_key', label: 'API Key', placeholder: '...', secret: true }],
    steps: [
      { text: 'Откройте', link: 'https://console.mistral.ai/api-keys', linkText: 'console.mistral.ai/api-keys' },
      { text: 'Зарегистрируйтесь → Create new key' },
      { text: 'Бесплатно: все модели, но всего ~2 запроса/мин' },
      { text: 'Медленный лимит — держите как резерв, не как основной' },
    ],
    models: ['mistral-free (модель подбирается автоматически)'],
  },
  {
    id: 'github', name: 'GitHub Models', icon: '🐙', color: 'from-slate-600 to-gray-800',
    description: '100+ моделей (GPT-4o, Llama, Phi) по обычному токену GitHub',
    fields: [{ key: 'github_models_token', label: 'Personal Access Token', placeholder: 'ghp_...', secret: true }],
    steps: [
      { text: 'Откройте', link: 'https://github.com/settings/tokens', linkText: 'github.com/settings/tokens' },
      { text: 'Generate new token (classic) → отметьте права models:read' },
      { text: 'Скопируйте токен (начинается с ghp_)' },
      { text: 'Бесплатно в рамках суточных лимитов GitHub' },
    ],
    models: ['github-free (модель подбирается автоматически)'],
  },
  {
    id: 'deepseek', name: 'DeepSeek AI', icon: '🧠', color: 'from-indigo-500 to-blue-600',
    description: 'Дешёвый и мощный AI — используется в Economy режиме вместо GPT-4o',
    fields: [{ key: 'deepseek_api_key', label: 'API Key', placeholder: 'sk-...', secret: true }],
    steps: [
      { text: 'Откройте', link: 'https://platform.deepseek.com/api_keys', linkText: 'platform.deepseek.com/api_keys' },
      { text: 'Войдите или создайте аккаунт (есть бесплатные кредиты)' },
      { text: 'Нажмите Create new API key → скопируйте ключ' },
      { text: 'В Economy режиме (Dashboard → Профиль) агенты используют DeepSeek вместо Claude/GPT-4o' },
      { text: 'DeepSeek Chat: дешёвый ($0.14/1M токенов). Reasoner R1: глубокий анализ ($0.55/1M)' },
    ],
    models: ['deepseek-chat', 'deepseek-reasoner'],
  },
  {
    id: 'tiktok', name: 'TikTok', icon: '🎵', color: 'from-rose-500 to-pink-500',
    description: 'Публикация коротких видео и фото-постов в TikTok',
    fields: [{ key: 'tiktok_access_token', label: 'Access Token', placeholder: 'act...', secret: true }],
    steps: [
      { text: 'Зарегистрируйтесь как разработчик:', link: 'https://developers.tiktok.com', linkText: 'developers.tiktok.com' },
      { text: 'Создайте приложение → запросите доступ к Content Posting API' },
      { text: 'Выдайте scope: video.publish, video.upload' },
      { text: 'Пройдите OAuth авторизацию → получите Access Token' },
      { text: 'Токен живёт 24 часа — нужно обновлять через Refresh Token' },
    ],
    models: [],
  },
  {
    id: 'google_drive', name: 'Google Drive', icon: '📂', color: 'from-yellow-500 to-orange-500',
    description: 'Постоянная память — кэш анализов ниш, экономит 90% токенов при повторных запусках',
    fields: [
      { key: 'google_service_account_json', label: 'Service Account JSON', placeholder: '{"type":"service_account",...}', secret: true },
    ],
    steps: [
      { text: 'Откройте', link: 'https://console.cloud.google.com', linkText: 'console.cloud.google.com' },
      { text: 'Создайте проект → включите Google Drive API' },
      { text: 'IAM и администрирование → Сервисные аккаунты → Создать' },
      { text: 'Скачайте JSON ключ сервисного аккаунта' },
      { text: 'Создайте папку на Google Диске, откройте права для email сервисного аккаунта' },
      { text: 'Вставьте полное содержимое JSON файла в поле выше' },
      { text: 'ID папки: из URL диска — .../folders/FOLDER_ID — скопируйте в профиль Dashboard' },
    ],
    models: [],
  },
]

function FieldInput({ field, value, onChange, onDelete, testResult }) {
  const [show, setShow] = React.useState(false)
  // Пустое поле означает «не трогали» — стереть ключ можно только явной кнопкой.
  const saved = Boolean(value)
  return (
    <div className="space-y-1">
      <label className="text-xs text-nexus-muted">{field.label}</label>
      <div className="relative">
        <input
          type={field.secret && !show ? 'password' : 'text'}
          value={value || ''}
          onChange={e => onChange(field.key, e.target.value)}
          placeholder={field.placeholder}
          className="w-full bg-nexus-card border border-nexus-border rounded-lg px-3 py-2 pr-10 text-xs text-nexus-text placeholder-nexus-muted focus:border-purple-500 outline-none font-mono"
        />
        {field.secret && (
          <button type="button" onClick={() => setShow(s => !s)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-nexus-muted hover:text-nexus-text">
            {show ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
          </button>
        )}
      </div>
      {saved && (
        <button type="button" onClick={() => onDelete(field)}
          className="flex items-center gap-1 text-xs text-nexus-muted hover:text-red-400 transition">
          <Trash2 className="w-3 h-3" /> Удалить ключ
        </button>
      )}
      {testResult && (
        <div className={'flex items-center gap-1 text-xs ' + (testResult.ok ? 'text-green-400' : 'text-red-400')}>
          {testResult.ok ? <CheckCircle className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
          {testResult.message}
        </div>
      )}
    </div>
  )
}

function ProviderCard({ provider, values, onChange, onDelete, testResults }) {
  const [open, setOpen] = React.useState(false)
  const hasKeys = provider.fields.some(f => values[f.key])
  const tested = provider.fields.filter(f => testResults[f.key])
  const allOk = hasKeys && tested.length > 0 && tested.every(f => testResults[f.key]?.ok)
  const anyFail = provider.fields.some(f => testResults[f.key] && !testResults[f.key]?.ok)
  return (
    <div className={'glass rounded-xl overflow-hidden border ' + (anyFail ? 'border-red-500/30' : allOk ? 'border-green-500/30' : 'border-nexus-border')}>
      <button onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-4 p-4 hover:bg-nexus-card/50 transition text-left">
        <div className={'w-10 h-10 rounded-lg bg-gradient-to-br ' + provider.color + ' flex items-center justify-center text-lg flex-shrink-0'}>
          {provider.icon}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-nexus-text">{provider.name}</span>
            {allOk && <span className="text-xs text-green-400 flex items-center gap-1"><CheckCircle className="w-3 h-3" /> Подключён</span>}
            {anyFail && <span className="text-xs text-red-400 flex items-center gap-1"><XCircle className="w-3 h-3" /> Ошибка</span>}
            {hasKeys && !allOk && !anyFail && <span className="text-xs text-yellow-400">● Сохранён</span>}
          </div>
          <p className="text-xs text-nexus-muted">{provider.description}</p>
        </div>
        {provider.models.length > 0 && (
          <div className="hidden lg:flex gap-1">
            {provider.models.map(m => <span key={m} className="text-xs bg-nexus-card border border-nexus-border rounded px-1.5 py-0.5 text-nexus-muted font-mono">{m}</span>)}
          </div>
        )}
        {open ? <ChevronUp className="w-4 h-4 text-nexus-muted flex-shrink-0" /> : <ChevronDown className="w-4 h-4 text-nexus-muted flex-shrink-0" />}
      </button>
      {open && (
        <div className="border-t border-nexus-border grid md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-nexus-border">
          <div className="p-4 space-y-4">
            <h4 className="text-xs font-semibold text-purple-300 uppercase tracking-wider">API Ключи</h4>
            {provider.fields.map(field => (
              <FieldInput key={field.key} field={field} value={values[field.key]} onChange={onChange}
                onDelete={onDelete} testResult={testResults[field.key]} />
            ))}
          </div>
          <div className="p-4">
            <h4 className="text-xs font-semibold text-cyan-300 uppercase tracking-wider mb-3">Как подключить</h4>
            <ol className="space-y-2.5">
              {provider.steps.map((step, i) => (
                <li key={i} className="flex gap-2 text-xs text-nexus-muted">
                  <span className="text-purple-400 font-bold flex-shrink-0">{i + 1}.</span>
                  <span>
                    {step.text}{' '}
                    {step.link && (
                      <a href={step.link} target="_blank" rel="noopener noreferrer"
                        className="text-cyan-400 hover:text-cyan-300 inline-flex items-center gap-0.5">
                        {step.linkText}<ExternalLink className="w-3 h-3" />
                      </a>
                    )}
                  </span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      )}
    </div>
  )
}

export default function Connections() {
  const [values, setValues] = useState({})
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResults, setTestResults] = useState({})
  const [saved, setSaved] = useState(false)
  useEffect(() => { connectionsApi.list().then(r => setValues(r.data || {})) }, [])
  const onChange = (key, val) => setValues(p => ({ ...p, [key]: val }))
  const save = async () => {
    setSaving(true)
    await connectionsApi.save(values)
    setSaved(true); setTimeout(() => setSaved(false), 2000); setSaving(false)
  }
  // Проверка сперва сохраняет. Раньше зелёная галочка означала только «Meta
  // приняла ключ» — вписанное значение при этом нигде не оставалось, и после
  // перезагрузки страницы пропадало. Выглядело как «подключено», работало как
  // «не подключено».
  const testAll = async () => {
    setTesting(true)
    try {
      await connectionsApi.save(values)
      setSaved(true); setTimeout(() => setSaved(false), 2000)
      const r = await connectionsApi.test(values)
      setTestResults(r.data || {})
    } catch { setTestResults({}) }
    setTesting(false)
  }
  const removeKey = async (field) => {
    if (!window.confirm(`Удалить ${field.label}? Ключ будет стёрт с сервера.`)) return
    const { data } = await connectionsApi.remove(field.key)
    if (data?.ok) {
      setValues(p => { const next = { ...p }; delete next[field.key]; return next })
      setTestResults(p => { const next = { ...p }; delete next[field.key]; return next })
      if (data.note) window.alert(data.note)
    }
  }
  const connectedCount = PROVIDERS.filter(p => p.fields.some(f => values[f.key])).length
  return (
    <div className="max-w-4xl mx-auto">
      <div className="mb-6 flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><Plug className="text-purple-400" /> Подключения</h1>
          <p className="text-nexus-muted text-sm mt-1">Подключено: <span className="text-purple-300 font-semibold">{connectedCount} / {PROVIDERS.length}</span> провайдеров</p>
        </div>
        <div className="flex gap-2">
          <button onClick={testAll} disabled={testing}
            className="px-4 py-2 rounded-lg border border-nexus-border text-nexus-muted text-sm hover:text-nexus-text transition flex items-center gap-2">
            {testing ? <Loader className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />} Проверить все
          </button>
          <button onClick={save} disabled={saving}
            className="px-4 py-2 rounded-lg bg-purple-600 text-white text-sm hover:bg-purple-500 transition flex items-center gap-2 disabled:opacity-50">
            {saving ? <Loader className="w-4 h-4 animate-spin" /> : saved ? <CheckCircle className="w-4 h-4" /> : <Save className="w-4 h-4" />}
            {saved ? 'Сохранено!' : 'Сохранить'}
          </button>
        </div>
      </div>
      {(() => {
        const ESSENTIAL = ['claude', 'heygen', 'higgsfield', 'telegram', 'desktop_agent']
        const ess = PROVIDERS.filter(p => ESSENTIAL.includes(p.id))
          .sort((a, b) => ESSENTIAL.indexOf(a.id) - ESSENTIAL.indexOf(b.id))
        const opt = PROVIDERS.filter(p => !ESSENTIAL.includes(p.id))
        return (
          <>
            <div className="text-xs font-semibold text-violet-300 uppercase tracking-wider mb-2">
              ⭐ Необходимое для Reels-автоматизации
            </div>
            <div className="space-y-3">
              {ess.map(p => <ProviderCard key={p.id} provider={p} values={values} onChange={onChange} onDelete={removeKey} testResults={testResults} />)}
            </div>
            <div className="text-xs font-semibold text-[#5a5a7a] uppercase tracking-wider mt-6 mb-2">
              Опционально — можно подключить позже (есть бесплатные)
            </div>
            <div className="space-y-3 opacity-80">
              {opt.map(p => <ProviderCard key={p.id} provider={p} values={values} onChange={onChange} onDelete={removeKey} testResults={testResults} />)}
            </div>
          </>
        )
      })()}
      <div className="mt-4 glass rounded-xl p-4">
        <p className="text-xs text-nexus-muted">
          🔒 <span className="text-nexus-text">Безопасность:</span> ключи хранятся в БД сервера. В браузер возвращается только маска (первые и последние 4 символа). Сырые ключи никогда не покидают сервер.
        </p>
      </div>
    </div>
  )
}