import React, { useEffect, useState } from 'react'
import { Clapperboard, Loader, RefreshCw, RotateCcw, X, ChevronDown, ChevronUp, Copy, Check, Upload } from 'lucide-react'
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

const NEXT_NOTE = {
  awaiting_approval: 'Ролик ушёл вам в Telegram на согласование.',
  no_telegram: 'Ролик принят, но согласовать некому — Telegram не подключён.',
  delivered: 'Ответ доставлен тому, кто спрашивал.',
  empty: 'Ответ пустой — доставлять нечего.',
}

// Форма приёма готового медиа. Ссылки приносит внешний исполнитель, сервер
// сам их не достанет — без этой формы задание висит в очереди навсегда.
function Handover({ job, onDone }) {
  const isText = job.kind === 'ai_task'
  const [form, setForm] = useState(
    isText ? { text: '', note: '' }
           : { video_url: '', image_url: '', audio_url: '', note: '' })
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))

  const send = async () => {
    setErr(''); setBusy(true)
    try {
      const { data } = await production.result(job.id, form)
      if (!data.ok) { setErr(data.error || 'сервер не принял результат'); return }
      onDone(NEXT_NOTE[data.next?.status] || data.next?.note || 'Результат принят.')
    } catch (e) {
      setErr(e.response?.data?.detail || e.message)
    } finally { setBusy(false) }
  }

  const field = (k, ph) => (
    <input value={form[k]} onChange={set(k)} placeholder={ph}
      className="w-full bg-[#09091a] border border-[#1c1c30] rounded-lg px-3 py-2 text-xs
                 text-[#c0c0e0] placeholder-[#4a4a68] focus:outline-none focus:border-violet-500/40" />
  )

  return (
    <div className="mt-3 space-y-2 bg-[#09091a] rounded-lg p-3">
      {isText ? (
        <textarea value={form.text} onChange={set('text')} rows={6}
          placeholder="ответ Клода — придёт туда, откуда пришёл вопрос"
          className="w-full bg-[#09091a] border border-[#1c1c30] rounded-lg px-3 py-2 text-xs
                     text-[#c0c0e0] placeholder-[#4a4a68] focus:outline-none focus:border-violet-500/40" />
      ) : (
        <>
          {field('video_url', 'ссылка на готовый ролик (mp4)')}
          {field('image_url', 'ссылка на обложку или фото')}
          {field('audio_url', 'ссылка на озвучку')}
        </>
      )}
      {field('note', 'заметка: чем и как сделано')}
      {err && <div className="text-xs text-red-300">{err}</div>}
      <button onClick={send} disabled={busy}
        className="px-3 py-1.5 rounded-lg text-xs bg-violet-600/20 border border-violet-500/30
                   text-violet-200 hover:bg-violet-600/30 disabled:opacity-40">
        {busy ? 'Отправляю…' : 'Отправить в конвейер'}
      </button>
      <p className="text-[11px] text-[#5a5a7a]">
        {isText
          ? 'Ответ уйдёт в тот чат, откуда пришёл вопрос, и в ленту на сайте.'
          : 'Дальше система смонтирует ролик и пришлёт вам на согласование.'}
      </p>
    </div>
  )
}

function Job({ job, onRetry, onCancel, onDone }) {
  const [open, setOpen] = useState(false)
  const [give, setGive] = useState(false)
  const [copied, setCopied] = useState(false)
  const st = STATUS[job.status] || STATUS.queued
  const brief = job.brief || {}

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(job.brief_text || JSON.stringify(brief, null, 2))
      setCopied(true); setTimeout(() => setCopied(false), 2000)
    } catch { setOpen(true) }   // буфер недоступен — просто раскрываем ТЗ
  }

  return (
    <div className={`rounded-xl border p-4 ${st.cls}`}>
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-medium">
          {job.kind === 'ai_task'
            ? `🧠 Вопрос Клоду: ${(brief.prompt || '').slice(0, 60)}`
            : brief.theme || job.kind}
        </span>
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
        <button onClick={copy}
          className="text-xs text-[#5a5a7a] hover:text-cyan-300 flex items-center gap-1">
          {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
          {copied ? 'скопировано' : 'копировать ТЗ'}
        </button>
        {job.status !== 'done' && job.status !== 'cancelled' && (
          <button onClick={() => setGive(g => !g)}
            className="text-xs text-[#5a5a7a] hover:text-emerald-300 flex items-center gap-1">
            <Upload className="w-3 h-3" /> вставить готовое
          </button>
        )}
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

      {give && <Handover job={job} onDone={onDone} />}

      {open && (
        <pre className="text-[11px] text-[#8a8ab0] whitespace-pre-wrap mt-2 bg-[#09091a] rounded-lg p-3 overflow-x-auto">
          {job.brief_text || JSON.stringify(brief, null, 2)}
        </pre>
      )}
    </div>
  )
}

export default function Production() {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')

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

      {note && (
        <div className="text-sm text-emerald-300 bg-emerald-500/5 border border-emerald-500/25 rounded-xl p-3">
          {note}
        </div>
      )}

      {items.length === 0 && (
        <div className="text-sm text-[#5a5a7a] bg-[#0d0d1c] border border-[#1c1c30] rounded-xl p-5">
          Заданий пока нет. Они появятся, когда конвейер подготовит ТЗ на ролик.
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-3">
        {items.map(job => (
          <Job key={job.id} job={job}
            onRetry={async (j) => { await production.retry(j.id); load() }}
            onCancel={async (j) => { await production.cancel(j.id); load() }}
            onDone={(msg) => { setNote(msg); load() }} />
        ))}
      </div>
    </div>
  )
}
