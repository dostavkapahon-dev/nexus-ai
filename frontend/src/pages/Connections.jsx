import React, { useState, useEffect } from 'react'
import { Plug, Save, CheckCircle, XCircle, Loader, Eye, EyeOff, ExternalLink, ChevronDown, ChevronUp } from 'lucide-react'
import { connections as connectionsApi } from '../lib/api'

const PROVIDERS = [
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
    models: ['gemini-1.5-flash', 'gemini-1.5-pro'],
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
    id: 'instagram', name: 'Instagram Business', icon: '📸', color: 'from-pink-500 to-purple-500',
    description: 'Публикация фото-постов в Instagram Business аккаунт',
    fields: [
      { key: 'instagram_access_token', label: 'Page Access Token', placeholder: 'EAAo3ELgu...', secret: true },
      { key: 'instagram_account_id', label: 'Instagram Account ID', placeholder: '17841400...', secret: false },
    ],
    steps: [
      { text: 'Создайте Facebook Page и подключите Instagram Professional к ней' },
      { text: 'Откройте', link: 'https://developers.facebook.com/tools/explorer', linkText: 'Graph API Explorer' },
      { text: 'Выберите приложение → User or Page → выберите вашу Facebook Page' },
      { text: 'Выдайте права: pages_manage_posts, instagram_basic, instagram_content_publish' },
      { text: 'Нажмите Generate Access Token и скопируйте токен' },
      { text: 'Account ID: выполните GET /me?fields=instagram_business_account → скопируйте id' },
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
  {
    id: 'heygen', name: 'HeyGen', icon: '🎬', color: 'from-violet-500 to-fuchsia-500',
    description: 'AI-аватары: превращает текст в видео с говорящим аватаром',
    fields: [{ key: 'heygen_api_key', label: 'API Key', placeholder: 'OTk...==', secret: true }],
    steps: [
      { text: 'Откройте', link: 'https://app.heygen.com/settings/api', linkText: 'app.heygen.com → Settings → API' },
      { text: 'Скопируйте API Key и вставьте выше' },
      { text: 'Аватар и голос по умолчанию настраиваются через env: HEYGEN_AVATAR_ID, HEYGEN_VOICE_ID' },
    ],
    models: [],
  },
  {
    id: 'higgsfield', name: 'Higgsfield', icon: '🌀', color: 'from-amber-500 to-orange-600',
    description: 'AI-генерация видео из текста и картинки (text/image-to-video)',
    fields: [{ key: 'higgsfield_api_key', label: 'API Key', placeholder: 'hf_...', secret: true }],
    steps: [
      { text: 'Откройте', link: 'https://higgsfield.ai', linkText: 'higgsfield.ai' },
      { text: 'В настройках аккаунта создайте API ключ' },
      { text: 'Вставьте ключ выше. Базовый URL API при необходимости меняется через env HIGGSFIELD_API_BASE' },
    ],
    models: [],
  },
]

function FieldInput({ field, value, onChange, testResult }) {
  const [show, setShow] = React.useState(false)
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
      {testResult && (
        <div className={'flex items-center gap-1 text-xs ' + (testResult.ok ? 'text-green-400' : 'text-red-400')}>
          {testResult.ok ? <CheckCircle className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
          {testResult.message}
        </div>
      )}
    </div>
  )
}

function ProviderCard({ provider, values, onChange, testResults }) {
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
              <FieldInput key={field.key} field={field} value={values[field.key]} onChange={onChange} testResult={testResults[field.key]} />
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
  const testAll = async () => {
    setTesting(true)
    try { const r = await connectionsApi.test(values); setTestResults(r.data || {}) }
    catch { setTestResults({}) }
    setTesting(false)
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
      <div className="space-y-3">
        {PROVIDERS.map(provider => <ProviderCard key={provider.id} provider={provider} values={values} onChange={onChange} testResults={testResults} />)}
      </div>
      <div className="mt-4 glass rounded-xl p-4">
        <p className="text-xs text-nexus-muted">
          🔒 <span className="text-nexus-text">Безопасность:</span> ключи хранятся в БД сервера. В браузер возвращается только маска (первые и последние 4 символа). Сырые ключи никогда не покидают сервер.
        </p>
      </div>
    </div>
  )
}