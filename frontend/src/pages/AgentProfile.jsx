import React, { useEffect, useState } from 'react'
import { Sliders, Save, Eye, Loader, CheckCircle } from 'lucide-react'
import { agentProfile } from '../lib/api'

// 🎛 Главный агент. Здесь пользователь задаёт «дирижёру» рамку работы: нишу,
// бренд, цели, аудиторию, стиль, площадки, частоту, правила и ограничения.
// Кнопка «Показать промпт» существует не для красоты: без неё непонятно,
// доезжают ли настройки до модели вообще.

const TEXT_FIELDS = [
  { key: 'niche', label: 'Ниша', ph: 'доставка еды, барбершоп, онлайн-школа…' },
  { key: 'brand_name', label: 'Бренд', ph: 'название' },
  { key: 'brand_location', label: 'Город / регион', ph: 'Алматы' },
  { key: 'tone_of_voice', label: 'Tone of voice', ph: 'дружелюбный, без канцелярита' },
  { key: 'timezone', label: 'Часовой пояс', ph: 'Asia/Almaty' },
]

const AREA_FIELDS = [
  { key: 'goals', label: 'Цели', ph: 'что считаем результатом: заявки, продажи, подписчики' },
  { key: 'audience', label: 'Аудитория', ph: 'кто эти люди, что их беспокоит' },
  { key: 'style', label: 'Стиль', ph: 'как выглядит контент' },
  { key: 'rules', label: 'Правила', ph: 'что делать всегда' },
  { key: 'constraints', label: 'Ограничения', ph: 'чего не делать никогда' },
  { key: 'tasks', label: 'Постоянные задачи', ph: 'чем агент занимается без напоминаний' },
  { key: 'strategy', label: 'Стратегия', ph: 'как будем двигаться' },
]

const PLATFORMS = ['instagram', 'tiktok', 'telegram', 'youtube', 'vk', 'threads']

export default function AgentProfile() {
  const [p, setP] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [preview, setPreview] = useState('')

  useEffect(() => { agentProfile.get().then(r => setP(r.data)) }, [])

  const set = (k, v) => setP(prev => ({ ...prev, [k]: v }))
  const togglePlatform = (name) => {
    const cur = p.platforms || []
    set('platforms', cur.includes(name) ? cur.filter(x => x !== name) : [...cur, name])
  }

  const save = async () => {
    setSaving(true)
    try {
      await agentProfile.save({
        ...p,
        posts_per_day: Number(p.posts_per_day) || 0,
      })
      setSaved(true); setTimeout(() => setSaved(false), 2000)
    } finally { setSaving(false) }
  }

  const showPrompt = async () => {
    const { data } = await agentProfile.preview()
    setPreview(data.prompt)
  }

  if (!p) {
    return <div className="text-[#5a5a7a] text-sm flex items-center gap-2">
      <Loader className="w-4 h-4 animate-spin" /> Загрузка…
    </div>
  }

  const input = 'w-full bg-[#09091a] border border-[#1c1c30] rounded-lg px-3 py-2 text-sm outline-none focus:border-violet-500/50'

  return (
    <div className="max-w-3xl space-y-5">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-600 to-fuchsia-500 flex items-center justify-center">
          <Sliders className="w-5 h-5 text-white" />
        </div>
        <div>
          <h1 className="text-lg font-bold">Главный агент</h1>
          <p className="text-sm text-[#5a5a7a]">
            Эти настройки уходят в каждый запрос к модели — и дирижёру, и агентам
          </p>
        </div>
      </div>

      <div className="bg-[#0d0d1c] border border-[#1c1c30] rounded-xl p-5 space-y-4">
        <div className="grid md:grid-cols-2 gap-3">
          {TEXT_FIELDS.map(f => (
            <div key={f.key}>
              <label className="text-xs text-[#5a5a7a]">{f.label}</label>
              <input className={input} placeholder={f.ph}
                value={p[f.key] || ''} onChange={e => set(f.key, e.target.value)} />
            </div>
          ))}
          <div>
            <label className="text-xs text-[#5a5a7a]">Публикаций в день</label>
            <input className={input} type="number" min="0" max="20"
              value={p.posts_per_day ?? 0} onChange={e => set('posts_per_day', e.target.value)} />
          </div>
        </div>

        <div>
          <label className="text-xs text-[#5a5a7a]">Площадки</label>
          <div className="flex gap-2 flex-wrap mt-1.5">
            {PLATFORMS.map(name => (
              <button key={name} onClick={() => togglePlatform(name)}
                className={`px-3 py-1.5 rounded-lg text-xs border capitalize transition ${
                  (p.platforms || []).includes(name)
                    ? 'border-violet-500/40 bg-violet-600/15 text-violet-300'
                    : 'border-[#1c1c30] text-[#5a5a7a] hover:text-[#c0c0e0]'}`}>
                {name}
              </button>
            ))}
          </div>
        </div>

        {AREA_FIELDS.map(f => (
          <div key={f.key}>
            <label className="text-xs text-[#5a5a7a]">{f.label}</label>
            <textarea rows={2} className={input + ' resize-y'} placeholder={f.ph}
              value={p[f.key] || ''} onChange={e => set(f.key, e.target.value)} />
          </div>
        ))}

        <div>
          <label className="text-xs text-[#5a5a7a]">Голос бренда</label>
          <textarea rows={5} className={input + ' resize-y'}
            value={p.brand_voice || ''} onChange={e => set('brand_voice', e.target.value)} />
        </div>

        <div className="flex gap-2">
          <button onClick={save} disabled={saving}
            className="px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 text-white text-sm flex items-center gap-2 disabled:opacity-50">
            {saving ? <Loader className="w-4 h-4 animate-spin" />
              : saved ? <CheckCircle className="w-4 h-4" /> : <Save className="w-4 h-4" />}
            {saved ? 'Сохранено' : 'Сохранить'}
          </button>
          <button onClick={showPrompt}
            className="px-4 py-2 rounded-lg border border-[#1c1c30] text-[#c0c0e0] text-sm flex items-center gap-2 hover:bg-[#12122a]">
            <Eye className="w-4 h-4" /> Показать промпт
          </button>
        </div>
      </div>

      {preview && (
        <div className="bg-[#0d0d1c] border border-[#1c1c30] rounded-xl p-4">
          <div className="text-xs uppercase tracking-wider text-[#5a5a7a] mb-2">
            Что получает модель
          </div>
          <pre className="text-xs text-[#c0c0e0] whitespace-pre-wrap font-mono">{preview}</pre>
        </div>
      )}
    </div>
  )
}
