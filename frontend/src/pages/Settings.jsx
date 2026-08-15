import React, { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Settings as Cog } from 'lucide-react'
import AgentSetup from './AgentSetup'
import PromptStudio from './PromptStudio'
import Cost from './Cost'
import Health from './Health'

// Настройки системы одним разделом. Раньше это были четыре пункта меню
// (агент, промпты, расходы, здоровье), между которыми не было видимой разницы
// для пользователя — все четыре про «как система настроена и как себя чувствует».
const TABS = [
  { id: 'agent', label: 'Агент и бренд', El: AgentSetup },
  { id: 'prompts', label: 'Промпты', El: PromptStudio },
  { id: 'cost', label: 'Расходы', El: Cost },
  { id: 'health', label: 'Здоровье', El: Health },
]

export default function Settings() {
  const [params, setParams] = useSearchParams()
  const [tab, setTab] = useState(() => {
    const t = params.get('tab')
    return TABS.some(x => x.id === t) ? t : 'agent'
  })
  const select = (id) => { setTab(id); setParams({ tab: id }, { replace: true }) }
  const Active = TABS.find(t => t.id === tab).El

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-slate-600 to-slate-400 flex items-center justify-center">
          <Cog className="w-5 h-5 text-white" />
        </div>
        <div>
          <h1 className="text-xl font-bold">Настройки</h1>
          <p className="text-sm text-[#5a5a7a]">Агент, промпты, расходы и состояние системы</p>
        </div>
      </div>

      <div className="flex gap-2 flex-wrap border-b border-[#1c1c30] pb-2">
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
