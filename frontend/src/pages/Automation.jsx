import React from 'react'
import { automation } from '../lib/api'
import { Power, Compass, Clapperboard, Play, Save, Loader2, Clock } from 'lucide-react'

const JOBS = [
  { id: 'autopilot', label: 'Автопилот (план)', hint: 'Создаёт план для активных ниш' },
  { id: 'trends',    label: 'Анализ трендов',   hint: 'Agent 6' },
  { id: 'generate',  label: 'Генерация постов', hint: 'Agents 3+4' },
  { id: 'publish',   label: 'Публикация',       hint: 'Во все платформы' },
  { id: 'report',    label: 'Отчёт',            hint: 'Сводка в Telegram' },
]

const PROVIDERS = [
  { v: 'auto', label: 'Авто (HeyGen→Higgsfield→Runway)' },
  { v: 'heygen', label: 'HeyGen' },
  { v: 'higgsfield', label: 'Higgsfield' },
  { v: 'runway', label: 'Runway' },
]

const hours = Array.from({ length: 24 }, (_, i) => i)

function Toggle({ on, onClick, label, desc, icon: Icon }) {
  return (
    <button onClick={onClick}
      className={`flex items-center gap-3 w-full p-4 rounded-xl border text-left transition ${
        on ? 'bg-violet-600/15 border-violet-500/40' : 'bg-[#0e0e1d] border-[#1c1c30]'
      }`}>
      <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${on ? 'bg-violet-600/30 text-violet-300' : 'bg-[#15152a] text-[#5a5a7a]'}`}>
        <Icon className="w-4 h-4" />
      </div>
      <div className="flex-1">
        <div className="text-sm font-medium text-[#e0e0f5]">{label}</div>
        <div className="text-[11px] text-[#5a5a7a]">{desc}</div>
      </div>
      <div className={`w-10 h-6 rounded-full p-0.5 transition ${on ? 'bg-violet-500' : 'bg-[#23233a]'}`}>
        <div className={`w-5 h-5 rounded-full bg-white transition ${on ? 'translate-x-4' : ''}`} />
      </div>
    </button>
  )
}

function HourSelect({ value, onChange, label }) {
  return (
    <label className="flex items-center justify-between gap-3 p-3 rounded-lg bg-[#0e0e1d] border border-[#1c1c30]">
      <span className="text-xs text-[#c0c0e0] flex items-center gap-2"><Clock className="w-3.5 h-3.5 text-[#5a5a7a]" />{label}</span>
      <select value={value} onChange={e => onChange(parseInt(e.target.value))}
        className="bg-[#15152a] border border-[#23233a] rounded px-2 py-1 text-xs text-[#e0e0f5]">
        {hours.map(h => <option key={h} value={h}>{String(h).padStart(2, '0')}:00 UTC</option>)}
      </select>
    </label>
  )
}

export default function Automation() {
  const [cfg, setCfg] = React.useState(null)
  const [saving, setSaving] = React.useState(false)
  const [running, setRunning] = React.useState('')
  const [msg, setMsg] = React.useState('')

  const load = () => automation.get().then(r => setCfg(r.data))
  React.useEffect(() => { load() }, [])

  const set = (k, v) => setCfg(c => ({ ...c, [k]: v }))

  const save = async () => {
    setSaving(true); setMsg('')
    try { const r = await automation.save(cfg); setCfg(r.data); setMsg('Сохранено ✓') }
    catch (e) { setMsg('Ошибка сохранения') }
    finally { setSaving(false); setTimeout(() => setMsg(''), 2500) }
  }

  const run = async (id) => {
    setRunning(id); setMsg('')
    try { await automation.run(id); setMsg(`Запущено: ${id} ✓`) }
    catch (e) { setMsg(`Ошибка запуска ${id}`) }
    finally { setRunning(''); setTimeout(() => setMsg(''), 3000) }
  }

  if (!cfg) return <div className="text-[#5a5a7a] text-sm">Загрузка…</div>

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[#e0e0f5]">Автоматизация</h1>
        <p className="text-sm text-[#5a5a7a] mt-1">Полный цикл 24/7: автопилот создаёт план, генерирует контент и публикует его сам.</p>
      </div>

      <div className="space-y-2.5">
        <Toggle icon={Power} on={cfg.enabled} onClick={() => set('enabled', !cfg.enabled)}
          label="Главный выключатель" desc="Включает всю автоматизацию по расписанию" />
        <Toggle icon={Compass} on={cfg.autopilot} onClick={() => set('autopilot', !cfg.autopilot)}
          label="Автопилот" desc="Каждый час досоздаёт план для активных ниш" />
        <Toggle icon={Clapperboard} on={cfg.auto_video} onClick={() => set('auto_video', !cfg.auto_video)}
          label="Авто-видео" desc="Генерировать видеоклип к каждому посту" />
      </div>

      {cfg.auto_video && (
        <div className="p-4 rounded-xl bg-[#0e0e1d] border border-[#1c1c30]">
          <label className="text-xs text-[#c0c0e0]">Провайдер видео</label>
          <select value={cfg.video_provider} onChange={e => set('video_provider', e.target.value)}
            className="mt-2 w-full bg-[#15152a] border border-[#23233a] rounded px-3 py-2 text-sm text-[#e0e0f5]">
            {PROVIDERS.map(p => <option key={p.v} value={p.v}>{p.label}</option>)}
          </select>
        </div>
      )}

      <div>
        <div className="text-xs font-semibold text-[#8a8ab0] uppercase tracking-wide mb-2">Расписание (UTC)</div>
        <div className="grid grid-cols-2 gap-2">
          <HourSelect label="Тренды" value={cfg.schedule_trends} onChange={v => set('schedule_trends', v)} />
          <HourSelect label="Генерация" value={cfg.schedule_generate} onChange={v => set('schedule_generate', v)} />
          <HourSelect label="Публикация" value={cfg.schedule_publish} onChange={v => set('schedule_publish', v)} />
          <HourSelect label="Отчёт" value={cfg.schedule_report} onChange={v => set('schedule_report', v)} />
        </div>
        <label className="flex items-center justify-between gap-3 p-3 mt-2 rounded-lg bg-[#0e0e1d] border border-[#1c1c30]">
          <span className="text-xs text-[#c0c0e0]">Постов за один прогон</span>
          <input type="number" min="1" max="50" value={cfg.batch_size}
            onChange={e => set('batch_size', parseInt(e.target.value) || 1)}
            className="w-20 bg-[#15152a] border border-[#23233a] rounded px-2 py-1 text-xs text-[#e0e0f5]" />
        </label>
      </div>

      <div className="flex items-center gap-3">
        <button onClick={save} disabled={saving}
          className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium disabled:opacity-50">
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Сохранить
        </button>
        {msg && <span className="text-xs text-[#8a8ab0]">{msg}</span>}
      </div>

      <div>
        <div className="text-xs font-semibold text-[#8a8ab0] uppercase tracking-wide mb-2">Запустить сейчас</div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {JOBS.map(j => (
            <button key={j.id} onClick={() => run(j.id)} disabled={running === j.id}
              className="flex items-center gap-2 p-3 rounded-lg bg-[#0e0e1d] border border-[#1c1c30] hover:border-violet-500/40 text-left disabled:opacity-50">
              {running === j.id ? <Loader2 className="w-4 h-4 animate-spin text-violet-300" /> : <Play className="w-4 h-4 text-violet-300" />}
              <div>
                <div className="text-xs font-medium text-[#e0e0f5]">{j.label}</div>
                <div className="text-[10px] text-[#5a5a7a]">{j.hint}</div>
              </div>
            </button>
          ))}
        </div>
        <p className="text-[11px] text-[#5a5a7a] mt-2">Ручной запуск работает даже при выключенном главном выключателе — удобно для теста.</p>
      </div>
    </div>
  )
}
