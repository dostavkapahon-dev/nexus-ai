import React, { useState, useEffect } from 'react'
import { Search, Plus, RefreshCw, Loader, TrendingUp, TrendingDown, Trash2, Users } from 'lucide-react'
import { research } from '../lib/api'

const KINDS = [
  { k: '', l: 'Все' }, { k: 'trends', l: 'Тренды' },
  { k: 'viral', l: 'Разборы роликов' }, { k: 'competitor', l: 'Конкуренты' },
]
const PLATFORMS = ['instagram', 'youtube', 'tiktok']

export default function Research() {
  const [items, setItems] = useState([])
  const [comps, setComps] = useState([])
  const [kind, setKind] = useState('')
  const [platform, setPlatform] = useState('instagram')
  const [handle, setHandle] = useState('')
  const [busy, setBusy] = useState('')

  const load = async () => {
    try {
      const [a, b] = await Promise.all([research.history(kind), research.competitors()])
      setItems(a.data?.items || []); setComps(b.data?.competitors || [])
    } catch {}
  }
  useEffect(() => { load() }, [kind])

  const add = async () => {
    if (!handle.trim()) return
    setBusy('add')
    try {
      const r = await research.trackCompetitor(platform, handle.trim())
      if (!r.data?.ok) alert(r.data?.error || 'Не удалось получить данные')
      setHandle('')
    } catch (e) { alert('Ошибка: ' + e.message) }
    setBusy(''); load()
  }

  const refresh = async () => {
    setBusy('refresh')
    try {
      const r = await research.refreshCompetitors()
      alert(`Обновлено: ${r.data?.updated ?? 0} из ${r.data?.total ?? 0}`)
    } catch (e) { alert('Ошибка: ' + e.message) }
    setBusy(''); load()
  }

  const stop = async (p, h) => {
    if (!confirm(`Перестать следить за @${h}? История сохранится.`)) return
    try { await research.stopCompetitor(p, h) } catch {}
    load()
  }

  return (
    <div className="max-w-5xl mx-auto">
      <div className="mb-5">
        <h1 className="text-xl font-bold gradient-text flex items-center gap-2">
          <Search className="w-5 h-5 text-cyan-400" /> Исследования рынка
        </h1>
        <p className="text-xs text-[#5a5a7a] mt-1">
          История трендов и разборов + динамика конкурентов — на этом строится стратегия
        </p>
      </div>

      {/* КОНКУРЕНТЫ */}
      <div className="card p-5 mb-4">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <span className="font-semibold flex items-center gap-2">
            <Users className="w-4 h-4 text-violet-400" /> Конкуренты
          </span>
          <button onClick={refresh} disabled={!!busy}
            className="text-xs px-3 py-1.5 rounded-lg bg-[#0d0d1a] border border-[#1c1c30] text-[#c0c0e0] disabled:opacity-50 flex items-center gap-1.5">
            {busy === 'refresh' ? <Loader className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
            Обновить срезы
          </button>
        </div>

        <div className="flex gap-2 mb-3 flex-wrap">
          <select value={platform} onChange={e => setPlatform(e.target.value)}
            className="bg-[#0d0d1a] border border-[#1c1c30] rounded-lg px-2 py-1.5 text-xs text-[#e8e8f5] outline-none">
            {PLATFORMS.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
          <input value={handle} onChange={e => setHandle(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && add()}
            placeholder="ник конкурента без @"
            className="flex-1 min-w-[160px] bg-[#0d0d1a] border border-[#1c1c30] rounded-lg px-3 py-1.5 text-xs text-[#e8e8f5] placeholder-[#5a5a7a] focus:border-violet-500 outline-none" />
          <button onClick={add} disabled={!!busy}
            className="text-xs px-3 py-1.5 rounded-lg bg-violet-600/20 text-violet-300 border border-violet-500/30 disabled:opacity-50 flex items-center gap-1.5">
            <Plus className="w-3 h-3" /> Следить
          </button>
        </div>

        {comps.length === 0 && (
          <div className="text-xs text-[#5a5a7a]">
            Пока никого не отслеживаем. Добавь конкурента — раз в неделю система будет
            снимать его метрики и показывать динамику.
          </div>
        )}
        {comps.map(c => (
          <div key={c.platform + c.handle}
            className="flex items-center justify-between py-2 border-b border-[#1c1c30] last:border-0">
            <div className="min-w-0">
              <div className="text-sm text-[#e8e8f5] truncate">
                @{c.handle} <span className="text-[10px] text-[#5a5a7a]">{c.platform}</span>
              </div>
              <div className="text-[11px] text-[#7a7a9a]">
                {(c.followers || 0).toLocaleString('ru')} подписчиков · ER {c.avg_engagement}%
                · срезов: {c.snapshots}
              </div>
            </div>
            <div className="flex items-center gap-3 shrink-0">
              {c.followers_delta != null && c.followers_delta !== 0 && (
                <span className={`text-xs flex items-center gap-1 ${c.followers_delta > 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {c.followers_delta > 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                  {c.followers_delta > 0 ? '+' : ''}{c.followers_delta}
                </span>
              )}
              <button onClick={() => stop(c.platform, c.handle)} className="text-[#5a5a7a] hover:text-red-400">
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* ИСТОРИЯ ИССЛЕДОВАНИЙ */}
      <div className="flex gap-2 mb-3 flex-wrap">
        {KINDS.map(k => (
          <button key={k.k || 'all'} onClick={() => setKind(k.k)}
            className={`text-xs px-3 py-1 rounded-lg border transition ${kind === k.k
              ? 'bg-violet-600/20 text-violet-300 border-violet-500/30'
              : 'bg-[#0d0d1a] text-[#7a7a9a] border-[#1c1c30]'}`}>{k.l}</button>
        ))}
      </div>

      <div className="space-y-2">
        {items.length === 0 && (
          <div className="card p-6 text-center text-sm text-[#5a5a7a]">
            Исследований пока нет. Запусти <code>/trend</code> или <code>/viral ссылка</code> —
            результаты будут копиться здесь.
          </div>
        )}
        {items.map(i => (
          <div key={i.id} className="card p-4">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400">{i.kind}</span>
              <span className="text-[11px] text-[#5a5a7a]">{(i.created_at || '').slice(0, 16).replace('T', ' ')}</span>
              {i.query && <span className="text-[11px] text-[#7a7a9a] truncate">· {i.query}</span>}
            </div>
            <div className="text-sm text-[#c0c0e0] whitespace-pre-wrap">{i.summary || '—'}</div>
            {(i.sources || []).length > 0 && (
              <div className="text-[10px] text-[#5a5a7a] mt-1 truncate">
                источники: {i.sources.filter(Boolean).slice(0, 3).join(', ')}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
