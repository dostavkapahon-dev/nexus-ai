import React, { useState, useEffect, useRef } from 'react'
import {
  Activity, RefreshCw, Loader, CheckCircle, XCircle, Circle,
  ExternalLink, Cpu, Zap, Brain, Send, Wand2, Clapperboard, Film, Star,
  Monitor, MonitorOff,
} from 'lucide-react'
import { ai, control, automation, desktop } from '../lib/api'

// Человеческие имена агентов — ключи совпадают с тем, что шлёт бэкенд в WS.
const AGENT_LABELS = {
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

const STATE_STYLE = {
  idle: 'border-[#1c1c30] bg-[#0d0d18] text-[#5a5a7a]',
  running: 'border-violet-500/60 bg-violet-600/15 text-violet-200 animate-pulse',
  done: 'border-green-500/40 bg-green-500/10 text-green-300',
  cached: 'border-sky-500/40 bg-sky-500/10 text-sky-300',
  error: 'border-red-500/50 bg-red-500/10 text-red-300',
}

const STATE_LABEL = {
  idle: 'ожидает', running: 'работает', done: 'готово',
  cached: 'из кэша', error: 'ошибка',
}

function FlowVisualizer() {
  const [agents, setAgents] = useState({})
  const [events, setEvents] = useState([])
  const [live, setLive] = useState(false)
  const wsRef = useRef(null)

  useEffect(() => {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/global`)
    wsRef.current = ws
    ws.onopen = () => setLive(true)
    ws.onclose = () => setLive(false)
    ws.onmessage = (e) => {
      let d
      try { d = JSON.parse(e.data) } catch { return }
      const time = new Date().toLocaleTimeString('ru-RU')

      if (d.event === 'agent_start') setAgents(p => ({ ...p, [d.agent]: 'running' }))
      else if (d.event === 'agent_done') setAgents(p => ({ ...p, [d.agent]: 'done' }))
      else if (d.event === 'cache_hit') setAgents(p => ({ ...p, [d.agent]: 'cached' }))
      else if (d.event === 'pipeline_complete') setAgents({})

      setEvents(p => [{ time, ...d }, ...p].slice(0, 30))
    }
    return () => ws.close()
  }, [])

  const names = Object.keys(AGENT_LABELS)
  const active = names.filter(n => agents[n] === 'running').length

  return (
    <div className="card p-5 mb-5 border border-[#1c1c30]">
      <div className="flex items-center gap-2 mb-4">
        <Cpu className="w-5 h-5 text-violet-400" />
        <span className="font-semibold text-[#e8e8f5]">Агенты</span>
        <span className="text-[11px] text-[#5a5a7a]">
          {active > 0 ? `${active} в работе` : 'простой'}
        </span>
        <span className={`ml-auto flex items-center gap-1.5 text-[11px] ${live ? 'text-green-400' : 'text-[#5a5a7a]'}`}>
          <span className={`w-2 h-2 rounded-full ${live ? 'bg-green-400 animate-pulse' : 'bg-[#3a3a55]'}`} />
          {live ? 'подключено' : 'нет связи'}
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2 mb-4">
        {names.map(n => {
          const st = agents[n] || 'idle'
          return (
            <div key={n}
              className={`rounded-lg border px-3 py-2.5 text-sm transition-all ${STATE_STYLE[st]}`}>
              <div className="font-medium truncate">{AGENT_LABELS[n]}</div>
              <div className="text-[11px] opacity-70 mt-0.5">{STATE_LABEL[st]}</div>
            </div>
          )
        })}
      </div>

      <div className="text-[11px] font-medium text-[#5a5a7a] mb-1.5">Лента событий</div>
      <div className="max-h-44 overflow-y-auto space-y-1">
        {events.length === 0 && (
          <div className="text-[12px] text-[#3a3a55] py-3 text-center">
            Пока тихо. Запусти <code className="text-violet-300">/factory</code> или
            <code className="text-violet-300"> /auto</code> в Telegram — события появятся здесь.
          </div>
        )}
        {events.map((e, i) => (
          <div key={i} className="flex items-baseline gap-2 text-[12px]">
            <span className="text-[#3a3a55] tabular-nums">{e.time}</span>
            <span className="text-[#c0c0e0]">{e.event}</span>
            {e.agent && <span className="text-violet-300">{AGENT_LABELS[e.agent] || e.agent}</span>}
            {e.platform && <span className="text-sky-300">{e.platform}</span>}
          </div>
        ))}
      </div>
    </div>
  )
}

function ProviderCard({ p }) {
  const Icon = p.ok ? CheckCircle : (p.has_key ? XCircle : Circle)
  const tone = p.ok ? 'text-green-400 border-green-500/30'
    : (p.has_key ? 'text-red-400 border-red-500/30' : 'text-[#5a5a7a] border-[#1c1c30]')

  return (
    <div className={`rounded-lg border ${tone.split(' ')[1]} bg-[#0d0d18] p-3.5`}>
      <div className="flex items-center gap-2">
        <Icon className={`w-4 h-4 flex-shrink-0 ${tone.split(' ')[0]}`} />
        <span className="font-medium text-sm text-[#e8e8f5]">{p.name}</span>
        {p.free && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-500/15 text-green-400">
            бесплатно
          </span>
        )}
      </div>

      {p.ok && p.model && (
        <div className="text-[11px] text-[#5a5a7a] mt-1.5">модель: {p.model}</div>
      )}
      {p.has_key && !p.ok && p.error && (
        <div className="text-[11px] text-red-400/90 mt-1.5">{p.error}</div>
      )}
      {!p.has_key && (
        <>
          <div className="text-[11px] text-[#5a5a7a] mt-1.5">{p.limits}</div>
          {p.signup && (
            <a href={p.signup} target="_blank" rel="noreferrer"
              className="inline-flex items-center gap-1 text-[11px] text-violet-300 hover:text-violet-200 mt-1.5">
              получить ключ <ExternalLink className="w-3 h-3" />
            </a>
          )}
          <div className="text-[10px] text-[#3a3a55] mt-1">
            переменная: <code>{p.key_env}</code>
          </div>
        </>
      )}
    </div>
  )
}

function SystemHealth() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      const r = await ai.providers()
      setData(r.data)
    } catch (e) {
      setData({ providers: [], working: [], ready: false, _error: e.message })
    }
    setLoading(false)
  }
  useEffect(() => { load() }, [])

  const providers = data?.providers || []
  const paid = providers.filter(p => !p.free)
  const free = providers.filter(p => p.free)

  return (
    <div className="card p-5 border border-[#1c1c30]">
      <div className="flex items-center gap-2 mb-1">
        <Zap className="w-5 h-5 text-violet-400" />
        <span className="font-semibold text-[#e8e8f5]">ИИ-провайдеры</span>
        <button onClick={load} disabled={loading}
          className="ml-auto text-[#5a5a7a] hover:text-violet-300 disabled:opacity-40">
          {loading ? <Loader className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
        </button>
      </div>

      {data && (
        <div className={`text-sm mb-4 ${data.ready ? 'text-green-400' : 'text-red-400'}`}>
          {data.ready
            ? `Работают: ${data.working.join(', ')}`
            : 'Рабочих ИИ-ключей нет — анализ и генерация не запустятся'}
        </div>
      )}

      {loading && !data && (
        <div className="text-sm text-[#5a5a7a] py-4">Проверяю провайдеров...</div>
      )}

      {paid.length > 0 && (
        <>
          <div className="text-[11px] font-medium text-[#5a5a7a] mb-2">Основные</div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mb-4">
            {paid.map(p => <ProviderCard key={p.key_env} p={p} />)}
          </div>
        </>
      )}

      {free.length > 0 && (
        <>
          <div className="text-[11px] font-medium text-[#5a5a7a] mb-2">
            Бесплатные — достаточно одного, чтобы всё ожило
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {free.map(p => <ProviderCard key={p.key_env} p={p} />)}
          </div>
        </>
      )}
    </div>
  )
}


// Пульт и фабрика переехали сюда с бывшей главной: управление задачами — это
// и есть командный центр, а главная по ТЗ показывает только статус.
function Pult() {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [feed, setFeed] = useState([])

  const loadFeed = () => control.feed(40).then(r => setFeed(r.data?.feed || [])).catch(() => {})
  useEffect(() => {
    loadFeed()
    // Раз в 10 секунд: прежние 4 секунды держали постоянный поток запросов
    // даже когда никто ничего не отправлял.
    const t = setInterval(loadFeed, 10000)
    return () => clearInterval(t)
  }, [])

  const send = async () => {
    const t = text.trim()
    if (!t || busy) return
    setBusy(true); setText('')
    try { await control.command(t) } catch {}
    await loadFeed(); setBusy(false)
  }
  const onKey = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }

  const badge = (src) => src === 'telegram'
    ? <span title="из Telegram">✈️</span>
    : src === 'dashboard' ? <span title="с сайта">🖥</span> : <span>⚙️</span>

  return (
    <div className="card p-5 mb-5 border border-violet-500/25">
      <div className="flex items-center gap-2 mb-3">
        <Brain className="w-5 h-5 text-violet-400" />
        <span className="font-semibold">Пульт управления</span>
        <span className="text-[11px] text-[#5a5a7a]">— один мозг, общий с Telegram</span>
      </div>

      <div className="bg-[#0d0d1a] border border-[#1c1c30] rounded-lg p-3 mb-3 h-56 overflow-y-auto flex flex-col gap-2 text-xs">
        {feed.length === 0 && <div className="text-[#5a5a7a] m-auto">Напишите команду — например «проанализируй аккаунт» или «сделай рилс про доставку»</div>}
        {feed.map((m, i) => (
          <div key={i} className={`flex gap-2 ${m.role === 'user' ? 'text-[#c0c0e0]' : 'text-[#9a9ac0]'}`}>
            <div className="shrink-0">{m.role === 'user' ? badge(m.source) : '🤖'}</div>
            <div className={`rounded-lg px-2.5 py-1.5 whitespace-pre-wrap ${m.role === 'user' ? 'bg-violet-600/15' : 'bg-[#07070f] border border-[#1c1c30]'}`}>{m.text}</div>
          </div>
        ))}
      </div>

      <div className="flex items-end gap-2">
        <textarea rows={1} value={text} onChange={e => setText(e.target.value)} onKeyDown={onKey}
          placeholder="Команда (Enter — отправить)…"
          className="flex-1 bg-[#0d0d1a] border border-[#1c1c30] rounded-lg px-3 py-2 text-sm text-[#e8e8f5] placeholder-[#5a5a7a] focus:border-violet-500 outline-none resize-none" />
        <button onClick={send} disabled={busy}
          className="btn-primary flex items-center gap-2 disabled:opacity-50">
          {busy ? <Loader className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          {busy ? 'Думаю…' : 'Отправить'}
        </button>
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

function Factory() {
  const [topic, setTopic] = useState('')
  const [publish, setPublish] = useState(false)
  const [running, setRunning] = useState(false)
  const [res, setRes] = useState(null)
  const [agent, setAgent] = useState(null)

  const loadAgent = () => desktop.status().then(r => setAgent(!!r.data?.connected)).catch(() => setAgent(false))
  useEffect(() => { loadAgent(); const t = setInterval(loadAgent, 30000); return () => clearInterval(t) }, [])

  const run = async () => {
    setRunning(true); setRes(null)
    try { const r = await automation.factory({ topic: topic || null, dry_run: !publish }); setRes(r.data) }
    catch (e) { setRes({ ok: false, error: e.response?.data?.error || e.message }) }
    setRunning(false)
  }

  const plan = res?.plan || {}, strat = res?.strategy || {}, wow = res?.wow || {}
  const cover = res?.assets?.cover, video = res?.assets?.video
  const story = res?.brief?.storyboard || []

  return (
    <div className="card p-5 mb-5">
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <Clapperboard className="w-5 h-5 text-violet-400" />
        <span className="font-semibold">Создать Reels</span>
        <span className="text-[11px] text-[#5a5a7a]">— анализ → ТЗ → видео → публикация</span>
        <span className={`ml-auto flex items-center gap-1.5 text-[11px] ${agent ? 'text-green-400' : 'text-[#5a5a7a]'}`}>
          {agent ? <Monitor className="w-3.5 h-3.5" /> : <MonitorOff className="w-3.5 h-3.5" />}
          браузер-агент {agent ? 'на связи' : 'оффлайн'}
        </span>
      </div>
      <textarea rows={2} value={topic} onChange={e => setTopic(e.target.value)}
        placeholder="Тема (или пусто — выберу сам). Напр.: AI заменит дизайнеров"
        className="w-full bg-[#0d0d1a] border border-[#1c1c30] rounded-lg px-3 py-2 text-sm text-[#e8e8f5] placeholder-[#5a5a7a] focus:border-violet-500 outline-none resize-none" />
      <div className="flex items-center justify-between mt-3 flex-wrap gap-2">
        <label className="flex items-center gap-2 text-xs text-[#c0c0e0] cursor-pointer">
          <input type="checkbox" checked={publish} onChange={e => setPublish(e.target.checked)} />
          Опубликовать сразу
        </label>
        <button onClick={run} disabled={running}
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
  )
}

export default function CommandCenter() {
  return (
    <div className="max-w-5xl">
      <div className="flex items-center gap-3 mb-1">
        <Activity className="w-6 h-6 text-violet-400" />
        <h1 className="text-xl font-semibold text-[#e8e8f5]">Командный центр</h1>
      </div>
      <p className="text-sm text-[#5a5a7a] mb-5">
        Управление задачами: команды, создание контента и живая картина работы агентов.
      </p>

      <Pult />
      <Factory />
      <FlowVisualizer />
      <SystemHealth />
    </div>
  )
}
