import React, { useState, useEffect } from 'react'
import { ListChecks, RefreshCw, XCircle, Loader, ChevronRight } from 'lucide-react'
import { tasks as tasksApi } from '../lib/api'

const STATUS = {
  CREATED:   { emoji: '🕓', cls: 'text-[#9a9ac0] bg-[#1c1c30]' },
  RUNNING:   { emoji: '⚙️', cls: 'text-cyan-400 bg-cyan-500/10' },
  WAITING:   { emoji: '⏸',  cls: 'text-amber-400 bg-amber-500/10' },
  COMPLETED: { emoji: '✅', cls: 'text-green-400 bg-green-500/10' },
  FAILED:    { emoji: '❌', cls: 'text-red-400 bg-red-500/10' },
  CANCELLED: { emoji: '🚫', cls: 'text-[#7a7a9a] bg-[#1c1c30]' },
}

const FILTERS = ['', 'RUNNING', 'FAILED', 'COMPLETED']

export default function Tasks() {
  const [list, setList] = useState([])
  const [stats, setStats] = useState(null)
  const [filter, setFilter] = useState('')
  const [open, setOpen] = useState(null)
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const [a, b] = await Promise.all([
        tasksApi.list(filter ? { status: filter } : {}),
        tasksApi.stats(),
      ])
      setList(a.data?.tasks || [])
      setStats(b.data || null)
    } catch { /* пустой список покажет состояние сам */ }
    setLoading(false)
  }

  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t) }, [filter])

  const cancel = async (id) => { try { await tasksApi.cancel(id) } catch {} ; load() }

  return (
    <div className="max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-5 flex-wrap gap-2">
        <div>
          <h1 className="text-xl font-bold gradient-text flex items-center gap-2">
            <ListChecks className="w-5 h-5 text-violet-400" /> Задачи
          </h1>
          <p className="text-xs text-[#5a5a7a] mt-1">
            Каждая фоновая работа — с ID, статусом, шагами и текстом ошибки
          </p>
        </div>
        <button onClick={load} className="text-xs px-3 py-1.5 rounded-lg bg-[#0d0d1a] border border-[#1c1c30] text-[#c0c0e0] flex items-center gap-1.5">
          {loading ? <Loader className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />} Обновить
        </button>
      </div>

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
          <Stat label="Всего задач" value={stats.total} />
          <Stat label="Выполняется" value={stats.by_status?.RUNNING || 0} />
          <Stat label="С ошибкой" value={stats.by_status?.FAILED || 0} />
          <Stat label="Расход AI" value={`$${(stats.cost_usd || 0).toFixed(4)}`} />
        </div>
      )}

      <div className="flex gap-2 mb-3">
        {FILTERS.map(f => (
          <button key={f || 'all'} onClick={() => setFilter(f)}
            className={`text-xs px-3 py-1 rounded-lg border transition ${filter === f
              ? 'bg-violet-600/20 text-violet-300 border-violet-500/30'
              : 'bg-[#0d0d1a] text-[#7a7a9a] border-[#1c1c30]'}`}>
            {f || 'Все'}
          </button>
        ))}
      </div>

      <div className="space-y-2">
        {list.length === 0 && (
          <div className="card p-6 text-center text-sm text-[#5a5a7a]">
            Задач пока нет. Запусти генерацию, фабрику или команду в Центре управления.
          </div>
        )}
        {list.map(t => {
          const st = STATUS[t.status] || STATUS.CREATED
          const isOpen = open === t.id
          return (
            <div key={t.id} className="card p-4">
              <div className="flex items-start gap-3 cursor-pointer" onClick={() => setOpen(isOpen ? null : t.id)}>
                <span className={`text-xs px-2 py-1 rounded-lg shrink-0 ${st.cls}`}>{st.emoji} {t.status}</span>
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-[#e8e8f5] truncate">{t.goal || t.kind}</div>
                  <div className="text-[11px] text-[#5a5a7a] mt-0.5">
                    <code>{t.id}</code> · {t.kind} · {t.source}
                    {t.duration_sec ? ` · ${t.duration_sec.toFixed(0)}с` : ''}
                    {t.attempts > 1 ? ` · попыток: ${t.attempts}` : ''}
                    {t.cost_usd ? ` · $${t.cost_usd.toFixed(4)}` : ''}
                  </div>
                  {t.error && !isOpen && (
                    <div className="text-[11px] text-red-400 mt-1 truncate">⚠️ {t.error}</div>
                  )}
                </div>
                {['CREATED', 'RUNNING', 'WAITING'].includes(t.status) && (
                  <button onClick={e => { e.stopPropagation(); cancel(t.id) }}
                    title="Отменить" className="text-[#7a7a9a] hover:text-red-400">
                    <XCircle className="w-4 h-4" />
                  </button>
                )}
                <ChevronRight className={`w-4 h-4 text-[#5a5a7a] transition ${isOpen ? 'rotate-90' : ''}`} />
              </div>

              {isOpen && (
                <div className="mt-3 pt-3 border-t border-[#1c1c30] space-y-2 text-xs">
                  {t.error && (
                    <div className="bg-red-500/10 text-red-300 rounded-lg px-3 py-2 whitespace-pre-wrap">
                      {t.error}
                    </div>
                  )}
                  {(t.agents || []).length > 0 && (
                    <div className="text-[#9a9ac0]">Агенты: {t.agents.join(', ')}</div>
                  )}
                  {(t.models || []).length > 0 && (
                    <div className="text-[#9a9ac0]">Модели: {t.models.join(', ')}</div>
                  )}
                  {(t.steps || []).length > 0 && (
                    <div>
                      <div className="text-[#7a7a9a] mb-1">Шаги</div>
                      {t.steps.map((s, i) => (
                        <div key={i} className="bg-[#0d0d1a] rounded px-2 py-1 mb-1">
                          <span className={s.ok ? 'text-green-400' : 'text-red-400'}>{s.ok ? '✓' : '✗'}</span>{' '}
                          {s.action}{s.agent ? <span className="text-[#5a5a7a]"> — {s.agent}</span> : null}
                          {s.error ? <span className="text-red-400"> · {s.error}</span> : null}
                        </div>
                      ))}
                    </div>
                  )}
                  {t.result && (
                    <pre className="bg-[#0d0d1a] rounded px-2 py-1 overflow-x-auto text-[#9a9ac0]">
                      {JSON.stringify(t.result, null, 2)}
                    </pre>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div className="card p-3">
      <div className="text-[10px] text-[#5a5a7a]">{label}</div>
      <div className="text-lg font-semibold text-[#e8e8f5] mt-0.5">{value}</div>
    </div>
  )
}
