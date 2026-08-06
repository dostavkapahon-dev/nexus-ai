import React, { useState, useEffect } from 'react'
import {
  Brain, Save, Loader, Plus, Trash2, RefreshCw,
  Monitor, Globe, Eye, Share2, Send, Film,
} from 'lucide-react'
import { agent } from '../lib/api'

const KIND_LABELS = {
  hook: '🎣 Хук',
  format: '🎬 Формат',
  visual: '🎨 Визуал',
  audience: '👥 Аудитория',
  mistake: '⛔ Ошибка',
  rule: '📌 Правило',
}

const CAP_META = {
  pc_control: { icon: Monitor, label: 'Управление ПК', hint: 'запусти start_agent.bat' },
  web_search: { icon: Globe, label: 'Поиск в интернете', hint: '' },
  vision: { icon: Eye, label: 'Зрение (фото/видео)', hint: 'нужен ключ ИИ' },
  social: { icon: Share2, label: 'Соцсети', hint: 'нужен AYRSHARE_API_KEY' },
  telegram: { icon: Send, label: 'Telegram', hint: 'нужен токен бота' },
  montage: { icon: Film, label: 'Монтаж', hint: '' },
}

function Capabilities({ caps }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
      {Object.entries(CAP_META).map(([key, meta]) => {
        const on = caps?.[key]
        const Icon = meta.icon
        return (
          <div key={key}
            className={`rounded-lg border px-3 py-2.5 ${on
              ? 'border-green-500/30 bg-green-500/8'
              : 'border-[#1c1c30] bg-[#0d0d18]'}`}>
            <div className="flex items-center gap-2">
              <Icon className={`w-4 h-4 ${on ? 'text-green-400' : 'text-[#5a5a7a]'}`} />
              <span className={`text-sm ${on ? 'text-[#e8e8f5]' : 'text-[#5a5a7a]'}`}>
                {meta.label}
              </span>
            </div>
            {!on && meta.hint && (
              <div className="text-[10px] text-[#3a3a55] mt-1">{meta.hint}</div>
            )}
          </div>
        )
      })}
    </div>
  )
}

function SkillsPanel() {
  const [data, setData] = useState(null)
  const [kind, setKind] = useState('hook')
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [busy, setBusy] = useState(false)

  const load = async () => {
    try { setData((await agent.skills()).data) } catch { /* ignore */ }
  }
  useEffect(() => { load() }, [])

  const add = async () => {
    if (!title.trim()) return
    setBusy(true)
    try {
      await agent.addSkill({ kind, title, body })
      setTitle(''); setBody('')
      await load()
    } catch { /* ignore */ }
    setBusy(false)
  }

  const remove = async (id) => {
    await agent.deleteSkill(id)
    await load()
  }

  const skills = data?.skills || []

  return (
    <div className="card p-5 border border-[#1c1c30]">
      <div className="flex items-center gap-2 mb-1">
        <Brain className="w-5 h-5 text-violet-400" />
        <span className="font-semibold text-[#e8e8f5]">Память агента</span>
        <span className="text-[11px] text-[#5a5a7a]">
          {data?.stats?.total || 0} записей
        </span>
        <button onClick={load} className="ml-auto text-[#5a5a7a] hover:text-violet-300">
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>
      <p className="text-[12px] text-[#5a5a7a] mb-4">
        Что сработало и чего избегать. Агент подмешивает это в каждую задачу —
        не изобретает заново и не повторяет ошибок. Пополняется сам после
        разбора чужих роликов (<code className="text-violet-300">/viral</code>).
      </p>

      {/* Добавление */}
      <div className="bg-[#0d0d18] border border-[#1c1c30] rounded-lg p-3 mb-4">
        <div className="flex gap-2 mb-2">
          <select value={kind} onChange={e => setKind(e.target.value)}
            className="bg-[#0a0a14] border border-[#1c1c30] rounded-lg px-2 py-1.5 text-sm text-[#e8e8f5] outline-none">
            {Object.entries(KIND_LABELS).map(([k, l]) =>
              <option key={k} value={k}>{l}</option>)}
          </select>
          <input value={title} onChange={e => setTitle(e.target.value)}
            placeholder="Суть одной строкой"
            className="flex-1 bg-[#0a0a14] border border-[#1c1c30] rounded-lg px-3 py-1.5 text-sm text-[#e8e8f5] placeholder-[#5a5a7a] focus:border-violet-500 outline-none" />
        </div>
        <div className="flex gap-2">
          <input value={body} onChange={e => setBody(e.target.value)}
            placeholder="Деталь: как применять (необязательно)"
            className="flex-1 bg-[#0a0a14] border border-[#1c1c30] rounded-lg px-3 py-1.5 text-sm text-[#e8e8f5] placeholder-[#5a5a7a] focus:border-violet-500 outline-none" />
          <button onClick={add} disabled={busy || !title.trim()}
            className="flex items-center gap-1.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white px-3 py-1.5 rounded-lg text-sm transition">
            {busy ? <Loader className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
            Добавить
          </button>
        </div>
      </div>

      {/* Список */}
      <div className="space-y-1.5 max-h-80 overflow-y-auto">
        {skills.length === 0 && (
          <div className="text-[12px] text-[#3a3a55] py-4 text-center">
            Память пуста. Разбери чужие ролики командой{' '}
            <code className="text-violet-300">/viral ссылка</code> — агент
            запишет уроки сам.
          </div>
        )}
        {skills.map(s => (
          <div key={s.id}
            className="flex items-start gap-2 bg-[#0d0d18] border border-[#1c1c30] rounded-lg px-3 py-2">
            <span className="text-[11px] whitespace-nowrap mt-0.5">
              {KIND_LABELS[s.kind] || s.kind}
            </span>
            <div className="flex-1 min-w-0">
              <div className="text-sm text-[#e8e8f5]">{s.title}</div>
              {s.body && <div className="text-[11px] text-[#5a5a7a] mt-0.5">{s.body}</div>}
            </div>
            {s.score > 1 && (
              <span className="text-[10px] text-violet-300 mt-1">×{s.score}</span>
            )}
            <button onClick={() => remove(s.id)}
              className="text-[#3a3a55] hover:text-red-400 mt-0.5">
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function AgentSetup() {
  const [cfg, setCfg] = useState(null)
  const [voice, setVoice] = useState('')
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState(null)

  const load = async () => {
    try {
      const r = await agent.config()
      setCfg(r.data)
      setVoice(r.data.brand_voice || '')
    } catch { /* ignore */ }
  }
  useEffect(() => { load() }, [])

  const save = async () => {
    setSaving(true); setMsg(null)
    try {
      await agent.saveConfig({ brand_voice: voice })
      setMsg({ ok: true, text: 'Сохранено ✓' })
    } catch (e) {
      setMsg({ ok: false, text: e.message })
    }
    setSaving(false)
  }

  return (
    <div className="max-w-4xl">
      <div className="flex items-center gap-3 mb-1">
        <Brain className="w-6 h-6 text-violet-400" />
        <h1 className="text-xl font-semibold text-[#e8e8f5]">Настройка агента</h1>
      </div>
      <p className="text-sm text-[#5a5a7a] mb-5">
        Специфика бренда, возможности и память — всё в одном месте.
      </p>

      {/* Возможности */}
      <div className="card p-5 mb-5 border border-[#1c1c30]">
        <div className="text-sm font-medium text-[#c0c0e0] mb-3">Что агент умеет прямо сейчас</div>
        <Capabilities caps={cfg?.capabilities} />
      </div>

      {/* Голос бренда */}
      <div className="card p-5 mb-5 border border-[#1c1c30]">
        <div className="text-sm font-medium text-[#c0c0e0] mb-1">Голос бренда и специфика</div>
        <p className="text-[12px] text-[#5a5a7a] mb-3">
          Тон, стиль, о чём говорим и о чём нет. Это уходит в каждый текст и сценарий.
        </p>
        <textarea value={voice} onChange={e => setVoice(e.target.value)} rows={8}
          placeholder="Например: Тон уверенный, без канцелярита. Пишем короткими фразами. Всегда конкретика и цифры вместо общих слов. Цена от 15 000 ₸."
          className="w-full bg-[#0d0d1a] border border-[#1c1c30] rounded-lg px-3 py-2 text-sm text-[#e8e8f5] placeholder-[#5a5a7a] focus:border-violet-500 outline-none resize-y" />
        <div className="flex items-center gap-3 mt-3">
          <button onClick={save} disabled={saving}
            className="flex items-center gap-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium transition">
            {saving ? <Loader className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Сохранить
          </button>
          {msg && (
            <span className={`text-sm ${msg.ok ? 'text-green-400' : 'text-red-400'}`}>
              {msg.text}
            </span>
          )}
        </div>
      </div>

      <SkillsPanel />
    </div>
  )
}
