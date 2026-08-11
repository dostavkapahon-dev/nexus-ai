import React, { useState, useEffect } from 'react'
import { HeartPulse, RefreshCw, Loader, Clock, AlertTriangle } from 'lucide-react'
import { system } from '../lib/api'

// «Молчит» — отдельный статус, а не разновидность «работает»: агент, не
// вызывавшийся сутки, чаще всего означает сломанный джоб, и это надо видеть.
const AGENT = {
  online:   { label: 'Работает', cls: 'text-green-400 bg-green-500/10' },
  degraded: { label: 'С ошибками', cls: 'text-amber-400 bg-amber-500/10' },
  silent:   { label: 'Молчит', cls: 'text-[#7a7a9a] bg-[#1c1c30]' },
}

const VERDICT = {
  ok:       { label: 'Система в порядке', cls: 'text-green-400 border-green-500/25 bg-green-500/8' },
  degraded: { label: 'Есть проблемы',     cls: 'text-amber-400 border-amber-500/25 bg-amber-500/8' },
  broken:   { label: 'Система сломана',   cls: 'text-red-400 border-red-500/25 bg-red-500/8' },
}

const fmt = (iso) => (iso ? iso.slice(0, 16).replace('T', ' ') : '—')

export default function Health() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try { setData((await system.health()).data) } catch { /* состояние покажет пустой экран */ }
    setLoading(false)
  }

  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t) }, [])

  const v = VERDICT[data?.verdict] || VERDICT.degraded

  return (
    <div className="max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-5 flex-wrap gap-2">
        <div>
          <h1 className="text-xl font-bold gradient-text flex items-center gap-2">
            <HeartPulse className="w-5 h-5 text-violet-400" /> Здоровье системы
          </h1>
          <p className="text-xs text-[#5a5a7a] mt-1">
            Агенты, площадки, планировщик, расходы и ошибки — в одном месте
          </p>
        </div>
        <button onClick={load}
          className="text-xs px-3 py-1.5 rounded-lg bg-[#0d0d1a] border border-[#1c1c30] text-[#c0c0e0] flex items-center gap-1.5">
          {loading ? <Loader className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />} Обновить
        </button>
      </div>

      {!data && (
        <div className="text-center text-xs text-[#5a5a7a] py-10 border border-[#1c1c30] rounded-xl bg-[#0d0d1a]">
          Загрузка состояния…
        </div>
      )}

      {data && (
        <>
          <div className={`border rounded-xl px-4 py-3 mb-4 text-sm font-medium ${v.cls}`}>
            {v.label}
            <span className="text-[11px] font-normal opacity-70 ml-2">
              обновлено {fmt(data.generated_at)} UTC
            </span>
          </div>

          {data.ai && !data.ai.available && (
            <div className="border border-cyan-500/25 bg-cyan-500/8 rounded-xl px-4 py-3 mb-4">
              <div className="text-sm text-cyan-300 font-medium">Режим «только управление»</div>
              <div className="text-[11px] text-[#9a9ac0] mt-1">
                Ни один ИИ-провайдер не подключён. Публикация, очередь, задачи, метрики
                и отчёты работают. Генерация текста и видео — недоступна, пока нет ключа.
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
            <Stat label="Задач за сутки" value={data.tasks?.total ?? 0} />
            <Stat label="Из них упало" value={data.tasks?.failed ?? 0}
                  warn={(data.tasks?.failed ?? 0) > 0} />
            <Stat label="Расход за сутки" value={`$${(data.costs?.day?.cost_usd ?? 0).toFixed(4)}`} />
            <Stat label="Бюджет использован" value={`${data.costs?.budget?.used_pct ?? 0}%`}
                  warn={data.costs?.budget?.alert} />
          </div>

          <Section title="Агенты">
            {(data.agents || []).length === 0 && <Empty>Вызовов моделей пока не было.</Empty>}
            <div className="space-y-1.5">
              {(data.agents || []).map((a) => {
                const st = AGENT[a.status] || AGENT.silent
                return (
                  <div key={a.agent} className="flex items-center justify-between gap-3 flex-wrap
                                                border border-[#1c1c30] rounded-lg bg-[#0d0d1a] px-3 py-2">
                    <div className="flex items-center gap-2">
                      <span className={`text-[11px] px-2 py-0.5 rounded-md ${st.cls}`}>{st.label}</span>
                      <span className="text-xs text-[#c0c0e0]">{a.agent}</span>
                    </div>
                    <div className="text-[11px] text-[#5a5a7a] flex gap-3 flex-wrap">
                      <span>успех {a.success_rate}%</span>
                      <span>вызовов {a.calls}</span>
                      <span>${a.cost_usd.toFixed(4)}</span>
                      <span className="flex items-center gap-1"><Clock className="w-3 h-3" /> {fmt(a.last_run)}</span>
                    </div>
                  </div>
                )
              })}
            </div>
          </Section>

          <Section title="Площадки">
            <div className="space-y-1.5">
              {(data.social || []).map((s) => (
                <div key={s.platform} className="flex items-center justify-between gap-3 flex-wrap
                                                 border border-[#1c1c30] rounded-lg bg-[#0d0d1a] px-3 py-2">
                  <div className="flex items-center gap-2">
                    <span className={`text-[11px] px-2 py-0.5 rounded-md ${
                      s.ok ? 'text-green-400 bg-green-500/10' : 'text-[#7a7a9a] bg-[#1c1c30]'}`}>
                      {s.ok ? 'Подключено' : 'Не настроено'}
                    </span>
                    <span className="text-xs text-[#c0c0e0]">{s.platform}</span>
                  </div>
                  <div className="text-[11px] text-[#5a5a7a] flex gap-3 flex-wrap">
                    {s.can_publish !== undefined && <span>публикация: {s.can_publish ? 'да' : 'нет'}</span>}
                    {s.expires_at && <span>токен до {fmt(s.expires_at)}</span>}
                    {s.error && <span className="text-red-400/90">{String(s.error).slice(0, 80)}</span>}
                  </div>
                </div>
              ))}
            </div>
          </Section>

          <Section title="Планировщик">
            {!data.scheduler?.running && (
              <Empty>Планировщик не запущен — расписание не работает.</Empty>
            )}
            {data.scheduler?.running && (
              <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                {(data.scheduler.jobs || []).map((j) => (
                  <div key={j.id} className="border border-[#1c1c30] rounded-lg bg-[#0d0d1a] px-3 py-2">
                    <div className="text-xs text-[#c0c0e0]">{j.id}</div>
                    <div className="text-[11px] text-[#5a5a7a]">след. запуск: {fmt(j.next_run)}</div>
                  </div>
                ))}
              </div>
            )}
          </Section>

          <Section title="Ошибки за сутки">
            {(data.errors?.total ?? 0) === 0 && <Empty>Ошибок нет.</Empty>}
            <div className="space-y-1.5">
              {(data.errors?.tasks || []).map((t) => (
                <ErrorRow key={t.id} title={`${t.kind} · ${t.id}`} text={t.error} />
              ))}
              {(data.errors?.agents || []).map((a, i) => (
                <ErrorRow key={i} title={`${a.agent} / ${a.model || '—'}`} text={a.error} />
              ))}
            </div>
          </Section>
        </>
      )}
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div className="mb-5">
      <div className="text-xs font-medium text-[#9a9ac0] mb-2">{title}</div>
      {children}
    </div>
  )
}

function Stat({ label, value, warn }) {
  return (
    <div className={`border rounded-xl px-3 py-2.5 ${
      warn ? 'border-amber-500/25 bg-amber-500/5' : 'border-[#1c1c30] bg-[#0d0d1a]'}`}>
      <div className="text-[10px] text-[#5a5a7a]">{label}</div>
      <div className="text-lg font-bold text-[#c0c0e0]">{value}</div>
    </div>
  )
}

function Empty({ children }) {
  return <div className="text-[11px] text-[#5a5a7a] border border-[#1c1c30] rounded-lg bg-[#0d0d1a] px-3 py-2.5">{children}</div>
}

function ErrorRow({ title, text }) {
  return (
    <div className="border border-red-500/15 bg-red-500/5 rounded-lg px-3 py-2">
      <div className="text-[11px] text-[#c0c0e0] flex items-center gap-1.5">
        <AlertTriangle className="w-3 h-3 text-red-400" /> {title}
      </div>
      <div className="text-[11px] text-red-400/90 mt-0.5">{text}</div>
    </div>
  )
}
