import React, { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Calendar } from 'lucide-react'
import Queue from './Queue'
import Publishing from './Publishing'
import Tasks from './Tasks'

// Три очереди — контент-план, публикации и фоновые задачи — для пользователя
// одна сущность «что в работе». Раньше это были три пункта меню, между которыми
// приходилось гадать, где искать свой пост.
const TABS = [
  { id: 'plan', label: 'Контент-план', El: Queue },
  { id: 'publications', label: 'Публикации', El: Publishing },
  { id: 'tasks', label: 'Задачи', El: Tasks },
]

export default function Content() {
  const [params, setParams] = useSearchParams()
  const [tab, setTab] = useState(() => {
    const t = params.get('tab')
    return TABS.some(x => x.id === t) ? t : 'plan'
  })
  const select = (id) => { setTab(id); setParams({ tab: id }, { replace: true }) }
  const Active = TABS.find(t => t.id === tab).El

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-600 to-cyan-500 flex items-center justify-center">
          <Calendar className="w-5 h-5 text-white" />
        </div>
        <div>
          <h1 className="text-xl font-bold">Контент</h1>
          <p className="text-sm text-[#5a5a7a]">План, публикации и фоновые задачи</p>
        </div>
      </div>

      <div className="flex gap-2 border-b border-[#1c1c30] pb-2">
        {TABS.map(t => (
          <button key={t.id} onClick={() => select(t.id)}
            className={`px-3 py-1.5 rounded-lg text-sm transition ${
              tab === t.id ? 'bg-violet-600/15 text-violet-300 border border-violet-500/25'
                           : 'text-[#5a5a7a] hover:text-[#c0c0e0]'}`}>
            {t.label}
          </button>
        ))}
      </div>

      <Active />
    </div>
  )
}
