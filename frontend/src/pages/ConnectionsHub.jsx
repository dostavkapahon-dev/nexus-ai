import React, { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Plug } from 'lucide-react'
import Social from './Social'
import TelegramConnect from './TelegramConnect'
import Connections from './Connections'

// Все интеграции в одном разделе. До этого ключи и подключения вводились в пяти
// местах сразу (главная, «Ключи API», «Площадки», «Telegram-бот», мастер канала),
// и пользователь не знал, какое из них настоящее.
const TABS = [
  { id: 'platforms', label: 'Площадки', El: Social },
  { id: 'telegram', label: 'Telegram-канал', El: TelegramConnect },
  { id: 'keys', label: 'Ключи и доступы', El: Connections },
]

export default function ConnectionsHub() {
  const [params, setParams] = useSearchParams()
  const [tab, setTab] = useState(() => {
    const t = params.get('tab')
    return TABS.some(x => x.id === t) ? t : 'platforms'
  })
  const select = (id) => { setTab(id); setParams({ tab: id }, { replace: true }) }
  const Active = TABS.find(t => t.id === tab).El

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center">
          <Plug className="w-5 h-5 text-white" />
        </div>
        <div>
          <h1 className="text-xl font-bold">Подключения</h1>
          <p className="text-sm text-[#5a5a7a]">Площадки, каналы и доступы — всё в одном месте</p>
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
