import React, { useState, useEffect } from 'react'
import { Plug, Save, CheckCircle, XCircle, Loader, Eye, EyeOff } from 'lucide-react'
import { connections as connectionsApi } from '../lib/api'

const FIELDS = [
  { key: 'anthropic_api_key', label: 'Anthropic API Key', placeholder: 'sk-ant-...', provider: 'Claude' },
  { key: 'openai_api_key', label: 'OpenAI API Key', placeholder: 'sk-...', provider: 'GPT-4o' },
  { key: 'gemini_api_key', label: 'Google Gemini API Key', placeholder: 'AIza...', provider: 'Gemini' },
  { key: 'telegram_bot_token', label: 'Telegram Bot Token', placeholder: '123456:ABC...', provider: 'Telegram' },
  { key: 'telegram_chat_id', label: 'Telegram Chat ID', placeholder: '-100...', provider: 'Telegram' },
  { key: 'youtube_api_key', label: 'YouTube Data API Key', placeholder: 'AIza...', provider: 'YouTube' },
]

function Field({ field, value, onChange, testResult }) {
  const [show, setShow] = useState(false)
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <label className="text-xs text-nexus-muted">{field.label}</label>
        <span className="text-xs px-2 py-0.5 rounded-full bg-nexus-card text-nexus-muted border border-nexus-border">{field.provider}</span>
      </div>
      <div className="relative">
        <input type={show ? 'text' : 'password'} value={value || ''} onChange={e => onChange(field.key, e.target.value)}
          placeholder={field.placeholder}
          className="w-full bg-nexus-card border border-nexus-border rounded-lg px-3 py-2 pr-10 text-sm text-nexus-text placeholder-nexus-muted focus:border-purple-500 outline-none font-mono" />
        <button type="button" onClick={() => setShow(s => !s)} className="absolute right-3 top-1/2 -translate-y-1/2 text-nexus-muted hover:text-nexus-text">
          {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
        </button>
      </div>
      {testResult && (
        <div className={`flex items-center gap-1 text-xs ${testResult.ok ? 'text-green-400' : 'text-red-400'}`}>
          {testResult.ok ? <CheckCircle className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
          {testResult.message}
        </div>
      )}
    </div>
  )
}

export default function Connections() {
  const [values, setValues] = useState({})
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResults, setTestResults] = useState({})
  const [saved, setSaved] = useState(false)

  useEffect(() => { connectionsApi.list().then(r => setValues(r.data || {})) }, [])

  const onChange = (key, val) => setValues(p => ({ ...p, [key]: val }))

  const save = async () => {
    setSaving(true)
    await connectionsApi.save(values)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
    setSaving(false)
  }

  const testAll = async () => {
    setTesting(true)
    try {
      const r = await connectionsApi.test(values)
      setTestResults(r.data || {})
    } catch { setTestResults({}) }
    setTesting(false)
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><Plug className="text-purple-400" /> Подключения</h1>
          <p className="text-nexus-muted text-sm mt-1">API ключи для AI провайдеров</p>
        </div>
        <div className="flex gap-2">
          <button onClick={testAll} disabled={testing}
            className="px-4 py-2 rounded-lg border border-nexus-border text-nexus-muted text-sm hover:text-nexus-text transition flex items-center gap-2">
            {testing ? <Loader className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />} Проверить
          </button>
          <button onClick={save} disabled={saving}
            className="px-4 py-2 rounded-lg bg-purple-600 text-white text-sm hover:bg-purple-500 transition flex items-center gap-2 disabled:opacity-50">
            {saving ? <Loader className="w-4 h-4 animate-spin" /> : saved ? <CheckCircle className="w-4 h-4" /> : <Save className="w-4 h-4" />}
            {saved ? 'Сохранено!' : 'Сохранить'}
          </button>
        </div>
      </div>

      <div className="glass rounded-xl p-5 space-y-5">
        {FIELDS.map(field => (
          <Field key={field.key} field={field} value={values[field.key]} onChange={onChange} testResult={testResults[field.key]} />
        ))}
      </div>

      <div className="mt-4 glass rounded-xl p-4">
        <h3 className="text-xs font-semibold text-purple-300 uppercase tracking-wider mb-3">Как получить ключи</h3>
        <div className="space-y-1.5 text-xs text-nexus-muted">
          <p>• <span className="text-nexus-text">Anthropic:</span> console.anthropic.com → API Keys</p>
          <p>• <span className="text-nexus-text">OpenAI:</span> platform.openai.com → API Keys</p>
          <p>• <span className="text-nexus-text">Gemini:</span> aistudio.google.com → Get API Key</p>
          <p>• <span className="text-nexus-text">Telegram Bot:</span> @BotFather → /newbot</p>
          <p>• <span className="text-nexus-text">Telegram Chat ID:</span> @userinfobot → перешлите сообщение</p>
        </div>
      </div>
    </div>
  )
}
