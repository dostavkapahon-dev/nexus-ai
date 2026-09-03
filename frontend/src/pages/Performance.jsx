import React, { useState, useEffect } from 'react'
import { TrendingUp, TrendingDown, RefreshCw, Loader, Brain, Eye, Heart } from 'lucide-react'
import { performance as perfApi } from '../lib/api'

const PERIODS = [{ d: 7, l: '7 дней' }, { d: 30, l: '30 дней' }, { d: 90, l: '90 дней' }]

export default function Performance() {
  const [data, setData] = useState(null)
  const [best, setBest] = useState([])
  const [worst, setWorst] = useState([])
  const [days, setDays] = useState(30)
  const [busy, setBusy] = useState('')

  const load = async () => {
    setBusy('load')
    try {
      const [a, b, c] = await Promise.all([
        perfApi.overview(days), perfApi.top(days, 5, false), perfApi.top(days, 3, true),
      ])
      setData(a.data); setBest(b.data?.posts || []); setWorst(c.data?.posts || [])
    } catch {}
    setBusy('')
  }
  useEffect(() => { load() }, [days])

  const collect = async () => {
    setBusy('collect')
    try {
      const r = await perfApi.collect()
      alert(`Обновлено публикаций: ${r.data?.updated ?? 0}`)
    } catch (e) { alert('Ошибка: ' + e.message) }
    setBusy(''); load()
  }

  const learn = async () => {
    setBusy('learn')
    try {
      const r = await perfApi.learn(days)
      alert(r.data?.ok ? `Уроков извлечено: ${r.data.learned}` : (r.data?.reason || r.data?.error))
    } catch (e) { alert('Ошибка: ' + e.message) }
    setBusy('')
  }

  return (
    <div className="max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-5 flex-wrap gap-2">
        <div>
          <h1 className="text-xl font-bold gradient-text flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-green-400" /> Результаты публикаций
          </h1>
          <p className="text-xs text-[#5a5a7a] mt-1">
            Реальные метрики площадок — на них учится агент
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          {PERIODS.map(p => (
            <button key={p.d} onClick={() => setDays(p.d)}
              className={`text-xs px-3 py-1.5 rounded-lg border transition ${days === p.d
                ? 'bg-violet-600/20 text-violet-300 border-violet-500/30'
                : 'bg-[#0d0d1a] text-[#7a7a9a] border-[#1c1c30]'}`}>{p.l}</button>
          ))}
          <button onClick={collect} disabled={!!busy}
            className="text-xs px-3 py-1.5 rounded-lg bg-[#0d0d1a] border border-[#1c1c30] text-[#c0c0e0] disabled:opacity-50 flex items-center gap-1.5">
            {busy === 'collect' ? <Loader className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
            Собрать метрики
          </button>
          <button onClick={learn} disabled={!!busy}
            className="text-xs px-3 py-1.5 rounded-lg bg-violet-600/20 text-violet-300 border border-violet-500/30 disabled:opacity-50 flex items-center gap-1.5">
            <Brain className="w-3 h-3" /> Обучить агента
          </button>
        </div>
      </div>

      {data && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
          <Stat label="Публикаций" value={data.posts} />
          <Stat label="Просмотров" value={(data.views || 0).toLocaleString('ru')} icon={<Eye className="w-3 h-3" />} />
          <Stat label="Лайков" value={(data.likes || 0).toLocaleString('ru')} icon={<Heart className="w-3 h-3" />} />
          <Stat label="Средний ER" value={`${data.avg_engagement_rate}%`} />
          <Stat label="Провалов" value={data.failed} danger={data.failed > 0} />
        </div>
      )}

      {data?.by_platform?.length > 0 && (
        <div className="card p-4 mb-4">
          <div className="text-sm font-medium text-[#e8e8f5] mb-2">По площадкам</div>
          {data.by_platform.map(p => (
            <div key={p.platform} className="flex items-center justify-between text-xs py-1.5 border-b border-[#1c1c30] last:border-0">
              <span className="text-[#c0c0e0] capitalize">{p.platform}</span>
              <span className="text-[#9a9ac0]">
                {p.posts} постов · {p.views.toLocaleString('ru')} просмотров · ER {p.avg_er}%
              </span>
            </div>
          ))}
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-4">
        <PostList title="Что сработало" posts={best} icon={<TrendingUp className="w-4 h-4 text-green-400" />} good />
        <PostList title="Что не сработало" posts={worst} icon={<TrendingDown className="w-4 h-4 text-red-400" />} />
      </div>

      {best.length === 0 && (
        <div className="card p-6 text-center text-sm text-[#5a5a7a] mt-4">
          Метрик пока нет. Они собираются автоматически каждый день в 23:00 —
          или нажми «Собрать метрики».
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, icon, danger }) {
  return (
    <div className="card p-3">
      <div className="text-[10px] text-[#5a5a7a] flex items-center gap-1">{icon}{label}</div>
      <div className={`text-lg font-semibold mt-0.5 ${danger ? 'text-red-400' : 'text-[#e8e8f5]'}`}>{value}</div>
    </div>
  )
}

function PostList({ title, posts, icon, good }) {
  return (
    <div className="card p-4">
      <div className="text-sm font-medium text-[#e8e8f5] mb-2 flex items-center gap-2">{icon}{title}</div>
      {posts.length === 0 && <div className="text-xs text-[#5a5a7a]">Пока нет данных</div>}
      {posts.map(p => (
        <div key={p.id} className="py-2 border-b border-[#1c1c30] last:border-0">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs text-[#e8e8f5] truncate">{p.topic || '—'}</span>
            <span className={`text-xs shrink-0 ${good ? 'text-green-400' : 'text-red-400'}`}>
              ER {p.engagement_rate}%
            </span>
          </div>
          {p.hook && <div className="text-[11px] text-[#7a7a9a] mt-0.5 truncate">хук: {p.hook}</div>}
          <div className="text-[10px] text-[#5a5a7a] mt-0.5">
            {p.platform} · {p.format || 'пост'} · {(p.views || 0).toLocaleString('ru')} просмотров
            {p.url && <> · <a href={p.url} target="_blank" rel="noreferrer" className="text-cyan-400 hover:underline">открыть</a></>}
          </div>
        </div>
      ))}
    </div>
  )
}
