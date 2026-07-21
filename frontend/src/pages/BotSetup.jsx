import React, { useState, useEffect } from 'react'
import { Bot, Send, Loader, CheckCircle, XCircle, RefreshCw, Save, MessageSquare, Users, KeyRound } from 'lucide-react'
import { connections, bot } from '../lib/api'

const COMMANDS = [
  ['/menu', 'пульт с кнопками'],
  ['/status', 'статус системы'],
  ['/factory [тема]', 'весь цикл: анализ→генерация→превью'],
  ['/factory [тема] post', 'то же + публикация'],
  ['/create', 'создать контент из плана'],
  ['/publish', 'опубликовать очередь'],
  ['/plan', 'контент-план на неделю'],
  ['/trend', 'тренды прямо сейчас'],
  ['/pause  /resume', 'пауза / возобновить'],
  ['/config', 'настройки'],
]

function Field({ label, icon: Icon, value, onChange, placeholder, hint }) {
  return (
    <div className="mb-4">
      <label className="flex items-center gap-2 text-sm text-[#c0c0e0] mb-1.5">
        {Icon && <Icon className="w-4 h-4 text-violet-400" />}{label}
      </label>
      <input value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
        className="w-full bg-[#0d0d1a] border border-[#1c1c30] rounded-lg px-3 py-2 text-sm text-[#e8e8f5] placeholder-[#5a5a7a] focus:border-violet-500 outline-none" />
      {hint && <div className="text-[11px] text-[#5a5a7a] mt-1">{hint}</div>}
    </div>
  )
}

export default function BotSetup() {
  const [token, setToken] = useState('')
  const [admin, setAdmin] = useState('')
  const [group, setGroup] = useState('')
  const [status, setStatus] = useState(null)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [msg, setMsg] = useState(null)

  const loadStatus = async () => {
    try {
      const r = await bot.status()
      setStatus(r.data)
      if (r.data.post_chat_id) setGroup(r.data.post_chat_id)
    } catch (e) { /* ignore */ }
  }
  useEffect(() => { loadStatus() }, [])

  const save = async () => {
    setSaving(true); setMsg(null)
    try {
      const data = {}
      if (token) data.telegram_bot_token = token
      if (admin) data.telegram_chat_id = admin
      if (group) data.telegram_post_chat_id = group
      await connections.save(data)
      setMsg({ ok: true, text: 'Сохранено ✓' })
      setToken('')
      await loadStatus()
    } catch (e) {
      setMsg({ ok: false, text: e.response?.data?.detail || e.message })
    }
    setSaving(false)
  }

  const testGroup = async () => {
    setTesting(true); setMsg(null)
    try {
      const r = await bot.testPost(group || null)
      setMsg({ ok: r.data.ok, text: r.data.message })
    } catch (e) {
      setMsg({ ok: false, text: e.response?.data?.detail || e.message })
    }
    setTesting(false)
  }

  return (
    <div className="max-w-3xl">
      <div className="flex items-center gap-3 mb-1">
        <Bot className="w-6 h-6 text-violet-400" />
        <h1 className="text-xl font-semibold text-[#e8e8f5]">Настройка Telegram-бота</h1>
        <button onClick={loadStatus} className="ml-auto text-[#5a5a7a] hover:text-violet-300">
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>
      <p className="text-sm text-[#5a5a7a] mb-5">
        Управляй системой из Telegram кнопками и командами. Посты идут в отдельную группу.
      </p>

      {/* Статус */}
      <div className="card p-4 mb-5 border border-[#1c1c30] flex flex-wrap gap-4 text-sm">
        <span className="flex items-center gap-1.5">
          {status?.ok ? <CheckCircle className="w-4 h-4 text-green-400" /> : <XCircle className="w-4 h-4 text-red-400" />}
          Бот: {status?.username ? '@' + status.username : (status?.has_token ? 'токен есть' : 'не подключён')}
        </span>
        <span className="flex items-center gap-1.5">
          {status?.admin_chat_id ? <CheckCircle className="w-4 h-4 text-green-400" /> : <XCircle className="w-4 h-4 text-[#5a5a7a]" />}
          Админ-чат
        </span>
        <span className="flex items-center gap-1.5">
          {status?.post_chat_id ? <CheckCircle className="w-4 h-4 text-green-400" /> : <XCircle className="w-4 h-4 text-[#5a5a7a]" />}
          Группа постов
        </span>
      </div>

      <div className="card p-5 mb-5 border border-[#1c1c30]">
        <Field label="Bot Token" icon={KeyRound} value={token} onChange={setToken}
          placeholder={status?.has_token ? '•••• уже сохранён, введите для замены' : '123456789:ABCdef...'}
          hint="Создайте бота у @BotFather → /newbot → скопируйте токен" />
        <Field label="Admin Chat ID (управление)" icon={MessageSquare} value={admin} onChange={setAdmin}
          placeholder="ваш личный chat_id, напр. 123456789"
          hint="Ваш ID: напишите боту @userinfobot. Только с этого чата принимаются команды." />
        <Field label="Group / Channel ID (посты)" icon={Users} value={group} onChange={setGroup}
          placeholder="-1001234567890"
          hint="Добавьте бота в группу админом. ID группы: перешлите сообщение из группы боту @userinfobot (начинается с -100)." />

        <div className="flex gap-2 mt-2">
          <button onClick={save} disabled={saving}
            className="flex items-center gap-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium transition">
            {saving ? <Loader className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Сохранить
          </button>
          <button onClick={testGroup} disabled={testing}
            className="flex items-center gap-2 bg-[#1a1a2e] hover:bg-[#22223a] text-[#c0c0e0] px-4 py-2 rounded-lg text-sm transition">
            {testing ? <Loader className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />} Тест в группу
          </button>
        </div>
        {msg && (
          <div className={`mt-3 text-sm ${msg.ok ? 'text-green-400' : 'text-red-400'}`}>{msg.text}</div>
        )}
      </div>

      {/* Команды */}
      <div className="card p-5 border border-[#1c1c30]">
        <div className="text-sm font-medium text-[#c0c0e0] mb-3">Команды бота (или кнопки после /menu)</div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1.5">
          {COMMANDS.map(([c, d]) => (
            <div key={c} className="flex items-baseline gap-2 text-sm">
              <code className="text-violet-300">{c}</code>
              <span className="text-[#5a5a7a] text-[12px]">— {d}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
