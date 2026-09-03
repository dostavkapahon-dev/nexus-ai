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

// Подключение к Клоду одним действием: ключ проверяется живым вызовом, и только
// после этого сохраняется. Иначе неверный ключ обнаружится при первой генерации,
// а выглядеть это будет как «система не работает».
function ClaudeCard({ onDone }) {
  const [key, setKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)

  const connect = async () => {
    setBusy(true); setMsg(null)
    try {
      const { data } = await connections.connectClaude(key)
      setMsg(data)
      if (data.ok) { setKey(''); onDone() }
    } finally { setBusy(false) }
  }

  return (
    <div className="bg-[#0d0d1c] border border-violet-500/25 rounded-xl p-4 space-y-2">
      <div className="text-sm font-medium">🧠 Подключить Клода — один раз</div>
      <p className="text-xs text-[#5a5a7a]">
        После подключения система обращается к Клоду сама: пересылать задания
        вручную больше не нужно. Ключ берётся в console.anthropic.com.
      </p>
      <div className="flex gap-2">
        <input type="password" value={key} onChange={e => setKey(e.target.value)}
          placeholder="sk-ant-…"
          className="flex-1 bg-[#09091a] border border-[#1c1c30] rounded-lg px-3 py-2 text-xs
                     text-[#c0c0e0] placeholder-[#4a4a68] focus:outline-none focus:border-violet-500/40" />
        <button onClick={connect} disabled={busy || !key}
          className="px-3 py-2 rounded-lg text-xs bg-violet-600/20 border border-violet-500/30
                     text-violet-200 hover:bg-violet-600/30 disabled:opacity-40">
          {busy ? 'Проверяю…' : 'Проверить и подключить'}
        </button>
      </div>
      {msg && (
        <div className={`text-xs ${msg.ok ? 'text-emerald-300' : 'text-red-300'}`}>
          {msg.message || msg.error}
        </div>
      )}
    </div>
  )
}

// Копия доступов одним файлом. Пока в Render не подключена постоянная база,
// это разница между «восстановил за минуту» и «ввожу пятнадцать полей заново».
function BackupCard() {
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)

  const download = async () => {
    setBusy(true); setMsg(null)
    try {
      const { data } = await connections.backup(password)
      if (!data.ok) { setMsg({ ok: false, text: data.error }); return }
      const blob = new Blob([JSON.stringify(data.file)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `nexus-keys-${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
      setMsg({ ok: true, text: `Сохранено ключей: ${data.count}. Храните файл и пароль отдельно.` })
    } finally { setBusy(false) }
  }

  const restore = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setBusy(true); setMsg(null)
    try {
      const parsed = JSON.parse(await file.text())
      const { data } = await connections.restore(parsed, password)
      setMsg({ ok: data.ok, text: data.ok ? `Восстановлено ключей: ${data.restored}` : data.error })
      if (data.ok) window.location.reload()
    } catch {
      setMsg({ ok: false, text: 'Не удалось прочитать файл копии.' })
    } finally { setBusy(false); e.target.value = '' }
  }

  return (
    <div className="bg-[#0d0d1c] border border-[#1c1c30] rounded-xl p-4 space-y-2">
      <div className="text-sm font-medium">💾 Копия ключей одним файлом</div>
      <p className="text-xs text-[#5a5a7a]">
        Файл шифруется отдельным паролем — не тем, что на сервере. Потеряете
        пароль — копию открыть нельзя, так и задумано.
      </p>
      <input type="password" value={password} onChange={e => setPassword(e.target.value)}
        placeholder="пароль копии (от 8 символов)"
        className="w-full bg-[#09091a] border border-[#1c1c30] rounded-lg px-3 py-2 text-xs
                   text-[#c0c0e0] placeholder-[#4a4a68] focus:outline-none focus:border-violet-500/40" />
      <div className="flex gap-2 items-center">
        <button onClick={download} disabled={busy || password.length < 8}
          className="px-3 py-2 rounded-lg text-xs border border-[#1c1c30] text-[#c0c0e0]
                     hover:border-violet-500/40 disabled:opacity-40">
          Скачать копию
        </button>
        <label className={`px-3 py-2 rounded-lg text-xs border border-[#1c1c30] cursor-pointer
                          hover:border-violet-500/40 ${password.length < 8 ? 'opacity-40 pointer-events-none' : ''}`}>
          Восстановить из файла
          <input type="file" accept="application/json" onChange={restore} className="hidden" />
        </label>
      </div>
      {msg && (
        <div className={`text-xs ${msg.ok ? 'text-emerald-300' : 'text-red-300'}`}>{msg.text}</div>
      )}
    </div>
  )
}

export default function Credentials() {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState('')
  const [note, setNote] = useState('')
  const [persistence, setPersistence] = useState(null)

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

  const verify = async () => {
    setBusy('verify')
    try {
      const { data } = await connections.verify()
      setPersistence(data)
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

      {/* Главный вопрос владельца — «почему я ввожу ключи каждый раз». Ответ
          должен стоять здесь же, рядом с полями ввода. */}
      <div className="bg-[#0d0d1c] border border-[#1c1c30] rounded-xl p-4 space-y-2">
        <div className="text-sm font-medium">🗄 Сохранность ключей</div>
        <button onClick={verify} disabled={busy === 'verify'}
          className="px-3 py-2 rounded-lg text-xs border border-[#1c1c30] text-[#c0c0e0]
                     hover:border-violet-500/40 disabled:opacity-40">
          {busy === 'verify' ? 'Проверяю…' : 'Проверить сохранность'}
        </button>
        {persistence && (
          <div className={`text-xs ${persistence.persistent ? 'text-emerald-300' : 'text-amber-300'}`}>
            {persistence.verdict}
          </div>
        )}
        {persistence && !persistence.persistent && (
          <ol className="text-[11px] text-[#8a8ab0] list-decimal ml-4 space-y-1">
            <li>Заведите бесплатную базу на supabase.com и скопируйте строку подключения.</li>
            <li>Render → ваш сервис → Environment → добавьте <code>DATABASE_URL</code>.</li>
            <li>Там же задайте <code>NEXUS_SECRET_KEY</code> — любую длинную строку, и не теряйте её.</li>
            <li>Save changes: сервис перезапустится, и ключи перестанут пропадать.</li>
          </ol>
        )}
      </div>

      <ClaudeCard onDone={load} />
      <BackupCard />

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
