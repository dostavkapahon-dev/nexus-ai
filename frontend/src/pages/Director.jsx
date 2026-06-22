import React, { useState, useEffect } from 'react'
import { Bot, Send, Loader, Monitor, MonitorOff, Globe, Sparkles, CheckCircle, XCircle, RefreshCw, Film, Wand2, Star, Clapperboard } from 'lucide-react'
import { automation, desktop } from '../lib/api'

const PLATFORMS = ['instagram', 'youtube', 'tiktok', 'telegram']

function FactoryPanel() {
  const [topic, setTopic] = useState('')
  const [publish, setPublish] = useState(false)
  const [running, setRunning] = useState(false)
  const [res, setRes] = useState(null)

  const run = async () => {
    setRunning(true); setRes(null)
    try {
      const r = await automation.factory({ topic: topic || null, dry_run: !publish })
      setRes(r.data)
    } catch (e) {
      setRes({ ok: false, error: e.response?.data?.error || e.message })
    }
    setRunning(false)
  }

  const plan = res?.plan || {}
  const strat = res?.strategy || {}
  const wow = res?.wow || {}
  const cover = res?.assets?.cover
  const video = res?.assets?.video
  const story = res?.brief?.storyboard || []

  return (
    <div className="card p-5 mb-5 border border-violet-500/25">
      <div className="flex items-center gap-2 mb-3">
        <Clapperboard className="w-5 h-5 text-violet-400" />
        <span className="font-semibold">Фабрика контента</span>
        <span className="text-[11px] text-[#5a5a7a]">— анализ → ТЗ → видео → публикация</span>
      </div>
      <textarea value={topic} onChange={e => setTopic(e.target.value)} rows={2}
        placeholder="Тема (или пусто — выберу сам по трендам). Напр.: AI заменит дизайнеров"
        className="w-full bg-[#0d0d1a] border border-[#1c1c30] rounded-lg px-3 py-2 text-sm text-[#e8e8f5] placeholder-[#5a5a7a] focus:border-violet-500 outline-none resize-none" />
      <div className="flex items-center justify-between mt-3 flex-wrap gap-2">
        <label className="flex items-center gap-2 text-xs text-[#c0c0e0] cursor-pointer">
          <input type="checkbox" checked={publish} onChange={e => setPublish(e.target.checked)} />
          Опубликовать сразу ({PLATFORMS.join(', ')})
        </label>
        <button onClick={run} disabled={running}
          className="btn-primary flex items-center gap-2 disabled:opacity-50">
          {running ? <Loader className="w-4 h-4 animate-spin" /> : <Wand2 className="w-4 h-4" />}
          {running ? 'Создаю...' : publish ? 'Создать и опубликовать' : 'Создать (превью)'}
        </button>
      </div>

      {res && res.ok !== false && (
        <div className="mt-4 space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
            <Metric label="Тема" value={plan.theme} />
            <Metric label={`Хук (${plan.hook_type || '?'})`} value={plan.hook_text} />
            <Metric label="Стратегия" value={`${strat.strategy || '—'} ~$${strat.est_cost ?? 0}`} />
            <Metric label="Вау" value={`${wow.score ?? '—'}/10`} icon={<Star className="w-3 h-3 text-yellow-400" />} />
          </div>
          {cover && (
            <img src={cover} alt="cover" className="rounded-lg max-h-64 border border-[#1c1c30]" />
          )}
          {story.length > 0 && (
            <div className="text-xs">
              <div className="text-[#7a7a9a] mb-1 flex items-center gap-1"><Film className="w-3 h-3" /> Раскадровка</div>
              {story.map((s, i) => (
                <div key={i} className="bg-[#0d0d1a] rounded px-2 py-1 mb-1">
                  <span className="text-violet-300">{s.t}</span> · {s.overlay} <span className="text-[#5a5a7a]">— {s.visual}</span>
                </div>
              ))}
            </div>
          )}
          <div className="flex flex-wrap gap-1.5 text-xs">
            {(res.steps || []).map((s, i) => (
              <span key={i} className={`px-2 py-0.5 rounded-full ${s.ok ? 'bg-green-500/10 text-green-400' : 'bg-amber-500/10 text-amber-400'}`}>
                {s.ok ? '✓' : '⚠'} {s.step}{s.provider ? ` [${s.provider}]` : ''}
              </span>
            ))}
          </div>
          {video && (
            <div className={`text-xs ${video.ok ? 'text-green-400' : 'text-amber-400'}`}>
              🎬 Видео: {video.ok ? `готово (${video.provider})` : (video.error || video.note)}
            </div>
          )}
          {res.published && !res.dry_run && (
            <div className="flex flex-wrap gap-1.5 text-xs">
              {Object.entries(res.published).map(([pf, r]) => (
                <span key={pf} className={`px-2 py-0.5 rounded-full ${r.ok ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
                  {r.ok ? '✅' : '⚠️'} {pf}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
      {res?.ok === false && (
        <div className="mt-3 text-xs text-red-400">{res.error}</div>
      )}
    </div>
  )
}

function Metric({ label, value, icon }) {
  return (
    <div className="bg-[#0d0d1a] rounded-lg px-3 py-2">
      <div className="text-[10px] text-[#5a5a7a] flex items-center gap-1">{icon}{label}</div>
      <div className="text-[#e8e8f5] mt-0.5 truncate" title={value}>{value || '—'}</div>
    </div>
  )
}

function AgentStatus() {
  const [connected, setConnected] = useState(null)
  const [checking, setChecking] = useState(false)

  const check = async () => {
    setChecking(true)
    try { const r = await desktop.status(); setConnected(Boolean(r.data?.connected)) }
    catch { setConnected(false) }
    setChecking(false)
  }
  useEffect(() => { check(); const t = setInterval(check, 15000); return () => clearInterval(t) }, [])

  return (
    <div className="card px-4 py-3 flex items-center justify-between mb-5">
      <div className="flex items-center gap-3">
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${connected ? 'bg-green-500/15' : 'bg-[#111120]'}`}>
          {connected ? <Monitor className="w-4 h-4 text-green-400" /> : <MonitorOff className="w-4 h-4 text-[#5a5a7a]" />}
        </div>
        <div>
          <div className="text-sm font-medium text-[#e8e8f5]">Браузерный агент на ПК</div>
          <div className="text-xs text-[#5a5a7a]">
            {connected === null ? 'Проверка...' : connected
              ? 'Подключён — дирижёр может управлять браузером'
              : 'Не подключён — запусти desktop_agent.py на своём ПК'}
          </div>
        </div>
      </div>
      <button onClick={check} disabled={checking}
        className="text-xs px-3 py-1.5 rounded-lg border border-[#1c1c30] text-[#5a5a7a] hover:text-[#e8e8f5] transition flex items-center gap-1.5 disabled:opacity-50">
        {checking ? <Loader className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />} Обновить
      </button>
    </div>
  )
}

function StepList({ steps }) {
  if (!steps?.length) return null
  return (
    <div className="mt-4 space-y-1.5">
      {steps.map((s, i) => (
        <div key={i} className="flex items-start gap-2 text-xs bg-[#0d0d1a] rounded-lg px-3 py-2">
          <span className="text-violet-400 font-mono flex-shrink-0">{i + 1}.</span>
          <div className="min-w-0">
            <span className="text-cyan-300 font-medium">{s.action}</span>
            {s.thought && <span className="text-[#7a7a9a]"> — {s.thought}</span>}
            {s.input?.task && <div className="text-[#5a5a7a] truncate">{s.input.task}</div>}
            {'result_ok' in s && (
              <span className={s.result_ok ? 'text-green-400' : 'text-red-400'}>
                {s.result_ok ? ' ✓' : ' ✕'}
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

function ResultBanner({ result }) {
  if (!result) return null
  const ok = result.ok && (result.status === 'done' || result.status === undefined)
  const needsInput = result.status === 'needs_input'
  return (
    <div className={`mt-4 rounded-xl px-4 py-3 text-sm border ${
      needsInput ? 'bg-amber-500/8 border-amber-500/30 text-amber-300'
      : ok ? 'bg-green-500/8 border-green-500/30 text-green-300'
      : 'bg-red-500/8 border-red-500/30 text-red-300'}`}>
      <div className="flex items-center gap-2 font-medium">
        {ok ? <CheckCircle className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
        {needsInput ? 'Нужен ваш ввод' : ok ? 'Готово' : 'Остановлено'}
      </div>
      <div className="mt-1 text-[#c0c0e0]">
        {result.summary || result.question || result.message || result.error || JSON.stringify(result).slice(0, 300)}
      </div>
    </div>
  )
}

export default function Director() {
  const [goal, setGoal] = useState('')
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null)

  const [task, setTask] = useState('')
  const [startUrl, setStartUrl] = useState('')
  const [bRunning, setBRunning] = useState(false)
  const [bResult, setBResult] = useState(null)

  const runDirector = async () => {
    if (!goal.trim()) return
    setRunning(true); setResult(null)
    try { const r = await automation.director({ goal }); setResult(r.data) }
    catch (e) { setResult({ ok: false, error: e.response?.data?.error || e.message }) }
    setRunning(false)
  }

  const runBrowser = async () => {
    if (!task.trim()) return
    setBRunning(true); setBResult(null)
    try { const r = await desktop.runAgent({ task, start_url: startUrl || undefined }); setBResult(r.data) }
    catch (e) { setBResult({ ok: false, error: e.response?.data?.error || e.message }) }
    setBRunning(false)
  }

  const examples = [
    'Собери цены 5 конкурентов по доставке еды и пришли сводку',
    'Опубликуй пост про скидку 20% в Instagram и VK',
    'Сделай Reels с аватаром про наш новый продукт',
  ]

  return (
    <div className="max-w-3xl">
      <div className="mb-6">
        <h1 className="text-xl font-bold gradient-text flex items-center gap-2">
          <Bot className="w-5 h-5 text-violet-400" /> Marketing Director
        </h1>
        <p className="text-xs text-[#5a5a7a] mt-1">Поставь цель словами — Claude сам всё сделает через агентов</p>
      </div>

      <AgentStatus />

      <FactoryPanel />

      {/* Director */}
      <div className="card p-5 mb-5">
        <div className="flex items-center gap-2 mb-3">
          <Sparkles className="w-4 h-4 text-violet-400" />
          <span className="font-semibold text-sm">Цель для дирижёра</span>
        </div>
        <textarea value={goal} onChange={e => setGoal(e.target.value)} rows={3}
          placeholder="Напр.: Запусти 3 Reels по нашей нише и опубликуй в Instagram и VK на этой неделе"
          className="w-full bg-[#0d0d1a] border border-[#1c1c30] rounded-lg px-3 py-2 text-sm text-[#e8e8f5] placeholder-[#5a5a7a] focus:border-violet-500 outline-none resize-none" />
        <div className="flex flex-wrap gap-1.5 mt-2">
          {examples.map(ex => (
            <button key={ex} onClick={() => setGoal(ex)}
              className="text-[11px] px-2 py-1 rounded-full bg-[#111120] text-[#7a7a9a] hover:text-violet-300 border border-[#1c1c30] transition">
              {ex}
            </button>
          ))}
        </div>
        <button onClick={runDirector} disabled={running || !goal.trim()}
          className="btn-primary mt-3 flex items-center gap-2 disabled:opacity-50">
          {running ? <Loader className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          {running ? 'Дирижёр работает...' : 'Запустить'}
        </button>
        <ResultBanner result={result} />
        <StepList steps={result?.steps} />
      </div>

      {/* Direct browser task */}
      <div className="card p-5">
        <div className="flex items-center gap-2 mb-3">
          <Globe className="w-4 h-4 text-cyan-400" />
          <span className="font-semibold text-sm">Прямая задача браузерному агенту</span>
        </div>
        <input value={startUrl} onChange={e => setStartUrl(e.target.value)}
          placeholder="Стартовый URL (опц.): https://www.olx.ua"
          className="w-full bg-[#0d0d1a] border border-[#1c1c30] rounded-lg px-3 py-2 text-sm text-[#e8e8f5] placeholder-[#5a5a7a] focus:border-cyan-500 outline-none mb-2 font-mono" />
        <textarea value={task} onChange={e => setTask(e.target.value)} rows={2}
          placeholder="Что сделать в браузере, напр.: открой моё объявление на OLX и обнови цену на 5000"
          className="w-full bg-[#0d0d1a] border border-[#1c1c30] rounded-lg px-3 py-2 text-sm text-[#e8e8f5] placeholder-[#5a5a7a] focus:border-cyan-500 outline-none resize-none" />
        <button onClick={runBrowser} disabled={bRunning || !task.trim()}
          className="mt-3 px-4 py-2 rounded-lg bg-cyan-600/20 text-cyan-300 border border-cyan-500/30 hover:bg-cyan-600/30 transition flex items-center gap-2 text-sm disabled:opacity-50">
          {bRunning ? <Loader className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          {bRunning ? 'Агент работает...' : 'Выполнить'}
        </button>
        <ResultBanner result={bResult} />
        <StepList steps={bResult?.steps} />
      </div>
    </div>
  )
}
