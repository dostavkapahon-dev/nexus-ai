import React, { useEffect, useState } from 'react'
import { Bot, Loader, RefreshCw } from 'lucide-react'
import { Link } from 'react-router-dom'
import { system } from '../lib/api'

// Список агентов и их состояние по журналу вызовов. Роли из ТЗ (Research,
// Instagram, Publisher и т.д.) появятся здесь, когда будет реестр агентов;
// пока показываем то, что действительно существует и работает, — придумывать
// карточки под несуществующие роли значило бы врать про возможности системы.
const LABELS = {
  niche_analyst: 'Аналитик ниши',
  viral_hunter: 'Охотник за вирусами',
  strategist: 'Стратег',
  copywriter: 'Копирайтер',
  reviewer: 'Ревьюер',
  voice_adapter: 'Голос бренда',
  visual_creator: 'Визуал',
  adapter: 'Адаптер площадок',
  trend_analyst: 'Тренды',
  funnel_agent: 'Воронка',
  reporter: 'Отчёты',
}

const STATUS = {
  online: { label: 'Работает', cls: 'text-emerald-300 bg-emerald-500/10 border-emerald-500/25' },
  degraded: { label: 'С ошибками', cls: 'text-amber-300 bg-amber-500/10 border-amber-500/25' },
  silent: { label: 'Молчит', cls: 'text-[#7a7a9a] bg-[#12122a] border-[#1c1c30]' },
}

const fmt = (iso) => (iso ? iso.slice(0, 16).replace('T', ' ') : 'ни разу')

export default function Agents() {
  const [items, setItems] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = async () => {
    setBusy(true)
    try {
      const { data } = await system.agents(24 * 7)
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
          <p className="text-sm text-[#5a5a7a]">Кто работает, с каким успехом и когда в последний раз</p>
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

      {items && items.length === 0 && (
        <div className="bg-[#0d0d1c] border border-[#1c1c30] rounded-xl p-5 text-sm text-[#5a5a7a]">
          Агенты ещё не запускались. Поставьте задачу в{' '}
          <Link to="/hq" className="text-violet-400">Командном центре</Link>.
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-3">
        {(items || []).map(a => {
          const st = STATUS[a.status] || STATUS.silent
          return (
            <div key={a.agent} className={`rounded-xl border p-4 ${st.cls}`}>
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium">{LABELS[a.agent] || a.agent}</span>
                <span className="text-xs">{st.label}</span>
              </div>
              <div className="text-xs mt-2 space-y-0.5 opacity-80">
                <div>вызовов за неделю: {a.calls ?? 0}</div>
                <div>успешно: {a.success_rate ?? 0}%</div>
                <div>последний запуск: {fmt(a.last_run)}</div>
              </div>
            </div>
          )
        })}
      </div>

      <p className="text-xs text-[#5a5a7a]">
        Промпты агентов настраиваются в{' '}
        <Link to="/settings?tab=prompts" className="text-violet-400">Настройках</Link>.
      </p>
    </div>
  )
}
