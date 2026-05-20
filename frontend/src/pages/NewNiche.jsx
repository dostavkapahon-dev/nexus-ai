import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Zap, Loader } from 'lucide-react'
import { niches as nichesApi } from '../lib/api'

const PLATFORMS = ['telegram', 'instagram', 'tiktok', 'threads', 'whatsapp']
const GOALS = ['subscribers', 'sales', 'awareness']
const TONES = ['neutral', 'friendly', 'professional', 'humorous', 'emotional']
const GOAL_LABELS = { subscribers: 'Подписчики', sales: 'Продажи', awareness: 'Узнаваемость' }
const TONE_LABELS = { neutral: 'Нейтральный', friendly: 'Дружелюбный', professional: 'Профессиональный', humorous: 'Юмористический', emotional: 'Эмоциональный' }

export default function NewNiche() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [form, setForm] = useState({
    name: '', city: '', goal: 'subscribers', budget_usd: 0,
    posts_per_day: 1, platforms: ['telegram'], tone_of_voice: 'neutral', about_user: '',
  })

  const set = (k, v) => setForm(p => ({ ...p, [k]: v }))
  const togglePlatform = (p) => {
    const cur = form.platforms
    set('platforms', cur.includes(p) ? cur.filter(x => x !== p) : [...cur, p])
  }

  const submit = async (e) => {
    e.preventDefault()
    if (!form.name.trim()) return
    setLoading(true)
    try {
      await nichesApi.create(form)
      navigate('/')
    } finally { setLoading(false) }
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Zap className="text-purple-400" /> Новая ниша</h1>
        <p className="text-nexus-muted text-sm mt-1">NEXUS проанализирует нишу и создаст 30-дневный план</p>
      </div>

      <form onSubmit={submit} className="space-y-5">
        <div className="glass rounded-xl p-5 space-y-4">
          <h3 className="text-sm font-semibold text-purple-300 uppercase tracking-wider">Основное</h3>
          <div>
            <label className="text-xs text-nexus-muted mb-1 block">Ниша *</label>
            <input required value={form.name} onChange={e => set('name', e.target.value)}
              placeholder="Например: фитнес, кулинария, психология..."
              className="w-full bg-nexus-card border border-nexus-border rounded-lg px-3 py-2 text-sm text-nexus-text placeholder-nexus-muted focus:border-purple-500 outline-none" />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-nexus-muted mb-1 block">Город</label>
              <input value={form.city} onChange={e => set('city', e.target.value)} placeholder="Москва"
                className="w-full bg-nexus-card border border-nexus-border rounded-lg px-3 py-2 text-sm text-nexus-text placeholder-nexus-muted focus:border-purple-500 outline-none" />
            </div>
            <div>
              <label className="text-xs text-nexus-muted mb-1 block">Цель</label>
              <select value={form.goal} onChange={e => set('goal', e.target.value)}
                className="w-full bg-nexus-card border border-nexus-border rounded-lg px-3 py-2 text-sm text-nexus-text focus:border-purple-500 outline-none">
                {GOALS.map(g => <option key={g} value={g}>{GOAL_LABELS[g]}</option>)}
              </select>
            </div>
          </div>
        </div>

        <div className="glass rounded-xl p-5 space-y-4">
          <h3 className="text-sm font-semibold text-purple-300 uppercase tracking-wider">Платформы</h3>
          <div className="flex flex-wrap gap-2">
            {PLATFORMS.map(p => (
              <button key={p} type="button" onClick={() => togglePlatform(p)}
                className={`px-3 py-1.5 rounded-lg text-sm capitalize transition border ${form.platforms.includes(p) ? 'bg-purple-600/30 border-purple-500 text-purple-300' : 'bg-nexus-card border-nexus-border text-nexus-muted hover:border-purple-500/50'}`}>
                {p}
              </button>
            ))}
          </div>
        </div>

        <div className="glass rounded-xl p-5 space-y-4">
          <h3 className="text-sm font-semibold text-purple-300 uppercase tracking-wider">Настройки</h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-nexus-muted mb-1 block">Постов в день: {form.posts_per_day}</label>
              <input type="range" min="1" max="5" value={form.posts_per_day}
                onChange={e => set('posts_per_day', Number(e.target.value))} className="w-full accent-purple-500" />
            </div>
            <div>
              <label className="text-xs text-nexus-muted mb-1 block">Бюджет USD/мес</label>
              <input type="number" min="0" value={form.budget_usd}
                onChange={e => set('budget_usd', Number(e.target.value))}
                className="w-full bg-nexus-card border border-nexus-border rounded-lg px-3 py-2 text-sm text-nexus-text focus:border-purple-500 outline-none" />
            </div>
          </div>
          <div>
            <label className="text-xs text-nexus-muted mb-1 block">Тональность</label>
            <div className="flex flex-wrap gap-2">
              {TONES.map(t => (
                <button key={t} type="button" onClick={() => set('tone_of_voice', t)}
                  className={`px-3 py-1 rounded-lg text-xs capitalize transition border ${form.tone_of_voice === t ? 'bg-cyan-600/30 border-cyan-500 text-cyan-300' : 'bg-nexus-card border-nexus-border text-nexus-muted hover:border-cyan-500/50'}`}>
                  {TONE_LABELS[t]}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="glass rounded-xl p-5 space-y-4">
          <h3 className="text-sm font-semibold text-purple-300 uppercase tracking-wider">О вас</h3>
          <textarea value={form.about_user} onChange={e => set('about_user', e.target.value)}
            placeholder="Расскажите о себе: кто вы, чем занимаетесь, ваш стиль общения..."
            rows={4} className="w-full bg-nexus-card border border-nexus-border rounded-lg px-3 py-2 text-sm text-nexus-text placeholder-nexus-muted focus:border-purple-500 outline-none resize-none" />
        </div>

        <button type="submit" disabled={loading || !form.name}
          className="w-full py-3 rounded-xl bg-gradient-to-r from-purple-600 to-cyan-600 text-white font-semibold text-sm hover:opacity-90 transition disabled:opacity-50 flex items-center justify-center gap-2">
          {loading ? <><Loader className="w-4 h-4 animate-spin" /> Запускаем NEXUS...</> : <><Zap className="w-4 h-4" /> ЗАПУСТИТЬ NEXUS</>}
        </button>
      </form>
    </div>
  )
}
