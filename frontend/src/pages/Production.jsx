import React, { useEffect, useState } from 'react'
import { Clapperboard, Loader, RefreshCw, RotateCcw, X, ChevronDown, ChevronUp } from 'lucide-react'
import { production } from '../lib/api'

// Производство роликов внешним исполнителем. Здесь видно, какое ТЗ ушло,
// кто его взял и что вернулось — иначе «ждём ролик» выглядит как зависание.

const STATUS = {
  queued: { label: 'ждёт исполнителя', cls: 'text-amber-300 border-amber-500/25 bg-amber-500/5' },
  taken: { label: 'в работе', cls: 'text-violet-300 border-violet-500/25 bg-violet-600/10' },
  done: { label: 'готово', cls: 'text-emerald-300 border-emerald-500/25 bg-emerald-500/5' },
  failed: { label: 'не удалось', cls: 'text-red-300 border-red-500/25 bg-red-500/5' },
  cancelled: { label: 'отменено', cls: 'text-[#5a5a7a] border-[#1c1c30] bg-[#0d0d1c]' },
}

const fmt = (iso) => (iso ? iso.slice(0, 16).replace('T', ' ') : '—')

function Job({ job, onRetry, onCancel }) {
  const [open, setOpen] = useState(false)
  const st = STATUS[job.status] || STATUS.queued
  const brief = job.brief || {}

  return (
    <div className={`rounded-xl border p-4 ${st.cls}`}>
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-medium">{brief.theme || job.kind}</span>
        <span className="text-xs">{st.label}</span>
        <span className="ml-auto text-[11px] text-[#5a5a7a] font-mono">{job.id.slice(0, 8)}</span>
      </div>

      {brief.hook_text && (
        <div className="text-xs text-[#8a8ab0] mt-1">Хук: {brief.hook_text}</div>
      )}
      <div className="text-[11px] text-[#5a5a7a] mt-2">
        создано {fmt(job.created_at)}
        {job.taken_at && ` · взято ${fmt(job.taken_at)}`}
        {job.done_at && ` · готово ${fmt(job.done_at)}`}
      </div>

      {job.error && <div className="text-xs text-red-300 mt-2">{job.error}</div>}

      {job.assets?.video_url && (
        <a href={job.assets.video_url} target="_blank" rel="noreferrer"
          className="text-xs text-cyan-400 hover:underline mt-2 inline-block">
          готовый ролик ↗
        </a>
      )}

      <div className="flex items-center gap-3 mt-3">
        <button onClick={() => setOpen(o => !o)}
          className="text-xs text-[#5a5a7a] hover:text-[#c0c0e0] flex items-center gap-1">
          {open ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          ТЗ
        </button>
        {job.status !== 'done' && (
          <>
            <button onClick={() => onRetry(job)}
              className="text-xs text-[#5a5a7a] hover:text-violet-300 flex items-center gap-1">
              <RotateCcw className="w-3 h-3" /> вернуть в очередь
            </button>
            <button onClick={() => onCancel(job)}
              className="text-xs text-[#5a5a7a] hover:text-red-400 flex items-center gap-1">
              <X className="w-3 h-3" /> отменить
            </button>
          </>
        )}
      </div>

      {open && (
        <pre className="text-[11px] text-[#8a8ab0] whitespace-pre-wrap mt-2 bg-[#09091a] rounded-lg p-3 overflow-x-auto">
          {JSON.stringify(brief, null, 2)}
        </pre>
      )}
    </div>
  )
}

export default function Production() {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = async () => {
    setBusy(true)
    try {
      const { data } = await production.jobs()
      setData(data)
    } finally { setBusy(false) }
  }
  useEffect(() => { load() }, [])

  const setProducer = async (value) => {
    await production.setProducer(value)
    load()
  }

  if (!data) {
    return <div className="text-[#5a5a7a] text-sm flex items-center gap-2">
      <Loader className="w-4 h-4 animate-spin" /> Загрузка…
    </div>
  }

  const items = data.items || []

  return (
    <div className="space-y-4">
      <div className="bg-[#0d0d1c] border border-[#1c1c30] rounded-xl p-4">
        <div className="flex items-center gap-2 mb-2">
          <Clapperboard className="w-4 h-4 text-violet-400" />
          <span className="font-medium text-sm">Кто делает видео</span>
          <button onClick={load} disabled={busy}
            className="ml-auto text-[#5a5a7a] hover:text-violet-300 disabled:opacity-40">
            <RefreshCw className={`w-4 h-4 ${busy ? 'animate-spin' : ''}`} />
          </button>
        </div>
        <div className="flex gap-2">
          {[['server', 'Сервер сам'], ['claude', 'Внешний исполнитель']].map(([v, label]) => (
            <button key={v} onClick={() => setProducer(v)}
              className={`px-3 py-1.5 rounded-lg text-xs border transition ${
                data.producer === v
                  ? 'border-violet-500/40 bg-violet-600/15 text-violet-300'
                  : 'border-[#1c1c30] text-[#5a5a7a] hover:text-[#c0c0e0]'}`}>
              {label}
            </button>
          ))}
        </div>
        <p className="text-[11px] text-[#5a5a7a] mt-2">
          {data.producer === 'claude'
            ? 'Конвейер готовит ТЗ и ждёт готовый ролик от исполнителя. Дальше — монтаж и согласование.'
            : 'Сервер генерирует видео сам через подключённые сервисы.'}
        </p>
      </div>

      {items.length === 0 && (
        <div className="text-sm text-[#5a5a7a] bg-[#0d0d1c] border border-[#1c1c30] rounded-xl p-5">
          Заданий пока нет. Они появятся, когда конвейер подготовит ТЗ на ролик.
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-3">
        {items.map(job => (
          <Job key={job.id} job={job}
            onRetry={async (j) => { await production.retry(j.id); load() }}
            onCancel={async (j) => { await production.cancel(j.id); load() }} />
        ))}
      </div>
    </div>
  )
}
