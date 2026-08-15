import React, { useEffect, useState } from 'react'
import { KeyRound, CheckCircle, XCircle, Loader, Trash2, RefreshCw, ShieldCheck, ShieldAlert } from 'lucide-react'
import { Link } from 'react-router-dom'
import { connections } from '../lib/api'

// Раздел «API / Credentials» по ТЗ: каждое подключение отдельной строкой, со
// статусом, датой подключения и действиями — проверить, переподключить, удалить.
// Список полей приходит с сервера, поэтому он не расходится с тем, что система
// реально умеет читать.

const fmt = (iso) => (iso ? iso.slice(0, 16).replace('T', ' ') : '—')

function Row({ item, onRecheck, onDelete, busy }) {
  const status = item.unreadable
    ? { cls: 'text-amber-300', label: 'зашифровано, нет ключа' }
    : item.connected
      ? { cls: 'text-emerald-300', label: 'подключено' }
      : { cls: 'text-[#5a5a7a]', label: 'не подключено' }

  return (
    <div className="flex items-center gap-3 px-3 py-2.5 border-b border-[#15152a] last:border-0">
      <div className="flex-1 min-w-0">
        <div className="text-sm">{item.label}</div>
        <div className="text-xs text-[#5a5a7a] font-mono truncate">
          {item.masked || item.key}
          {item.source === 'env' && ' · из переменных окружения'}
        </div>
      </div>
      <div className="hidden md:block text-xs text-[#5a5a7a] w-32">
        {item.connected ? fmt(item.connected_at) : ''}
      </div>
      <div className={`text-xs w-40 ${status.cls}`}>
        {status.label}
        {item.last_check_at && (
          <div className="text-[10px] text-[#5a5a7a]">
            проверка: {item.last_check_ok ? 'ок' : (item.last_check_error || 'ошибка')}
          </div>
        )}
      </div>
      <div className="flex gap-1.5">
        <button title="Проверить соединение" disabled={busy || !item.connected}
          onClick={() => onRecheck(item)}
          className="text-[#5a5a7a] hover:text-violet-300 disabled:opacity-30">
          <RefreshCw className={`w-4 h-4 ${busy === item.key ? 'animate-spin' : ''}`} />
        </button>
        <button title="Удалить" disabled={!item.connected}
          onClick={() => onDelete(item)}
          className="text-[#5a5a7a] hover:text-red-400 disabled:opacity-30">
          <Trash2 className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}

export default function Credentials() {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState('')
  const [note, setNote] = useState('')

  const load = async () => {
    const { data } = await connections.status()
    setData(data)
  }
  useEffect(() => { load() }, [])

  const recheck = async (item) => {
    setBusy(item.key)
    try {
      const { data } = await connections.recheck(item.key)
      setNote(`${item.label}: ${data.message || (data.ok ? 'ок' : 'не прошло')}`)
      await load()
    } finally { setBusy('') }
  }

  const remove = async (item) => {
    if (!window.confirm(`Удалить «${item.label}»? Доступ будет стёрт с сервера.`)) return
    const { data } = await connections.remove(item.key)
    if (data?.note) setNote(data.note)
    await load()
  }

  if (!data) {
    return <div className="text-[#5a5a7a] text-sm flex items-center gap-2">
      <Loader className="w-4 h-4 animate-spin" /> Загрузка…
    </div>
  }

  const groups = Object.entries(data.groups)
  const byGroup = (g) => data.items.filter(i => i.group === g)

  return (
    <div className="max-w-4xl space-y-5">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center">
          <KeyRound className="w-5 h-5 text-white" />
        </div>
        <div>
          <h1 className="text-xl font-bold">API / Credentials</h1>
          <p className="text-sm text-[#5a5a7a]">
            Подключено: {data.connected} из {data.items.length}
          </p>
        </div>
      </div>

      {/* Про шифрование говорим честно: включено или нет — это разные ситуации. */}
      <div className={`rounded-xl p-4 text-sm flex gap-2 items-start ${
        data.storage.enabled
          ? 'bg-emerald-500/8 text-emerald-300'
          : 'bg-amber-500/8 text-amber-300'}`}>
        {data.storage.enabled
          ? <ShieldCheck className="w-4 h-4 mt-0.5 flex-shrink-0" />
          : <ShieldAlert className="w-4 h-4 mt-0.5 flex-shrink-0" />}
        <div>
          {data.storage.enabled
            ? `Ключи хранятся в базе в зашифрованном виде (защищено: ${data.storage.encrypted}).`
            : data.storage.hint}
        </div>
      </div>

      {note && (
        <div className="bg-[#0d0d1c] border border-[#1c1c30] rounded-xl p-3 text-sm text-[#c0c0e0]">
          {note}
        </div>
      )}

      {groups.map(([group, title]) => {
        const items = byGroup(group)
        if (!items.length) return null
        return (
          <div key={group} className="bg-[#0d0d1c] border border-[#1c1c30] rounded-xl overflow-hidden">
            <div className="px-3 py-2 text-xs uppercase tracking-wider text-[#5a5a7a] border-b border-[#15152a]">
              {title}
            </div>
            {items.map(i => (
              <Row key={i.key} item={i} busy={busy} onRecheck={recheck} onDelete={remove} />
            ))}
          </div>
        )
      })}

      <p className="text-xs text-[#5a5a7a]">
        Добавить или изменить ключ — в разделе{' '}
        <Link to="/connections?tab=keys" className="text-violet-400">Подключения → Ключи и доступы</Link>.
        Секретные значения никогда не показываются целиком.
      </p>
    </div>
  )
}
