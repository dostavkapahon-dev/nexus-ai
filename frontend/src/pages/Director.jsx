import React, { useState, useEffect } from 'react'
import { Bot, Send, Loader, Monitor, MonitorOff, Globe, Sparkles, CheckCircle, XCircle, RefreshCw } from 'lucide-react'
import { automation, desktop } from '../lib/api'

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
