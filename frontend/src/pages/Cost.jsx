import React, { useState, useEffect } from 'react'
import { DollarSign, Save, RefreshCw, Loader, AlertTriangle } from 'lucide-react'
import { cost as costApi } from '../lib/api'

const PERIODS = [{ h: 24, l: 'Сутки' }, { h: 168, l: 'Неделя' }, { h: 720, l: 'Месяц' }]

export default function Cost() {
  const [data, setData] = useState(null)
  const [hours, setHours] = useState(24)
  const [budget, setBudget] = useState('')
  const [saved, setSaved] = useState(false)
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const r = await costApi.get(hours)
      setData(r.data)
      if (budget === '') setBudget(String(r.data?.budget?.limit_usd ?? ''))
    } catch { /* пусто — покажем состояние ниже */ }
    setLoading(false)
  }

  useEffect(() => { load() }, [hours])

  const save = async () => {
    try {
      await costApi.setBudget(parseFloat(budget) || 0)
      setSaved(true); setTimeout(() => setSaved(false), 1500); load()
    } catch {}
  }

  const b = data?.budget
  const pct = Math.min(100, b?.used_pct || 0)
  const barColor = b?.exceeded ? 'bg-red-500' : b?.alert ? 'bg-amber-500' : 'bg-green-500'

  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-5 flex-wrap gap-2">
        <div>
          <h1 className="text-xl font-bold gradient-text flex items-center gap-2">
            <DollarSign className="w-5 h-5 text-green-400" /> Расходы на AI
          </h1>
          <p className="text-xs text-[#5a5a7a] mt-1">
            Под учётом каждый вызов модели — включая автопилот, фабрику и дирижёра
          </p>
        </div>
        <div className="flex gap-2">
          {PERIODS.map(p => (
            <button key={p.h} onClick={() => setHours(p.h)}
              className={`text-xs px-3 py-1.5 rounded-lg border transition ${hours === p.h
                ? 'bg-violet-600/20 text-violet-300 border-violet-500/30'
                : 'bg-[#0d0d1a] text-[#7a7a9a] border-[#1c1c30]'}`}>{p.l}</button>
          ))}
          <button onClick={load} className="text-xs px-3 py-1.5 rounded-lg bg-[#0d0d1a] border border-[#1c1c30] text-[#c0c0e0]">
            {loading ? <Loader className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
          </button>
        </div>
      </div>

      {b && (
        <div className="card p-5 mb-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-[#e8e8f5]">Дневной бюджет</span>
            <span className={`text-sm ${b.exceeded ? 'text-red-400' : b.alert ? 'text-amber-400' : 'text-green-400'}`}>
              ${b.cost_usd.toFixed(4)} / ${b.limit_usd.toFixed(2)} ({b.used_pct}%)
            </span>
          </div>
          <div className="h-2 bg-[#0d0d1a] rounded-full overflow-hidden">
            <div className={`h-full ${barColor} transition-all`} style={{ width: `${pct}%` }} />
          </div>
          {b.exceeded && (
            <div className="mt-3 text-xs text-red-400 flex items-center gap-1.5">
              <AlertTriangle className="w-3 h-3" /> Дневной лимит исчерпан — платные модели лучше приостановить
            </div>
          )}
          <div className="flex items-end gap-2 mt-4">
            <div className="flex-1">
              <label className="text-[10px] text-[#5a5a7a]">Лимит в сутки, $ (0 — из переменной окружения)</label>
              <input type="number" step="0.5" min="0" value={budget} onChange={e => setBudget(e.target.value)}
                className="w-full bg-[#0d0d1a] border border-[#1c1c30] rounded-lg px-3 py-1.5 text-sm text-[#e8e8f5] focus:border-violet-500 outline-none" />
            </div>
            <button onClick={save}
              className="text-xs px-3 py-2 rounded-lg bg-violet-600/20 text-violet-300 border border-violet-500/30 flex items-center gap-1.5">
              <Save className="w-3 h-3" /> {saved ? 'Сохранено' : 'Сохранить'}
            </button>
          </div>
        </div>
      )}

      {data?.period && (
        <div className="grid grid-cols-3 gap-3 mb-4">
          <Stat label="Потрачено за период" value={`$${data.period.cost_usd.toFixed(4)}`} />
          <Stat label="Вызовов" value={data.period.calls} />
          <Stat label="Токенов" value={data.period.tokens.toLocaleString('ru')} />
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-4">
        <Table title="По моделям" rows={data?.by_model || []} nameKey="model" />
        <Table title="По агентам" rows={data?.by_agent || []} nameKey="agent" />
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

function Table({ title, rows, nameKey }) {
  return (
    <div className="card p-4">
      <div className="text-sm font-medium text-[#e8e8f5] mb-2">{title}</div>
      {rows.length === 0 && <div className="text-xs text-[#5a5a7a]">Пока нет данных</div>}
      {rows.map((r, i) => (
        <div key={i} className="flex items-center justify-between text-xs py-1.5 border-b border-[#1c1c30] last:border-0">
          <span className="text-[#c0c0e0] truncate mr-2">{r[nameKey]}</span>
          <span className="text-[#9a9ac0] shrink-0">
            ${r.cost_usd.toFixed(4)} <span className="text-[#5a5a7a]">· {r.calls}</span>
          </span>
        </div>
      ))}
    </div>
  )
}
