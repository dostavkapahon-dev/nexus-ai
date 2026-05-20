import React, { useState, useEffect } from 'react'
import { BarChart2, TrendingUp, Cpu, DollarSign, FileText, Zap } from 'lucide-react'
import { analytics as analyticsApi, niches as nichesApi } from '../lib/api'

export default function Analytics() {
  const [niches, setNiches] = useState([])
  const [selected, setSelected] = useState('')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    nichesApi.list().then(r => {
      setNiches(r.data)
      if (r.data.length > 0) setSelected(r.data[0].id)
    })
  }, [])

  useEffect(() => {
    if (!selected) return
    setLoading(true)
    analyticsApi.get(selected).then(r => { setData(r.data); setLoading(false) })
  }, [selected])

  const stats = data ? [
    { label: 'Запланировано', value: data.total_planned ?? 0, icon: FileText, color: 'purple' },
    { label: 'Сгенерировано', value: data.total_generated ?? 0, icon: Zap, color: 'cyan' },
    { label: 'Опубликовано', value: data.total_published ?? 0, icon: TrendingUp, color: 'green' },
    { label: 'Токенов', value: (data.total_tokens ?? 0).toLocaleString(), icon: Cpu, color: 'yellow' },
    { label: 'Стоимость AI', value: `$${(data.total_cost ?? 0).toFixed(4)}`, icon: DollarSign, color: 'pink' },
  ] : []

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold flex items-center gap-2"><BarChart2 className="text-purple-400" /> Аналитика</h1>
        <select value={selected} onChange={e => setSelected(e.target.value)}
          className="bg-nexus-card border border-nexus-border rounded-lg px-3 py-2 text-sm text-nexus-text focus:border-purple-500 outline-none">
          {niches.map(n => <option key={n.id} value={n.id}>{n.name}</option>)}
        </select>
      </div>

      {loading ? (
        <div className="text-center text-nexus-muted py-12">Загрузка...</div>
      ) : !data ? (
        <div className="text-center text-nexus-muted py-12">Выберите нишу</div>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4 mb-6">
            {stats.map(({ label, value, icon: Icon, color }) => (
              <div key={label} className="glass rounded-xl p-4">
                <div className={`flex items-center gap-2 text-nexus-muted text-xs mb-2`}>
                  <Icon className={`w-4 h-4 text-${color}-400`} />{label}
                </div>
                <div className="text-xl font-bold text-nexus-text">{value}</div>
              </div>
            ))}
          </div>

          {data.recent_logs?.length > 0 && (
            <div className="glass rounded-xl p-5">
              <h3 className="text-sm font-semibold text-purple-300 uppercase tracking-wider mb-4">Последние действия агентов</h3>
              <div className="space-y-2">
                {data.recent_logs.map((log, i) => (
                  <div key={i} className="flex items-center gap-3 text-xs py-2 border-b border-nexus-border last:border-0">
                    <span className="text-nexus-muted w-28 flex-shrink-0">{log.agent_name}</span>
                    <span className={`px-2 py-0.5 rounded-full border ${log.status === 'success' ? 'bg-green-900/30 border-green-500/30 text-green-400' : 'bg-red-900/30 border-red-500/30 text-red-400'}`}>{log.status}</span>
                    <span className="text-nexus-muted flex-1 truncate">{log.model_used || '—'}</span>
                    <span className="text-nexus-muted">{log.tokens_used ? `${log.tokens_used} tok` : ''}</span>
                    <span className="text-nexus-muted">{log.duration_sec ? `${log.duration_sec.toFixed(1)}s` : ''}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
