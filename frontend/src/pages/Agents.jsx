import React, { useEffect, useState } from 'react'
import { Bot, Loader, RefreshCw, Play, CheckCircle, AlertTriangle } from 'lucide-react'
import { Link } from 'react-router-dom'
import { agents as agentsApi } from '../lib/api'

// Роли агентов по ТЗ. Показываем не только «кто есть», но и чего конкретно
// не хватает роли, чтобы работать: «агент не работает» без причины —
// бесполезная информация.

const fmt = (iso) => (iso ? iso.slice(0, 16).replace('T', ' ') : 'ни разу')

function RunBox({ agentKey, onDone }) {
  const [task, setTask] = useState('')
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState(null)

  const run = async () => {
    if (!task.trim()) return
    setBusy(true); setRes(null)
    try {
      const { data } = await agentsApi.run(agentKey, task.trim())
      setRes(data)
      onDone?.()
    } catch (e) {
      setRes({ ok: false, error: e.response?.data?.detail || e.message })
    } finally { setBusy(false) }
  }

  return (
    <div className="mt-3 space-y-2">
      <div className="flex gap-2">
        <input value={task} onChange={e => setTask(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && run()}
          placeholder="Что поручить этой роли"
          className="flex-1 bg-[#09091a] border border-[#1c1c30] rounded-lg px-3 py-1.5 text-xs outline-none focus:border-violet-500/50" />
        <button onClick={run} disabled={busy}
          className="px-3 py-1.5 rounded-lg bg-violet-600/20 border border-violet-500/30 text-violet-300 text-xs flex items-center gap-1.5 disabled:opacity-50">
          {busy ? <Loader className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
          Запустить
        </button>
      </div>
      {res && (
        <div className={`text-xs whitespace-pre-wrap ${res.ok ? 'text-[#c0c0e0]' : 'text-red-400'}`}>
          {res.ok ? (res.result?.text || res.result?.error || 'готово') : res.error}
          {res.task_id && <span className="text-[#5a5a7a]"> · {res.task_id}</span>}
        </div>
      )}
    </div>
  )
}

export default function Agents() {
  const [items, setItems] = useState(null)
  const [busy, setBusy] = useState(false)
  const [open, setOpen] = useState('')

  const load = async () => {
    setBusy(true)
    try {
      const { data } = await agentsApi.list()
      setItems(data.agents || [])
    } finally { setBusy(false) }
  }
  useEffect(() => { load() }, [])

  return (
    <div className="max-w-4xl space-y-5">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-fuchsia-500 to-violet-600 flex items-center justify-center">
          <Bot className="w-5 h-5 text-white" />
        </div>
        <div className="flex-1">
          <h1 className="text-xl font-bold">Агенты</h1>
          <p className="text-sm text-[#5a5a7a]">
            Все задачи проходят через дирижёра — агенты не управляют системой сами
          </p>
        </div>
        <button onClick={load} disabled={busy}
          className="text-[#5a5a7a] hover:text-violet-300 disabled:opacity-40">
          <RefreshCw className={`w-4 h-4 ${busy ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {!items && (
        <div className="text-[#5a5a7a] text-sm flex items-center gap-2">
          <Loader className="w-4 h-4 animate-spin" /> Загрузка…
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-3">
        {(items || []).map(a => (
          <div key={a.key}
            className={`rounded-xl border p-4 ${a.ready
              ? 'border-[#1c1c30] bg-[#0d0d1c]'
              : 'border-amber-500/25 bg-amber-500/5'}`}>
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium">{a.title}</span>
              {a.ready
                ? <span className="text-xs text-emerald-300 flex items-center gap-1">
                    <CheckCircle className="w-3 h-3" /> готов
                  </span>
                : <span className="text-xs text-amber-300 flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3" /> нет доступа
                  </span>}
            </div>
            <div className="text-xs text-[#5a5a7a] mt-1">{a.role}</div>
            <ul className="text-xs text-[#8a8ab0] mt-2 space-y-0.5">
              {a.does.map(d => <li key={d}>· {d}</li>)}
            </ul>

            {!a.ready && (
              <div className="text-xs text-amber-300/90 mt-2">
                нужен ключ: {a.missing.join(', ')} —{' '}
                <Link to="/connections?tab=keys" className="underline">подключить</Link>
              </div>
            )}

            <div className="text-[11px] text-[#5a5a7a] mt-2">
              вызовов: {a.calls ?? 0} · последний запуск: {fmt(a.last_run)}
            </div>

            {a.ready && a.key !== 'director' && (
              open === a.key
                ? <RunBox agentKey={a.key} onDone={load} />
                : <button onClick={() => setOpen(a.key)}
                    className="mt-3 text-xs text-violet-300 hover:text-violet-200">
                    Поставить задачу
                  </button>
            )}
          </div>
        ))}
      </div>

      <p className="text-xs text-[#5a5a7a]">
        Промпты настраиваются в{' '}
        <Link to="/settings?tab=prompts" className="text-violet-400">Настройках</Link>,
        рамка работы агента — в{' '}
        <Link to="/settings?tab=agent" className="text-violet-400">профиле Главного агента</Link>.
      </p>
    </div>
  )
}
