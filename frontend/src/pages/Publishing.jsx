import React, { useState, useEffect } from 'react'
import { Send, RefreshCw, Loader, RotateCw, XCircle, PlayCircle } from 'lucide-react'
import { publishing } from '../lib/api'

// Статусы очереди. «Заблокировано» — это не сбой, а честный отказ площадки:
// повторять его бессмысленно, поэтому и цвет другой, чем у ошибки.
const STATUS = {
  scheduled: { emoji: '🕓', label: 'В расписании', cls: 'text-cyan-400 bg-cyan-500/10' },
  retrying:  { emoji: '🔁', label: 'Повтор',       cls: 'text-amber-400 bg-amber-500/10' },
  published: { emoji: '✅', label: 'Опубликовано', cls: 'text-green-400 bg-green-500/10' },
  failed:    { emoji: '❌', label: 'Не удалось',   cls: 'text-red-400 bg-red-500/10' },
  blocked:   { emoji: '🚫', label: 'Заблокировано API', cls: 'text-orange-400 bg-orange-500/10' },
  cancelled: { emoji: '⛔', label: 'Отменено',     cls: 'text-[#7a7a9a] bg-[#1c1c30]' },
}

const FILTERS = ['', 'scheduled', 'retrying', 'failed', 'blocked', 'published']

const fmt = (iso) => (iso ? iso.slice(0, 16).replace('T', ' ') : '—')

export default function Publishing() {
  const [items, setItems] = useState([])
  const [stats, setStats] = useState({})
  const [filter, setFilter] = useState('')
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      const r = await publishing.queue(filter)
      setItems(r.data?.items || [])
      setStats(r.data?.stats || {})
    } catch { /* пустая очередь покажет состояние сама */ }
    setLoading(false)
  }

  useEffect(() => { load(); const t = setInterval(load, 10000); return () => clearInterval(t) }, [filter])

  const act = async (fn, id) => { setBusy(id); try { await fn(id) } catch {} ; setBusy(''); load() }
  const processNow = async () => { setBusy('all'); try { await publishing.process() } catch {} ; setBusy(''); load() }

  return (
    <div className="max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-5 flex-wrap gap-2">
        <div>
          <h1 className="text-xl font-bold gradient-text flex items-center gap-2">
            <Send className="w-5 h-5 text-violet-400" /> Публикации
          </h1>
          <p className="text-xs text-[#5a5a7a] mt-1">
            Очередь расписания и повторы: сетевой сбой не теряет пост
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={processNow}
            className="text-xs px-3 py-1.5 rounded-lg bg-violet-600/15 border border-violet-500/25 text-violet-300 flex items-center gap-1.5">
            {busy === 'all' ? <Loader className="w-3 h-3 animate-spin" /> : <PlayCircle className="w-3 h-3" />}
            Разобрать сейчас
          </button>
          <button onClick={load}
            className="text-xs px-3 py-1.5 rounded-lg bg-[#0d0d1a] border border-[#1c1c30] text-[#c0c0e0] flex items-center gap-1.5">
            {loading ? <Loader className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />} Обновить
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <Stat label="В расписании" value={stats.scheduled || 0} />
        <Stat label="Ждут повтора" value={stats.retrying || 0} />
        <Stat label="Опубликовано" value={stats.published || 0} />
        <Stat label="Не удалось" value={(stats.failed || 0) + (stats.blocked || 0)} />
      </div>

      <div className="flex gap-1.5 mb-3 flex-wrap">
        {FILTERS.map((f) => (
          <button key={f || 'all'} onClick={() => setFilter(f)}
            className={`text-[11px] px-2.5 py-1 rounded-md border transition ${
              filter === f ? 'bg-violet-600/15 border-violet-500/25 text-violet-300'
                           : 'bg-[#0d0d1a] border-[#1c1c30] text-[#5a5a7a]'}`}>
            {f ? STATUS[f]?.label || f : 'Все'}
          </button>
        ))}
      </div>

      {items.length === 0 && (
        <div className="text-center text-xs text-[#5a5a7a] py-10 border border-[#1c1c30] rounded-xl bg-[#0d0d1a]">
          Очередь пуста — публиковать нечего.
        </div>
      )}

      <div className="space-y-2">
        {items.map((i) => {
          const st = STATUS[i.status] || { emoji: '•', label: i.status, cls: 'text-[#9a9ac0] bg-[#1c1c30]' }
          const canRetry = i.status !== 'published' && i.status !== 'cancelled'
          return (
            <div key={i.id} className="border border-[#1c1c30] rounded-xl bg-[#0d0d1a] p-3">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="flex items-center gap-2 min-w-0">
                  <span className={`text-[11px] px-2 py-0.5 rounded-md ${st.cls}`}>{st.emoji} {st.label}</span>
                  <span className="text-xs text-[#c0c0e0]">{i.platform}</span>
                  <span className="text-[11px] text-[#5a5a7a]">попыток: {i.attempts}</span>
                </div>
                <div className="flex gap-1.5">
                  {canRetry && (
                    <button onClick={() => act(publishing.retry, i.id)}
                      className="text-[11px] px-2 py-1 rounded-md bg-[#111120] border border-[#1c1c30] text-[#c0c0e0] flex items-center gap-1">
                      {busy === i.id ? <Loader className="w-3 h-3 animate-spin" /> : <RotateCw className="w-3 h-3" />} Повторить
                    </button>
                  )}
                  {(i.status === 'scheduled' || i.status === 'retrying') && (
                    <button onClick={() => act(publishing.cancel, i.id)}
                      className="text-[11px] px-2 py-1 rounded-md bg-[#111120] border border-[#1c1c30] text-[#7a7a9a] flex items-center gap-1">
                      <XCircle className="w-3 h-3" /> Снять
                    </button>
                  )}
                </div>
              </div>

              <div className="text-xs text-[#9a9ac0] mt-2 line-clamp-2">{i.text || i.topic || '—'}</div>

              <div className="text-[11px] text-[#5a5a7a] mt-1.5 flex gap-3 flex-wrap">
                <span>план: {fmt(i.scheduled_at)}</span>
                {i.next_retry_at && <span>повтор: {fmt(i.next_retry_at)}</span>}
                {i.post_url && (
                  <a href={i.post_url} target="_blank" rel="noreferrer" className="text-violet-400 hover:underline">
                    открыть пост
                  </a>
                )}
              </div>

              {i.error && (
                <div className="text-[11px] text-red-400/90 mt-1.5 bg-red-500/5 border border-red-500/15 rounded-md px-2 py-1">
                  ⚠️ {i.error}
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
    <div className="border border-[#1c1c30] rounded-xl bg-[#0d0d1a] px-3 py-2.5">
      <div className="text-[10px] text-[#5a5a7a]">{label}</div>
      <div className="text-lg font-bold text-[#c0c0e0]">{value}</div>
    </div>
  )
}
