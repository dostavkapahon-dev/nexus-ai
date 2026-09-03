import React, { useEffect, useState } from 'react'
import { Activity, CheckCircle, XCircle, AlertTriangle, Loader, Send } from 'lucide-react'
import { Link } from 'react-router-dom'
import { system } from '../lib/api'

// Главная по ТЗ отвечает на пять вопросов и молчит про остальное:
// система жива? что подключено? что делается сейчас? сколько вышло? что сломалось?
// Всё остальное живёт в своих разделах — иначе главная снова станет свалкой.

const Card = ({ title, children, to }) => {
  const body = (
    <div className="bg-[#0d0d1c] border border-[#1c1c30] rounded-xl p-5 h-full hover:border-[#2a2a45] transition">
      <div className="text-xs uppercase tracking-wider text-[#5a5a7a] mb-3">{title}</div>
      {children}
    </div>
  )
  return to ? <Link to={to}>{body}</Link> : body
}

const Dot = ({ ok }) => (
  <span className={`inline-block w-2 h-2 rounded-full ${ok ? 'bg-emerald-400' : 'bg-red-400'}`} />
)

export default function Home() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  const load = async () => {
    try {
      const { data } = await system.summary()
      setData(data); setError('')
    } catch (e) {
      setError(e.response?.data?.detail || 'сервер не отвечает')
    }
  }

  useEffect(() => {
    load()
    // Раз в 20 секунд: главная должна быть свежей, но не долбить сервер каждые 4с,
    // как это делал прежний пульт.
    const t = setInterval(load, 20000)
    return () => clearInterval(t)
  }, [])

  if (error) {
    return (
      <div className="max-w-3xl">
        <div className="bg-red-500/8 border border-red-500/25 text-red-300 rounded-xl p-5 text-sm">
          <XCircle className="w-4 h-4 inline mr-2" />Не удалось получить статус: {error}
        </div>
      </div>
    )
  }
  if (!data) {
    return <div className="text-[#5a5a7a] text-sm flex items-center gap-2">
      <Loader className="w-4 h-4 animate-spin" /> Загрузка…
    </div>
  }

  const task = data.current_task
  const connected = data.connections.filter(c => c.ok).length

  return (
    <div className="max-w-4xl space-y-5">
      <div>
        <h1 className="text-xl font-bold">Главная</h1>
        <p className="text-sm text-[#5a5a7a]">Общий статус системы</p>
      </div>

      {/* Без постоянной базы всё, что вводится в интерфейсе, исчезнет при
          следующем деплое. Молчать об этом — значит показывать настройки,
          которые не переживут ночь. */}
      {data.storage && !data.storage.persistent && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">
          <div className="text-sm font-medium text-amber-300">
            ⚠️ Постоянная база не подключена
          </div>
          <p className="text-xs text-[#c0c0e0] mt-1.5 leading-relaxed">
            {data.storage.warning}
          </p>
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-4">
        <Card title="Система">
          <div className="flex items-center gap-2 text-sm">
            <Dot ok={data.system.ok} />
            <span className="font-medium">Cloud Code — работает</span>
          </div>
          <div className="text-xs text-[#5a5a7a] mt-2">
            {data.system.ai_available
              ? `ИИ: ${data.system.providers.join(', ')}`
              : 'ИИ не подключён — доступны только прямые команды'}
          </div>
        </Card>

        <Card title="Подключения" to="/connections">
          <div className="text-sm space-y-1.5">
            {data.connections.length === 0 && <span className="text-[#5a5a7a]">нет площадок</span>}
            {data.connections.map(c => (
              <div key={c.platform} className="flex items-center gap-2 capitalize">
                <Dot ok={c.ok} />
                <span>{c.platform}</span>
                {!c.ok && c.configured && (
                  <span className="text-xs text-red-300/80 truncate">{c.error}</span>
                )}
                {!c.configured && <span className="text-xs text-[#5a5a7a]">не настроено</span>}
              </div>
            ))}
          </div>
          <div className="text-xs text-[#5a5a7a] mt-3">
            Подключено: {connected} из {data.connections.length}
          </div>
        </Card>

        <Card title="Задача" to="/hq">
          {task ? (
            <>
              <div className="text-sm font-medium truncate">{task.goal || task.kind}</div>
              <div className="text-xs text-[#5a5a7a] mt-1">
                {task.status}
                {task.percent !== null && task.percent !== undefined
                  ? ` — ${task.percent}%`
                  : ''}
              </div>
              {task.steps_total > 0 && (
                <div className="h-1.5 bg-[#12122a] rounded-full mt-3 overflow-hidden">
                  <div className="h-full bg-violet-500 rounded-full"
                    style={{ width: `${task.percent || 0}%` }} />
                </div>
              )}
            </>
          ) : (
            <div className="text-sm text-[#5a5a7a]">
              <Activity className="w-4 h-4 inline mr-1.5" />Сейчас ничего не выполняется
            </div>
          )}
        </Card>

        <Card title="Контент" to="/content">
          <div className="text-2xl font-bold">{data.published_today}</div>
          <div className="text-xs text-[#5a5a7a] mt-1">публикаций за сутки</div>
          {Object.entries(data.publications_today || {})
            .filter(([s]) => s !== 'published')
            .map(([status, n]) => (
              <div key={status} className="text-xs text-[#5a5a7a] mt-1.5">
                <Send className="w-3 h-3 inline mr-1" />{status}: {n}
              </div>
            ))}
        </Card>
      </div>

      <Card title="Ошибки">
        {data.errors === 0 ? (
          <div className="text-sm text-emerald-300 flex items-center gap-2">
            <CheckCircle className="w-4 h-4" /> 0 — за сутки ничего не падало
          </div>
        ) : (
          <Link to="/hq" className="text-sm text-amber-300 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4" /> {data.errors} за сутки — посмотреть
          </Link>
        )}
      </Card>
    </div>
  )
}
