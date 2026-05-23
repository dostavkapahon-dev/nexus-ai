import React, { useState, useEffect } from 'react'
import { Cpu, Save, RotateCcw, Loader } from 'lucide-react'
import { prompts as promptsApi } from '../lib/api'

const AGENTS = [
  { key: 'niche_analyst', label: 'NicheAnalyst', desc: 'Анализ ниши и аудитории' },
  { key: 'viral_hunter', label: 'ViralHunter', desc: 'Поиск вирусного контента' },
  { key: 'strategist', label: 'Strategist', desc: 'Создание контент-плана' },
  { key: 'copywriter', label: 'Copywriter', desc: 'Написание постов' },
  { key: 'reviewer', label: 'Reviewer', desc: 'Проверка качества' },
  { key: 'visual_creator', label: 'VisualCreator', desc: 'Генерация изображений' },
  { key: 'voice_adapter', label: 'VoiceAdapter', desc: 'Адаптация под стиль' },
  { key: 'adapter', label: 'Adapter', desc: 'Адаптация по платформам' },
]

const MODELS = [
  { value: 'claude-sonnet-4-6',        label: 'Claude Sonnet 4.6',      group: 'Anthropic' },
  { value: 'claude-sonnet-4-20250514', label: 'Claude Sonnet 4',        group: 'Anthropic' },
  { value: 'claude-haiku-4-5-20251001',label: 'Claude Haiku 4.5',       group: 'Anthropic' },
  { value: 'gpt-4o',                   label: 'GPT-4o',                  group: 'OpenAI' },
  { value: 'gpt-4o-mini',              label: 'GPT-4o Mini',             group: 'OpenAI' },
  { value: 'gemini-1.5-pro',           label: 'Gemini 1.5 Pro',          group: 'Google' },
  { value: 'gemini-1.5-flash',         label: 'Gemini 1.5 Flash',        group: 'Google' },
  { value: 'sonar-reasoning-pro',      label: 'Perplexity Sonar Reasoning Pro', group: 'Perplexity' },
  { value: 'sonar-pro',                label: 'Perplexity Sonar Pro',    group: 'Perplexity' },
  { value: 'sonar',                    label: 'Perplexity Sonar',        group: 'Perplexity' },
  { value: 'deepseek-chat',            label: 'DeepSeek Chat',           group: 'DeepSeek' },
  { value: 'deepseek-reasoner',        label: 'DeepSeek Reasoner (R1)',  group: 'DeepSeek' },
]

export default function PromptStudio() {
  const [selected, setSelected] = useState('copywriter')
  const [allPrompts, setAllPrompts] = useState({})
  const [editing, setEditing] = useState(null)
  const [saving, setSaving] = useState(false)
  const [resetting, setResetting] = useState(false)

  useEffect(() => {
    promptsApi.list().then(r => {
      setAllPrompts(r.data)
      setEditing(r.data[selected] ? { ...r.data[selected] } : null)
    })
  }, [])

  const selectAgent = (key) => {
    setSelected(key)
    setEditing(allPrompts[key] ? { ...allPrompts[key] } : null)
  }

  const save = async () => {
    if (!editing) return
    setSaving(true)
    await promptsApi.update(selected, { system_prompt: editing.system, user_prompt_template: editing.template, ai_model: editing.model })
    setSaving(false)
  }

  const reset = async () => {
    setResetting(true)
    const r = await promptsApi.reset(selected)
    const def = r.data.prompt
    setEditing({ ...def })
    setAllPrompts(p => ({ ...p, [selected]: def }))
    setResetting(false)
  }

  return (
    <div className="flex gap-4 h-[calc(100vh-3rem)]">
      <div className="w-52 flex-shrink-0 glass rounded-xl p-3 space-y-1 overflow-y-auto">
        <div className="text-xs text-nexus-muted uppercase tracking-wider px-2 mb-3">Агенты</div>
        {AGENTS.map(({ key, label, desc }) => (
          <button key={key} onClick={() => selectAgent(key)}
            className={`w-full text-left px-3 py-2.5 rounded-lg transition text-sm ${selected === key ? 'bg-purple-600/20 text-purple-300 border border-purple-500/30' : 'text-nexus-muted hover:bg-nexus-card hover:text-nexus-text'}`}>
            <div className="font-medium">{label}</div>
            <div className="text-xs opacity-60 mt-0.5">{desc}</div>
          </button>
        ))}
      </div>

      <div className="flex-1 glass rounded-xl flex flex-col overflow-hidden">
        <div className="p-4 border-b border-nexus-border flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Cpu className="text-purple-400 w-5 h-5" />
            <span className="font-semibold">{AGENTS.find(a => a.key === selected)?.label}</span>
          </div>
          <div className="flex gap-2">
            <button onClick={reset} disabled={resetting}
              className="px-3 py-1.5 text-xs rounded-lg border border-nexus-border text-nexus-muted hover:text-nexus-text transition flex items-center gap-1">
              {resetting ? <Loader className="w-3 h-3 animate-spin" /> : <RotateCcw className="w-3 h-3" />} Сброс
            </button>
            <button onClick={save} disabled={saving}
              className="px-3 py-1.5 text-xs rounded-lg bg-purple-600 text-white hover:bg-purple-500 transition flex items-center gap-1 disabled:opacity-50">
              {saving ? <Loader className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />} Сохранить
            </button>
          </div>
        </div>

        {editing ? (
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            <div>
              <label className="text-xs text-nexus-muted mb-1 block">AI Модель</label>
              <select value={editing.model || ''} onChange={e => setEditing(p => ({ ...p, model: e.target.value }))}
                className="w-full bg-nexus-card border border-nexus-border rounded-lg px-3 py-2 text-sm text-nexus-text focus:border-purple-500 outline-none">
                {['Anthropic','OpenAI','Google','Perplexity','DeepSeek'].map(group => (
                  <optgroup key={group} label={group}>
                    {MODELS.filter(m => m.group === group).map(m => (
                      <option key={m.value} value={m.value}>{m.label}</option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-nexus-muted mb-1 block">System Prompt</label>
              <textarea value={editing.system || ''} onChange={e => setEditing(p => ({ ...p, system: e.target.value }))} rows={8}
                className="w-full bg-nexus-card border border-nexus-border rounded-lg px-3 py-2 text-sm text-nexus-text font-mono resize-none focus:border-purple-500 outline-none" />
            </div>
            <div>
              <label className="text-xs text-nexus-muted mb-1 block">User Prompt Template</label>
              <textarea value={editing.template || ''} onChange={e => setEditing(p => ({ ...p, template: e.target.value }))} rows={10}
                className="w-full bg-nexus-card border border-nexus-border rounded-lg px-3 py-2 text-sm text-nexus-text font-mono resize-none focus:border-purple-500 outline-none" />
            </div>
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center text-nexus-muted">Загрузка...</div>
        )}
      </div>
    </div>
  )
}
