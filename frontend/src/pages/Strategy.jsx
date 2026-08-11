import React, { useState, useEffect } from 'react'
import { Compass, Play, Plus, Archive, Award, Loader } from 'lucide-react'
import { strategy as api } from '../lib/api'

export default function Strategy() {
  const [items, setItems] = useState([])
  const [current, setCurrent] = useState(null)
  const [best, setBest] = useState(null)
  const [form, setForm] = useState({ title: '', angle: '', plan: '' })
  const [busy, setBusy] = useState('')

  const load = async () => {
    try {
      const [a, b] = await Promise.all([api.effectiveness(), api.current()])
      setItems(a.data?.strategies || []); setBest(a.data?.best || null)
      setCurrent(b.data?.id ? b.data : null)
    } catch {}
  }
  useEffect(() => { load() }, [])

  const activate = async (id) => {
    setBusy(id); try { await api.activate(id) } catch {} ; setBusy(''); load()
  }
  const addManual = async () => {
    if (!form.title.trim()) return
    setBusy('add')
    try { await api.manual(form); setForm({ title: '', angle: '', plan: '' }) } catch {}
    setBusy(''); load()
  }

  return (
    <div className="max-w-4xl mx-auto">
      <div className="mb-5">
        <h1 className="text-xl font-bold gradient-text flex items-center gap-2">
          <Compass className="w-5 h-5 text-violet-400" /> Стратегии
        </h1>
        <p className="text-xs text-[#5a5a7a] mt-1">
          Версии с измеримым результатом — видно, какая реально работала лучше
        </p>
      </div>

      {current && (
        <div className="card p-5 mb-4 border border-violet-500/30">
          <div className="flex items-center gap-2 mb-1">
            <Play className="w-4 h-4 text-violet-400" />
            <span className="font-semibold text-[#e8e8f5]">Действующая: {current.title}</span>
            <span className="text-[10px] text-[#5a5a7a]">v{current.version}</span>
          </div>
          {current.angle && <div className="text-sm text-[#c0c0e0] mt-1">{current.angle}</div>}
          {current.plan && <div className="text-xs text-[#7a7a9a] mt-2 whitespace-pre-wrap">{current.plan}</div>}
        </div>
      )}

      {best && current && best.id !== current.id && (
        <div className="card p-4 mb-4 border border-amber-500/30">
          <div className="text-sm text-amber-400 flex items-center gap-2">
            <Award className="w-4 h-4" />
            Лучший результат показала «{best.title}» — ER {best.avg_engagement_rate}%
            ({best.posts} публикаций)
          </div>
          <button onClick={() => activate(best.id)}
            className="mt-2 text-xs px-3 py-1 rounded-lg bg-amber-500/15 text-amber-300 border border-amber-500/30">
            Вернуться к ней
          </button>
        </div>
      )}

      <div className="card p-4 mb-4">
        <div className="text-sm font-medium text-[#e8e8f5] mb-2">Своя стратегия</div>
        <div className="space-y-2">
          <input value={form.title} onChange={e => setForm({ ...form, title: e.target.value })}
            placeholder="Название"
            className="w-full bg-[#0d0d1a] border border-[#1c1c30] rounded-lg px-3 py-1.5 text-sm text-[#e8e8f5] placeholder-[#5a5a7a] focus:border-violet-500 outline-none" />
          <input value={form.angle} onChange={e => setForm({ ...form, angle: e.target.value })}
            placeholder="Угол подачи"
            className="w-full bg-[#0d0d1a] border border-[#1c1c30] rounded-lg px-3 py-1.5 text-sm text-[#e8e8f5] placeholder-[#5a5a7a] focus:border-violet-500 outline-none" />
          <textarea rows={2} value={form.plan} onChange={e => setForm({ ...form, plan: e.target.value })}
            placeholder="План на неделю"
            className="w-full bg-[#0d0d1a] border border-[#1c1c30] rounded-lg px-3 py-1.5 text-sm text-[#e8e8f5] placeholder-[#5a5a7a] focus:border-violet-500 outline-none resize-none" />
          <button onClick={addManual} disabled={!!busy}
            className="text-xs px-3 py-1.5 rounded-lg bg-violet-600/20 text-violet-300 border border-violet-500/30 disabled:opacity-50 flex items-center gap-1.5">
            {busy === 'add' ? <Loader className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />} Добавить
          </button>
        </div>
      </div>

      <div className="space-y-2">
        {items.length === 0 && (
          <div className="card p-6 text-center text-sm text-[#5a5a7a]">
            Стратегий пока нет. Запусти <code>/strategy</code> — агент предложит варианты
            на основе данных аккаунта и рынка.
          </div>
        )}
        {items.map(s => (
          <div key={s.id} className="card p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium text-[#e8e8f5]">{s.title}</span>
                  <span className="text-[10px] text-[#5a5a7a]">v{s.version}</span>
                  {s.status === 'active' && <span className="text-[10px] px-2 py-0.5 rounded-full bg-violet-500/15 text-violet-300">действующая</span>}
                  {s.status === 'archived' && <Archive className="w-3 h-3 text-[#5a5a7a]" />}
                  {s.source === 'manual' && <span className="text-[10px] text-[#7a7a9a]">своя</span>}
                </div>
                {s.angle && <div className="text-xs text-[#9a9ac0] mt-1">{s.angle}</div>}
                <div className="text-[11px] text-[#5a5a7a] mt-1">
                  {s.posts} публикаций · {(s.views || 0).toLocaleString('ru')} просмотров
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className={`text-sm ${s.avg_engagement_rate >= 5 ? 'text-green-400' : 'text-[#9a9ac0]'}`}>
                  ER {s.avg_engagement_rate}%
                </span>
                {s.status !== 'active' && (
                  <button onClick={() => activate(s.id)} disabled={!!busy}
                    className="text-xs px-2.5 py-1 rounded-lg bg-[#0d0d1a] border border-[#1c1c30] text-[#c0c0e0] disabled:opacity-50">
                    Включить
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
