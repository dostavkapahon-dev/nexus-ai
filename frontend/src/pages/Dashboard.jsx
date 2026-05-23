import React, { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { Zap, Play, Pause, Trash2, BarChart, CheckCircle, Cpu, Settings, DollarSign, Loader, Shield, AlertCircle, ToggleLeft, ToggleRight, Save, Database } from 'lucide-react'
import { niches as nichesApi, profile as profileApi, infrastructure } from '../lib/api'

const AGENT_LABELS = {
  niche_analyst: 'NicheAnalyst', viral_hunter: 'ViralHunter',
  strategist: 'Strategist', copywriter: 'Copywriter',
  reviewer: 'Reviewer', visual_creator: 'VisualCreator',
  voice_adapter: 'VoiceAdapter', adapter: 'Adapter'
}

function NicheCard({ niche, onDelete, onToggle }) {
  const [agents, setAgents] = useState({})
  const wsRef = useRef(null)

  useEffect(() => {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/${niche.id}`)
    wsRef.current = ws
    ws.onmessage = (e) => {
      const data = JSON.parse(e.data)
      if (data.event === 'agent_start') setAgents(p => ({ ...p, [data.agent]: 'running' }))
      else if (data.event === 'agent_done') setAgents(p => ({ ...p, [data.agent]: 'done' }))
      else if (data.event === 'cache_hit') setAgents(p => ({ ...p, [data.agent]: 'cached' }))
      else if (data.event === 'pipeline_complete') setAgents({})
    }
    return () => ws.close()
  }, [niche.id])

  const activeAgents = Object.entries(agents).filter(([, s]) => s === 'running')
  const cachedAgents = Object.entries(agents).filter(([, s]) => s === 'cached')

  return (
    <div className="glass rounded-xl p-5 flex flex-col gap-4">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${niche.status === 'active' ? 'bg-green-400' : 'bg-nexus-muted'}`} />
            <h3 className="font-semibold text-nexus-text">{niche.name}</h3>
          </div>
          <p className="text-xs text-nexus-muted mt-1">{niche.city} · {niche.goal}</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => onToggle(niche)} className="p-1.5 rounded-lg hover:bg-nexus-border transition text-nexus-muted hover:text-nexus-text">
            {niche.status === 'active' ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
          </button>
          <button onClick={() => onDelete(niche.id)} className="p-1.5 rounded-lg hover:bg-red-900/30 transition text-nexus-muted hover:text-red-400">
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>
      <div className="flex flex-wrap gap-1">
        {(niche.platforms || []).map(p => (
          <span key={p} className="px-2 py-0.5 text-xs rounded-full bg-purple-900/40 text-purple-300 border border-purple-500/30">{p}</span>
        ))}
      </div>
      {cachedAgents.length > 0 && (
        <div className="flex items-center gap-2 text-xs text-yellow-400">
          <Database className="w-3 h-3" /> Загружен из кэша Google Drive (экономия токенов)
        </div>
      )}
      {activeAgents.length > 0 && (
        <div className="space-y-1">
          {activeAgents.map(([agent]) => (
            <div key={agent} className="flex items-center gap-2 text-xs text-cyan-400">
              <Cpu className="w-3 h-3 animate-spin" />
              <span>{AGENT_LABELS[agent] || agent} работает...</span>
            </div>
          ))}
        </div>
      )}
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="bg-nexus-card rounded-lg p-2">
          <div className="text-nexus-muted">Постов/день</div>
          <div className="font-semibold text-nexus-text">{niche.posts_per_day}</div>
        </div>
        <div className="bg-nexus-card rounded-lg p-2">
          <div className="text-nexus-muted">Бюджет</div>
          <div className="font-semibold text-nexus-text">${niche.budget_usd}/мес</div>
        </div>
      </div>
      <div className="flex gap-2 pt-2 border-t border-nexus-border">
        <Link to={`/queue?niche_id=${niche.id}`} className="flex-1 text-center text-xs py-1.5 rounded-lg bg-purple-600/20 text-purple-300 hover:bg-purple-600/30 transition">
          Очередь
        </Link>
        <button onClick={() => nichesApi.generatePlan(niche.id)} className="flex-1 text-center text-xs py-1.5 rounded-lg bg-cyan-600/20 text-cyan-300 hover:bg-cyan-600/30 transition">
          Перезапустить
        </button>
      </div>
    </div>
  )
}

function ProfilePanel({ profile, onSave }) {
  const [form, setForm] = useState(profile)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [cost, setCost] = useState(null)

  useEffect(() => { setForm(profile) }, [profile])

  const set = (k, v) => setForm(p => ({ ...p, [k]: v }))

  const save = async () => {
    setSaving(true)
    await profileApi.save(form)
    onSave(form)
    setSaved(true); setTimeout(() => setSaved(false), 2000)
    setSaving(false)
  }

  const calcCost = async () => {
    const r = await profileApi.costEstimate({
      ai_mode: form.ai_mode || 'economy',
      posts_per_day: 1,
      days: form.strategy_duration || 30
    })
    setCost(r.data.estimated_cost_usd)
  }

  return (
    <div className="glass rounded-xl p-5 mb-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-semibold text-nexus-text flex items-center gap-2">
          <Settings className="w-4 h-4 text-purple-400" /> Настройки стратегии
        </h2>
        <button onClick={save} disabled={saving}
          className="px-3 py-1.5 text-xs rounded-lg bg-purple-600 text-white hover:bg-purple-500 transition flex items-center gap-1 disabled:opacity-50">
          {saving ? <Loader className="w-3 h-3 animate-spin" /> : saved ? <CheckCircle className="w-3 h-3" /> : <Save className="w-3 h-3" />}
          {saved ? 'Сохранено' : 'Сохранить'}
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-1">
          <label className="text-xs text-nexus-muted">Описание продукта / услуги</label>
          <textarea value={form.product_description || ''} onChange={e => set('product_description', e.target.value)}
            rows={3} placeholder="Что вы продаёте? Чем уникальны? Кому это нужно?"
            className="w-full bg-nexus-card border border-nexus-border rounded-lg px-3 py-2 text-sm text-nexus-text placeholder-nexus-muted focus:border-purple-500 outline-none resize-none" />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-nexus-muted">Стиль подачи / тон бренда</label>
          <textarea value={form.brand_style || ''} onChange={e => set('brand_style', e.target.value)}
            rows={3} placeholder="Экспертный, живой, с юмором? Что нельзя? Фишки подачи..."
            className="w-full bg-nexus-card border border-nexus-border rounded-lg px-3 py-2 text-sm text-nexus-text placeholder-nexus-muted focus:border-purple-500 outline-none resize-none" />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
        <div className="space-y-1">
          <label className="text-xs text-nexus-muted">Фокус стратегии</label>
          <select value={form.strategy_focus || 'subscribers'} onChange={e => set('strategy_focus', e.target.value)}
            className="w-full bg-nexus-card border border-nexus-border rounded-lg px-3 py-2 text-sm text-nexus-text focus:border-purple-500 outline-none">
            <option value="subscribers">📈 Рост подписчиков</option>
            <option value="sales">💰 Прямые продажи</option>
            <option value="engagement">💬 Комментинг и взаимодействие</option>
          </select>
        </div>
        <div className="space-y-1">
          <label className="text-xs text-nexus-muted">Срок стратегии</label>
          <div className="flex gap-2">
            {[30, 60, 90].map(d => (
              <button key={d} onClick={() => set('strategy_duration', d)}
                className={`flex-1 py-2 text-xs rounded-lg border transition ${form.strategy_duration === d ? 'border-purple-500 bg-purple-600/20 text-purple-300' : 'border-nexus-border text-nexus-muted hover:border-nexus-text'}`}>
                {d}д
              </button>
            ))}
          </div>
        </div>
        <div className="space-y-1">
          <label className="text-xs text-nexus-muted">ID папки Google Drive (для кэша)</label>
          <input value={form.google_drive_folder_id || ''} onChange={e => set('google_drive_folder_id', e.target.value)}
            placeholder="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs"
            className="w-full bg-nexus-card border border-nexus-border rounded-lg px-3 py-2 text-xs text-nexus-text placeholder-nexus-muted focus:border-purple-500 outline-none font-mono" />
        </div>
      </div>

      <div className="flex items-center justify-between mt-4 pt-4 border-t border-nexus-border">
        <div className="flex items-center gap-4">
          <span className="text-xs text-nexus-muted">Режим нейросетей:</span>
          <button onClick={() => set('ai_mode', form.ai_mode === 'economy' ? 'premium' : 'economy')}
            className="flex items-center gap-2 text-sm font-medium transition">
            {form.ai_mode === 'economy'
              ? <><ToggleLeft className="w-6 h-6 text-nexus-muted" /><span className="text-nexus-muted">Эконом</span><span className="text-xs text-nexus-muted">(Gemini + GPT-mini)</span></>
              : <><ToggleRight className="w-6 h-6 text-yellow-400" /><span className="text-yellow-400">Премиум</span><span className="text-xs text-yellow-400">(Claude + Perplexity + GPT-4o)</span></>
            }
          </button>
        </div>
        <button onClick={calcCost} className="flex items-center gap-1 text-xs text-cyan-400 hover:text-cyan-300 transition">
          <DollarSign className="w-3 h-3" /> Рассчитать стоимость
          {cost !== null && <span className="ml-1 bg-cyan-900/40 px-2 py-0.5 rounded text-cyan-300 font-semibold">≈ ${cost}</span>}
        </button>
      </div>
    </div>
  )
}

function InfraCheck() {
  const [checking, setChecking] = useState(false)
  const [results, setResults] = useState(null)

  const check = async () => {
    setChecking(true)
    try {
      const r = await infrastructure.check()
      setResults(r.data)
    } catch { setResults(null) }
    setChecking(false)
  }

  return (
    <div className="glass rounded-xl p-4 mb-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Shield className="w-4 h-4 text-cyan-400" />
          <span className="text-sm font-medium text-nexus-text">Проверка подключений</span>
          {results && <span className="text-xs text-nexus-muted">{results.summary}</span>}
        </div>
        <button onClick={check} disabled={checking}
          className="px-3 py-1.5 text-xs rounded-lg border border-nexus-border text-nexus-muted hover:text-nexus-text hover:border-cyan-500 transition flex items-center gap-1">
          {checking ? <Loader className="w-3 h-3 animate-spin" /> : <Shield className="w-3 h-3" />}
          Проверить все
        </button>
      </div>
      {results && (
        <div className="mt-3 flex flex-wrap gap-2">
          {Object.entries(results.results).map(([key, val]) => (
            <span key={key} className={`flex items-center gap-1 text-xs px-2 py-1 rounded-lg border ${val.ok ? 'border-green-500/30 bg-green-900/20 text-green-400' : 'border-red-500/30 bg-red-900/20 text-red-400'}`}>
              {val.ok ? <CheckCircle className="w-3 h-3" /> : <AlertCircle className="w-3 h-3" />}
              {key.replace(/_/g, ' ')}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

export default function Dashboard() {
  const [niches, setNiches] = useState([])
  const [loading, setLoading] = useState(true)
  const [profileData, setProfileData] = useState({
    product_description: '', brand_style: '', strategy_focus: 'subscribers',
    strategy_duration: 30, ai_mode: 'economy', google_drive_folder_id: ''
  })

  const load = async () => {
    try {
      const [nr, pr] = await Promise.all([nichesApi.list(), profileApi.get()])
      setNiches(nr.data)
      setProfileData(pr.data)
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const handleDelete = async (id) => {
    if (!confirm('Удалить нишу?')) return
    await nichesApi.delete(id)
    setNiches(p => p.filter(n => n.id !== id))
  }

  const handleToggle = async (niche) => {
    const newStatus = niche.status === 'active' ? 'paused' : 'active'
    await nichesApi.update(niche.id, { status: newStatus })
    setNiches(p => p.map(n => n.id === niche.id ? { ...n, status: newStatus } : n))
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><Zap className="text-purple-400" /> NEXUS AI</h1>
          <p className="text-nexus-muted text-sm mt-1">Автоматизация контента</p>
        </div>
        <Link to="/new" className="px-4 py-2 rounded-lg bg-gradient-to-r from-purple-600 to-cyan-600 text-white text-sm font-medium hover:opacity-90 transition">
          + Новая ниша
        </Link>
      </div>

      <ProfilePanel profile={profileData} onSave={setProfileData} />
      <InfraCheck />

      <div className="grid grid-cols-4 gap-4 mb-6">
        {[
          { label: 'Активных ниш', value: niches.filter(n => n.status === 'active').length, icon: Zap, color: 'purple' },
          { label: 'Всего ниш', value: niches.length, icon: BarChart, color: 'cyan' },
          { label: 'Режим AI', value: profileData.ai_mode === 'premium' ? 'Premium' : 'Эконом', icon: Cpu, color: profileData.ai_mode === 'premium' ? 'yellow' : 'green' },
          { label: 'Агентов', value: '8', icon: Cpu, color: 'yellow' },
        ].map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="glass rounded-xl p-4">
            <div className="flex items-center gap-2 text-nexus-muted text-xs mb-2">
              <Icon className={`w-4 h-4 text-${color}-400`} />{label}
            </div>
            <div className="text-2xl font-bold text-nexus-text">{value}</div>
          </div>
        ))}
      </div>

      {loading ? (
        <div className="text-center text-nexus-muted py-12">Загрузка...</div>
      ) : niches.length === 0 ? (
        <div className="text-center py-20">
          <Zap className="w-12 h-12 text-purple-400 mx-auto mb-4 opacity-50" />
          <h3 className="text-lg font-medium text-nexus-muted mb-2">Ниш пока нет</h3>
          <Link to="/new" className="px-6 py-2 rounded-lg bg-purple-600 text-white text-sm hover:bg-purple-500 transition">Создать нишу</Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {niches.map(n => <NicheCard key={n.id} niche={n} onDelete={handleDelete} onToggle={handleToggle} />)}
        </div>
      )}
    </div>
  )
}