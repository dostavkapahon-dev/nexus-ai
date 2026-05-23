import React, { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import {
  Zap, Play, Pause, Trash2, Cpu, CheckCircle, AlertCircle,
  Loader, RefreshCw, Database, Cloud, CloudOff, ExternalLink, Settings2
} from 'lucide-react'
import { niches as nichesApi, profile as profileApi, connections as connectionsApi, infrastructure } from '../lib/api'

const AI_PROVIDERS = [
  { id: 'claude',    label: 'Claude',    sub: 'Anthropic',  icon: '🟠', key: 'anthropic_api_key',  color: '#e97316' },
  { id: 'gpt4o',    label: 'GPT-4o',    sub: 'OpenAI',     icon: '⚡',  key: 'openai_api_key',     color: '#22c55e' },
  { id: 'deepseek', label: 'DeepSeek',  sub: 'Экономный',  icon: '🧠', key: 'deepseek_api_key',   color: '#6366f1' },
  { id: 'gemini',   label: 'Gemini',    sub: 'Google',     icon: '💎', key: 'gemini_api_key',     color: '#3b82f6' },
  { id: 'sonar',    label: 'Perplexity',sub: 'Поиск',      icon: '🔍', key: 'perplexity_api_key', color: '#14b8a6' },
]

const AGENT_LABELS = {
  niche_analyst: 'NicheAnalyst', viral_hunter: 'ViralHunter',
  strategist: 'Strategist', copywriter: 'Copywriter',
  reviewer: 'Reviewer', visual_creator: 'VisualCreator',
  voice_adapter: 'VoiceAdapter', adapter: 'Adapter'
}

// ─── AI Provider Selector ────────────────────────────────────────────────────
function AISelector({ activeAI, onSelect, connectedKeys }) {
  return (
    <div className="card p-5 mb-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Cpu className="w-4 h-4 text-violet-400" />
          <span className="font-semibold text-sm">Активный AI</span>
          <span className="text-[11px] text-[#5a5a7a] ml-1">— выбери основную нейросеть для всех агентов</span>
        </div>
        <Link to="/connections" className="text-xs text-[#5a5a7a] hover:text-violet-400 flex items-center gap-1 transition">
          <Settings2 className="w-3 h-3" /> Ключи API
        </Link>
      </div>
      <div className="grid grid-cols-5 gap-2">
        {AI_PROVIDERS.map(p => {
          const hasKey = connectedKeys[p.key]
          const isActive = activeAI === p.id
          return (
            <button key={p.id} onClick={() => onSelect(p.id)}
              className={`ai-card relative flex flex-col items-center gap-2 py-3 text-center ${isActive ? 'active' : ''}`}
              style={isActive ? { borderColor: p.color + '66', background: p.color + '15' } : {}}>
              <div className="text-2xl">{p.icon}</div>
              <div>
                <div className="text-xs font-semibold text-[#e8e8f5]">{p.label}</div>
                <div className="text-[10px] text-[#5a5a7a]">{p.sub}</div>
              </div>
              <div className={`absolute top-2 right-2 w-1.5 h-1.5 rounded-full ${hasKey ? 'bg-green-400' : 'bg-[#3a3a55]'}`} />
              {isActive && (
                <div className="absolute bottom-2 left-1/2 -translate-x-1/2 text-[9px] px-1.5 py-0.5 rounded-full"
                  style={{ background: p.color + '30', color: p.color }}>активен</div>
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}

// ─── Google Drive Connect ────────────────────────────────────────────────────
function GoogleDriveConnect({ profile, onSave, googleClientId }) {
  const [connecting, setConnecting] = useState(false)
  const [status, setStatus] = useState(null)

  const connected = Boolean(profile.google_drive_access_token)

  const connect = () => {
    if (!googleClientId) {
      setStatus({ ok: false, msg: 'Добавьте GOOGLE_CLIENT_ID в Render → Environment' })
      return
    }
    setConnecting(true)
    const client = window.google?.accounts?.oauth2?.initTokenClient({
      client_id: googleClientId,
      scope: 'https://www.googleapis.com/auth/drive.file',
      callback: async (resp) => {
        if (resp.error) {
          setStatus({ ok: false, msg: 'Отмена или ошибка: ' + resp.error })
          setConnecting(false)
          return
        }
        try {
          await profileApi.save({ ...profile, google_drive_access_token: resp.access_token })
          onSave({ ...profile, google_drive_access_token: resp.access_token })
          setStatus({ ok: true, msg: 'Google Drive подключён! Кэш анализов включён.' })
        } catch { setStatus({ ok: false, msg: 'Ошибка сохранения токена' }) }
        setConnecting(false)
      }
    })
    client?.requestAccessToken()
  }

  const disconnect = async () => {
    await profileApi.save({ ...profile, google_drive_access_token: '' })
    onSave({ ...profile, google_drive_access_token: '' })
    setStatus(null)
  }

  return (
    <div className="flex items-center justify-between px-4 py-3 rounded-xl border border-[#1c1c30] bg-[#0d0d1a]">
      <div className="flex items-center gap-3">
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-base ${connected ? 'bg-green-500/15' : 'bg-[#111120]'}`}>
          {connected ? '📂' : <CloudOff className="w-4 h-4 text-[#5a5a7a]" />}
        </div>
        <div>
          <div className="text-sm font-medium text-[#e8e8f5]">Google Drive</div>
          <div className="text-xs text-[#5a5a7a]">
            {connected ? 'Кэш анализов включён — экономия 90% токенов' : 'Подключи для кэширования анализов ниш'}
          </div>
        </div>
      </div>
      <div className="flex items-center gap-2">
        {status && (
          <span className={`text-xs ${status.ok ? 'text-green-400' : 'text-red-400'}`}>{status.msg}</span>
        )}
        {connected ? (
          <button onClick={disconnect}
            className="px-3 py-1.5 text-xs rounded-lg border border-[#1c1c30] text-[#5a5a7a] hover:text-red-400 hover:border-red-500/30 transition">
            Отключить
          </button>
        ) : (
          <button onClick={connect} disabled={connecting}
            className="px-4 py-1.5 text-xs rounded-lg bg-gradient-to-r from-[#4285f4] to-[#34a853] text-white font-medium hover:opacity-90 transition flex items-center gap-1.5 disabled:opacity-50">
            {connecting ? <Loader className="w-3 h-3 animate-spin" /> : <Cloud className="w-3 h-3" />}
            Подключить Google
          </button>
        )}
      </div>
    </div>
  )
}

// ─── Niche Card ──────────────────────────────────────────────────────────────
function NicheCard({ niche, onDelete, onToggle, onRerun }) {
  const [agents, setAgents] = useState({})
  const wsRef = useRef(null)

  useEffect(() => {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/${niche.id}`)
    wsRef.current = ws
    ws.onmessage = (e) => {
      const d = JSON.parse(e.data)
      if (d.event === 'agent_start')      setAgents(p => ({ ...p, [d.agent]: 'running' }))
      else if (d.event === 'agent_done')  setAgents(p => ({ ...p, [d.agent]: 'done' }))
      else if (d.event === 'cache_hit')   setAgents(p => ({ ...p, [d.agent]: 'cached' }))
      else if (d.event === 'pipeline_complete') setAgents({})
    }
    return () => ws.close()
  }, [niche.id])

  const running = Object.entries(agents).filter(([, s]) => s === 'running')
  const cached  = Object.entries(agents).filter(([, s]) => s === 'cached')
  const isActive = niche.status === 'active'

  return (
    <div className={`card p-5 flex flex-col gap-4 transition-all ${isActive ? 'glow-purple' : ''}`}>
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-3">
          <div className={`w-2.5 h-2.5 rounded-full mt-1.5 flex-shrink-0 ${isActive ? 'bg-green-400 pulse-dot' : 'bg-[#3a3a55]'}`} />
          <div>
            <h3 className="font-semibold text-[#e8e8f5]">{niche.name}</h3>
            <p className="text-xs text-[#5a5a7a] mt-0.5">{niche.city} · {niche.goal}</p>
          </div>
        </div>
        <div className="flex gap-1">
          <button onClick={() => onToggle(niche)}
            className={`p-1.5 rounded-lg transition ${isActive ? 'text-yellow-400 hover:bg-yellow-500/10' : 'text-green-400 hover:bg-green-500/10'}`}>
            {isActive ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
          </button>
          <button onClick={() => onRerun(niche.id)}
            className="p-1.5 rounded-lg transition text-[#5a5a7a] hover:text-cyan-400 hover:bg-cyan-500/10">
            <RefreshCw className="w-4 h-4" />
          </button>
          <button onClick={() => onDelete(niche.id)}
            className="p-1.5 rounded-lg transition text-[#5a5a7a] hover:text-red-400 hover:bg-red-500/10">
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {(niche.platforms || []).map(p => (
          <span key={p} className="px-2 py-0.5 text-[11px] rounded-full bg-violet-900/30 text-violet-300 border border-violet-500/25">{p}</span>
        ))}
      </div>

      {cached.length > 0 && (
        <div className="flex items-center gap-2 text-xs text-amber-400 bg-amber-500/8 rounded-lg px-3 py-1.5">
          <Database className="w-3 h-3" /> Загружено из кэша — токены сэкономлены
        </div>
      )}

      {running.length > 0 && (
        <div className="space-y-1.5">
          {running.map(([agent]) => (
            <div key={agent} className="flex items-center gap-2 text-xs text-cyan-400 bg-cyan-500/8 rounded-lg px-3 py-1.5">
              <Cpu className="w-3 h-3 animate-spin" />
              {AGENT_LABELS[agent] || agent} работает...
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="bg-[#0d0d1a] rounded-lg px-3 py-2">
          <div className="text-[#5a5a7a]">Постов/день</div>
          <div className="font-semibold text-[#e8e8f5] mt-0.5">{niche.posts_per_day}</div>
        </div>
        <div className="bg-[#0d0d1a] rounded-lg px-3 py-2">
          <div className="text-[#5a5a7a]">Бюджет</div>
          <div className="font-semibold text-[#e8e8f5] mt-0.5">${niche.budget_usd}/мес</div>
        </div>
      </div>

      <div className="flex gap-2 pt-1">
        <Link to={`/queue?niche_id=${niche.id}`}
          className="flex-1 text-center text-xs py-2 rounded-lg bg-violet-600/15 text-violet-300 hover:bg-violet-600/25 transition border border-violet-500/20">
          Очередь
        </Link>
        <Link to={`/analytics?niche_id=${niche.id}`}
          className="flex-1 text-center text-xs py-2 rounded-lg bg-cyan-600/15 text-cyan-300 hover:bg-cyan-600/25 transition border border-cyan-500/20">
          Аналитика
        </Link>
      </div>
    </div>
  )
}

// ─── Dashboard ───────────────────────────────────────────────────────────────
export default function Dashboard() {
  const [niches, setNiches] = useState([])
  const [loading, setLoading] = useState(true)
  const [profile, setProfile] = useState({
    product_description: '', brand_style: '', strategy_focus: 'subscribers',
    strategy_duration: 30, ai_mode: 'economy', google_drive_folder_id: '',
    google_drive_access_token: '', active_ai: 'claude'
  })
  const [connectedKeys, setConnectedKeys] = useState({})
  const [googleClientId, setGoogleClientId] = useState('')
  const [infraResults, setInfraResults] = useState(null)
  const [infraLoading, setInfraLoading] = useState(false)

  useEffect(() => {
    Promise.all([
      nichesApi.list(),
      profileApi.get(),
      connectionsApi.list(),
    ]).then(([nr, pr, cr]) => {
      setNiches(nr.data)
      setProfile(pr.data)
      const keys = {}
      AI_PROVIDERS.forEach(p => { keys[p.key] = Boolean(cr.data[p.key]) })
      setConnectedKeys(keys)
    }).finally(() => setLoading(false))

    // Load Google client ID for Drive OAuth
    import('../lib/api').then(({ auth }) => {
      auth.googleClientId().then(r => {
        if (r.data.enabled) {
          setGoogleClientId(r.data.client_id)
          if (!document.getElementById('gsi-script')) {
            const s = document.createElement('script')
            s.id = 'gsi-script'
            s.src = 'https://accounts.google.com/gsi/client'
            s.async = true
            document.head.appendChild(s)
          }
        }
      }).catch(() => {})
    })
  }, [])

  const selectAI = async (aiId) => {
    const updated = { ...profile, active_ai: aiId }
    setProfile(updated)
    await profileApi.save(updated)
  }

  const handleDelete = async (id) => {
    if (!confirm('Удалить нишу?')) return
    await nichesApi.delete(id)
    setNiches(p => p.filter(n => n.id !== id))
  }

  const handleToggle = async (niche) => {
    const s = niche.status === 'active' ? 'paused' : 'active'
    await nichesApi.update(niche.id, { status: s })
    setNiches(p => p.map(n => n.id === niche.id ? { ...n, status: s } : n))
  }

  const handleRerun = async (id) => {
    await nichesApi.generatePlan(id)
  }

  const checkInfra = async () => {
    setInfraLoading(true)
    try { const r = await infrastructure.check(); setInfraResults(r.data) }
    catch { setInfraResults(null) }
    setInfraLoading(false)
  }

  const activeNiches  = niches.filter(n => n.status === 'active').length
  const pausedNiches  = niches.filter(n => n.status !== 'active').length

  return (
    <div className="max-w-6xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold gradient-text flex items-center gap-2">
            <Zap className="w-5 h-5 text-violet-400" /> NEXUS AI
          </h1>
          <p className="text-xs text-[#5a5a7a] mt-1">Автономная публикация контента 24/7</p>
        </div>
        <Link to="/new" className="btn-primary flex items-center gap-1.5">
          + Новая ниша
        </Link>
      </div>

      {/* AI Selector */}
      <AISelector activeAI={profile.active_ai} onSelect={selectAI} connectedKeys={connectedKeys} />

      {/* Google Drive Connect */}
      <div className="mb-5">
        <GoogleDriveConnect profile={profile} onSave={setProfile} googleClientId={googleClientId} />
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-3 mb-5">
        {[
          { label: 'Активных ниш',  value: activeNiches,  color: '#22c55e' },
          { label: 'На паузе',       value: pausedNiches,  color: '#5a5a7a' },
          { label: 'Всего ниш',      value: niches.length, color: '#a78bfa' },
          { label: 'AI агентов',     value: '8',           color: '#22d3ee' },
        ].map(({ label, value, color }) => (
          <div key={label} className="card px-4 py-3">
            <div className="text-[11px] text-[#5a5a7a] mb-1">{label}</div>
            <div className="text-2xl font-bold" style={{ color }}>{value}</div>
          </div>
        ))}
      </div>

      {/* Infrastructure check */}
      <div className="card px-4 py-3 mb-5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="text-sm font-medium text-[#e8e8f5]">Статус подключений</div>
          {infraResults && (
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(infraResults.results || {}).map(([key, val]) => (
                <span key={key} className={`text-[11px] px-2 py-0.5 rounded-full flex items-center gap-1 ${val.ok ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
                  {val.ok ? <CheckCircle className="w-2.5 h-2.5" /> : <AlertCircle className="w-2.5 h-2.5" />}
                  {key.replace(/_api_key|_bot_token|_access_token/g, '').replace(/_/g, ' ')}
                </span>
              ))}
            </div>
          )}
        </div>
        <button onClick={checkInfra} disabled={infraLoading}
          className="text-xs px-3 py-1.5 rounded-lg border border-[#1c1c30] text-[#5a5a7a] hover:text-[#e8e8f5] hover:border-[#4c4c70] transition flex items-center gap-1.5 disabled:opacity-50">
          {infraLoading ? <Loader className="w-3 h-3 animate-spin" /> : <CheckCircle className="w-3 h-3" />}
          Проверить
        </button>
      </div>

      {/* Niches */}
      {loading ? (
        <div className="flex items-center justify-center py-20 text-[#5a5a7a]">
          <Loader className="w-5 h-5 animate-spin mr-2" /> Загрузка...
        </div>
      ) : niches.length === 0 ? (
        <div className="card p-12 text-center">
          <div className="text-4xl mb-3">🚀</div>
          <div className="font-semibold text-[#e8e8f5] mb-2">Нет активных ниш</div>
          <div className="text-sm text-[#5a5a7a] mb-5">Создай первую нишу — NEXUS начнёт генерировать и публиковать контент автоматически</div>
          <Link to="/new" className="btn-primary inline-flex items-center gap-2">
            <Zap className="w-4 h-4" /> Создать нишу
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-4">
          {niches.map(n => (
            <NicheCard key={n.id} niche={n}
              onDelete={handleDelete} onToggle={handleToggle} onRerun={handleRerun} />
          ))}
        </div>
      )}
    </div>
  )
}
