import React, { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { Zap, Play, Pause, Trash2, BarChart, CheckCircle, Cpu } from 'lucide-react'
import { niches as nichesApi } from '../lib/api'

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
      else if (data.event === 'pipeline_complete') setAgents({})
    }
    return () => ws.close()
  }, [niche.id])

  const activeAgents = Object.entries(agents).filter(([, s]) => s === 'running')

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

export default function Dashboard() {
  const [niches, setNiches] = useState([])
  const [loading, setLoading] = useState(true)

  const load = async () => {
    try {
      const r = await nichesApi.list()
      setNiches(r.data)
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

      <div className="grid grid-cols-4 gap-4 mb-6">
        {[
          { label: 'Активных ниш', value: niches.filter(n => n.status === 'active').length, icon: Zap, color: 'purple' },
          { label: 'Всего ниш', value: niches.length, icon: BarChart, color: 'cyan' },
          { label: 'Статус', value: 'Online', icon: CheckCircle, color: 'green' },
          { label: 'Агентов', value: '8', icon: Cpu, color: 'yellow' },
        ].map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="glass rounded-xl p-4">
            <div className={`flex items-center gap-2 text-nexus-muted text-xs mb-2`}>
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
