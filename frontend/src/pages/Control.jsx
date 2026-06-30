import React, { useState, useEffect } from 'react'
import {
  Rocket, Wand2, Loader, Save, CheckCircle, XCircle, Monitor, MonitorOff,
  Clapperboard, Megaphone, Star, Film, Brain, Video, Send, RefreshCw,
  Image as ImageIcon, Download
} from 'lucide-react'
import { connections as connApi, automation, desktop } from '../lib/api'

// Сервисы, которыми управляем прямо здесь
const SERVICES = [
  { id: 'gemini', name: 'Gemini (мозг-резерв, беспл.)', icon: '💎',
    fields: [{ key: 'gemini_api_key', label: 'API Key', ph: 'AIza...' }],
    link: 'https://aistudio.google.com/apikey' },
  { id: 'higgsfield', name: 'HiggsField (видео Reels)', icon: '🌌',
    fields: [{ key: 'higgsfield_api_key', label: 'API Key', ph: 'hf_...' }],
    link: 'https://higgsfield.ai' },
  { id: 'heygen', name: 'HeyGen (аватар, опц.)', icon: '🎭',
    fields: [{ key: 'heygen_api_key', label: 'API Key', ph: '...' }],
    link: 'https://app.heygen.com' },
  { id: 'telegram', name: 'Telegram (публикация+отчёты)', icon: '✈️',
    fields: [{ key: 'telegram_bot_token', label: 'Bot Token', ph: '123:ABC...' },
             { key: 'telegram_chat_id', label: 'Chat ID', ph: '-100...' }],
    link: 'https://t.me/BotFather' },
]

function dot(on) {
  return <span className={`w-2 h-2 rounded-full ${on ? 'bg-green-400' : 'bg-[#3a3a55]'}`} />
}

function ServiceRow({ svc, values, onChange, onSave, saving }) {
  const has = svc.fields.some(f => values[f.key])
  return (
    <div className="bg-[#0d0d1a] rounded-xl p-3 border border-[#1c1c30]">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-lg">{svc.icon}</span>
        <span className="text-sm font-medium text-[#e8e8f5] flex-1">{svc.name}</span>
        {dot(has)}
        <a href={svc.link} target="_blank" rel="noreferrer" className="text-[10px] text-cyan-400 hover:underline">где взять ↗</a>
      </div>
      <div className="grid sm:grid-cols-2 gap-2">
        {svc.fields.map(f => (
          <input key={f.key} type="password" placeholder={f.label + ' — ' + f.ph}
            value={values[f.key] || ''} onChange={e => onChange(f.key, e.target.value)}
            className="bg-[#07070f] border border-[#1c1c30] rounded-lg px-2 py-1.5 text-xs text-[#e8e8f5] placeholder-[#5a5a7a] focus:border-violet-500 outline-none font-mono" />
        ))}
      </div>
      <button onClick={() => onSave(svc)} disabled={saving}
        className="mt-2 text-xs px-3 py-1 rounded-lg bg-violet-600/20 text-violet-300 border border-violet-500/30 hover:bg-violet-600/30 transition flex items-center gap-1.5 disabled:opacity-50">
        {saving ? <Loader className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />} Сохранить
      </button>
    </div>
  )
}

export default function Control() {
  const [values, setValues] = useState({})
  const [saving, setSaving] = useState(false)
  const [agent, setAgent] = useState(null)

  // Фабрика
  const [topic, setTopic] = useState('')
  const [publish, setPublish] = useState(false)
  const [running, setRunning] = useState(false)
  const [res, setRes] = useState(null)

  // Фото
  const [photoPrompt, setPhotoPrompt] = useState('')
  const [photoPlatform, setPhotoPlatform] = useState('telegram')
  const [photoBusy, setPhotoBusy] = useState(false)
  const [photo, setPhoto] = useState(null)

  // Голос бренда
  const [voice, setVoice] = useState('')
  const [voiceSaved, setVoiceSaved] = useState(false)

  const loadAgent = () => desktop.status().then(r => setAgent(!!r.data?.connected)).catch(() => setAgent(false))
  useEffect(() => {
    connApi.list().then(r => setValues(r.data || {})).catch(() => {})
    automation.brand().then(r => setVoice(r.data?.voice || '')).catch(() => {})
    loadAgent(); const t = setInterval(loadAgent, 15000); return () => clearInterval(t)
  }, [])

  const onChange = (k, v) => setValues(p => ({ ...p, [k]: v }))
  const saveSvc = async () => {
    setSaving(true); try { await connApi.save(values) } catch {} setSaving(false)
  }
  const saveVoice = async () => {
    try { await automation.brandVoice(voice); setVoiceSaved(true); setTimeout(() => setVoiceSaved(false), 1500) } catch {}
  }
  const runFactory = async () => {
    setRunning(true); setRes(null)
    try { const r = await automation.factory({ topic: topic || null, dry_run: !publish }); setRes(r.data) }
    catch (e) { setRes({ ok: false, error: e.response?.data?.error || e.message }) }
    setRunning(false)
  }

  const createPhoto = async () => {
    if (!photoPrompt.trim()) return
    setPhotoBusy(true); setPhoto(null)
    try {
      const r = await automation.image({ prompt: photoPrompt, platform: photoPlatform })
      setPhoto(r.data)
    } catch (e) {
      setPhoto({ ok: false, error: e.response?.data?.error || e.message })
    }
    setPhotoBusy(false)
  }

  const plan = res?.plan || {}, strat = res?.strategy || {}, wow = res?.wow || {}
  const cover = res?.assets?.cover, video = res?.assets?.video
  const story = res?.brief?.storyboard || []

  return (
    <div className="max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-5 flex-wrap gap-2">
        <div>
          <h1 className="text-xl font-bold gradient-text flex items-center gap-2">
            <Rocket className="w-5 h-5 text-violet-400" /> Центр управления — Pakhon Studio
          </h1>
          <p className="text-xs text-[#5a5a7a] mt-1">Reels на автомате · мозг работает отсюда · настрой всё здесь</p>
        </div>
        <div className={`flex items-center gap-2 text-xs px-3 py-1.5 rounded-lg border ${agent ? 'border-green-500/30 text-green-400' : 'border-[#1c1c30] text-[#5a5a7a]'}`}>
          {agent ? <Monitor className="w-4 h-4" /> : <MonitorOff className="w-4 h-4" />}
          Браузер-агент {agent ? 'на связи' : 'оффлайн'}
          <button onClick={loadAgent}><RefreshCw className="w-3 h-3" /></button>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        {/* ФАБРИКА */}
        <div className="card p-5 lg:col-span-2">
          <div className="flex items-center gap-2 mb-3">
            <Clapperboard className="w-5 h-5 text-violet-400" />
            <span className="font-semibold">Создать Reels</span>
            <span className="text-[11px] text-[#5a5a7a]">— анализ → ТЗ → видео → публикация</span>
          </div>
          <textarea rows={2} value={topic} onChange={e => setTopic(e.target.value)}
            placeholder="Тема (или пусто — выберу сам). Напр.: AI заменит дизайнеров"
            className="w-full bg-[#0d0d1a] border border-[#1c1c30] rounded-lg px-3 py-2 text-sm text-[#e8e8f5] placeholder-[#5a5a7a] focus:border-violet-500 outline-none resize-none" />
          <div className="flex items-center justify-between mt-3 flex-wrap gap-2">
            <label className="flex items-center gap-2 text-xs text-[#c0c0e0] cursor-pointer">
              <input type="checkbox" checked={publish} onChange={e => setPublish(e.target.checked)} />
              Опубликовать сразу
            </label>
            <button onClick={runFactory} disabled={running}
              className="btn-primary flex items-center gap-2 disabled:opacity-50">
              {running ? <Loader className="w-4 h-4 animate-spin" /> : <Wand2 className="w-4 h-4" />}
              {running ? 'Создаю...' : publish ? 'Создать и опубликовать' : 'Создать (превью)'}
            </button>
          </div>
          {res && res.ok !== false && (
            <div className="mt-4 grid md:grid-cols-3 gap-3">
              <div className="md:col-span-2 space-y-2">
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <M l="Тема" v={plan.theme} />
                  <M l={`Хук (${plan.hook_type || '?'})`} v={plan.hook_text} />
                  <M l="Стратегия" v={`${strat.strategy || '—'} ~$${strat.est_cost ?? 0}`} />
                  <M l="Вау" v={`${wow.score ?? '—'}/10`} icon={<Star className="w-3 h-3 text-yellow-400" />} />
                </div>
                {story.length > 0 && (
                  <div className="text-xs">
                    <div className="text-[#7a7a9a] mb-1 flex items-center gap-1"><Film className="w-3 h-3" /> Раскадровка</div>
                    {story.map((s, i) => (
                      <div key={i} className="bg-[#0d0d1a] rounded px-2 py-1 mb-1">
                        <span className="text-violet-300">{s.t}</span> · {s.overlay}
                      </div>
                    ))}
                  </div>
                )}
                <div className="flex flex-wrap gap-1.5 text-xs">
                  {(res.steps || []).map((s, i) => (
                    <span key={i} className={`px-2 py-0.5 rounded-full ${s.ok ? 'bg-green-500/10 text-green-400' : 'bg-amber-500/10 text-amber-400'}`}>
                      {s.ok ? '✓' : '⚠'} {s.step}{s.provider ? `[${s.provider}]` : ''}
                    </span>
                  ))}
                </div>
                {video && (
                  <div className={`text-xs ${video.ok ? 'text-green-400' : 'text-amber-400'}`}>
                    🎬 {video.ok ? `видео готово (${video.provider})` : (video.error || video.note)}
                  </div>
                )}
              </div>
              {cover && <img src={cover} alt="" className="rounded-lg max-h-72 border border-[#1c1c30] justify-self-center" />}
            </div>
          )}
          {res?.ok === false && <div className="mt-3 text-xs text-red-400">{res.error}</div>}
        </div>

        {/* ФОТО */}
        <div className="card p-5 lg:col-span-2">
          <div className="flex items-center gap-2 mb-3">
            <ImageIcon className="w-5 h-5 text-cyan-400" />
            <span className="font-semibold">Создать фото</span>
            <span className="text-[11px] text-[#5a5a7a]">— описание → изображение (Imagen / DALL-E / Stability / беспл.)</span>
          </div>
          <textarea rows={2} value={photoPrompt} onChange={e => setPhotoPrompt(e.target.value)}
            placeholder="Опиши кадр. Напр.: курьер на электровелосипеде, неоновый город ночью, кинематографично"
            className="w-full bg-[#0d0d1a] border border-[#1c1c30] rounded-lg px-3 py-2 text-sm text-[#e8e8f5] placeholder-[#5a5a7a] focus:border-cyan-500 outline-none resize-none" />
          <div className="flex items-center justify-between mt-3 flex-wrap gap-2">
            <label className="flex items-center gap-2 text-xs text-[#c0c0e0]">
              Формат
              <select value={photoPlatform} onChange={e => setPhotoPlatform(e.target.value)}
                className="bg-[#0d0d1a] border border-[#1c1c30] rounded-lg px-2 py-1 text-xs text-[#e8e8f5] focus:border-cyan-500 outline-none">
                <option value="telegram">Квадрат 1:1 (Telegram/пост)</option>
                <option value="instagram">Вертикаль 9:16 (Stories/Reels)</option>
                <option value="tiktok">Вертикаль 9:16 (TikTok)</option>
                <option value="youtube">Вертикаль 9:16 (Shorts)</option>
              </select>
            </label>
            <button onClick={createPhoto} disabled={photoBusy || !photoPrompt.trim()}
              className="btn-primary flex items-center gap-2 disabled:opacity-50">
              {photoBusy ? <Loader className="w-4 h-4 animate-spin" /> : <Wand2 className="w-4 h-4" />}
              {photoBusy ? 'Рисую...' : 'Создать фото'}
            </button>
          </div>
          {photo?.ok && photo.url && (
            <div className="mt-4 flex flex-col items-center gap-2">
              <img src={photo.url} alt="" className="rounded-lg max-h-96 border border-[#1c1c30]" />
              <a href={photo.url} target="_blank" rel="noreferrer" download
                className="text-xs text-cyan-400 hover:underline flex items-center gap-1">
                <Download className="w-3 h-3" /> Открыть / скачать
              </a>
            </div>
          )}
          {photo?.ok === false && <div className="mt-3 text-xs text-red-400">{photo.error}</div>}
        </div>

        {/* СЕРВИСЫ */}
        <div className="card p-5">
          <div className="flex items-center gap-2 mb-3">
            <Brain className="w-5 h-5 text-cyan-400" />
            <span className="font-semibold">Сервисы — настрой здесь</span>
          </div>
          <p className="text-[11px] text-[#5a5a7a] mb-3">🧠 Мозг (Claude) — работает отсюда, ключ не нужен. Подключи видео и Telegram:</p>
          <div className="space-y-2">
            {SERVICES.map(s => (
              <ServiceRow key={s.id} svc={s} values={values} onChange={onChange} onSave={saveSvc} saving={saving} />
            ))}
          </div>
        </div>

        {/* ГОЛОС БРЕНДА */}
        <div className="card p-5">
          <div className="flex items-center gap-2 mb-3">
            <Megaphone className="w-5 h-5 text-violet-400" />
            <span className="font-semibold">Голос бренда</span>
          </div>
          <textarea rows={9} value={voice} onChange={e => setVoice(e.target.value)}
            className="w-full bg-[#0d0d1a] border border-[#1c1c30] rounded-lg px-3 py-2 text-xs text-[#e8e8f5] focus:border-violet-500 outline-none resize-none" />
          <button onClick={saveVoice}
            className="mt-2 text-xs px-3 py-1.5 rounded-lg bg-violet-600/20 text-violet-300 border border-violet-500/30 hover:bg-violet-600/30 transition flex items-center gap-1.5">
            {voiceSaved ? <CheckCircle className="w-3 h-3" /> : <Save className="w-3 h-3" />} {voiceSaved ? 'Сохранено' : 'Сохранить голос'}
          </button>
        </div>
      </div>
    </div>
  )
}

function M({ l, v, icon }) {
  return (
    <div className="bg-[#0d0d1a] rounded-lg px-3 py-2">
      <div className="text-[10px] text-[#5a5a7a] flex items-center gap-1">{icon}{l}</div>
      <div className="text-[#e8e8f5] mt-0.5 truncate" title={v}>{v || '—'}</div>
    </div>
  )
}
