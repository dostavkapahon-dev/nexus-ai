import React from 'react'
import { Routes, Route, NavLink } from 'react-router-dom'
import { Zap, LayoutDashboard, PlusCircle, List, Settings, Cpu, BarChart2, Plug } from 'lucide-react'
import Dashboard from './pages/Dashboard'
import NewNiche from './pages/NewNiche'
import Queue from './pages/Queue'
import PromptStudio from './pages/PromptStudio'
import Connections from './pages/Connections'
import Analytics from './pages/Analytics'

const NAV = [
  { to: '/', icon: LayoutDashboard, label: 'Дашборд' },
  { to: '/new', icon: PlusCircle, label: 'Новая ниша' },
  { to: '/queue', icon: List, label: 'Очередь' },
  { to: '/analytics', icon: BarChart2, label: 'Аналитика' },
  { to: '/prompts', icon: Cpu, label: 'Промпты' },
  { to: '/connections', icon: Plug, label: 'Подключения' },
]

export default function App() {
  return (
    <div className="flex min-h-screen bg-nexus-bg">
      <aside className="w-56 border-r border-nexus-border flex flex-col fixed h-full z-10">
        <div className="p-4 border-b border-nexus-border flex items-center gap-2">
          <Zap className="text-purple-400 w-6 h-6" />
          <span className="font-bold text-lg bg-gradient-to-r from-purple-400 to-cyan-400 bg-clip-text text-transparent">
            NEXUS AI
          </span>
        </div>
        <nav className="flex-1 p-3 space-y-1">
          {NAV.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all ${
                  isActive
                    ? 'bg-purple-600/20 text-purple-300 border border-purple-500/30'
                    : 'text-nexus-muted hover:text-nexus-text hover:bg-nexus-card'
                }`
              }
            >
              <Icon className="w-4 h-4" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="p-3 border-t border-nexus-border">
          <div className="text-xs text-nexus-muted text-center">v1.0.0 · NEXUS AI</div>
        </div>
      </aside>

      <main className="flex-1 ml-56 p-6 overflow-auto min-h-screen">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/new" element={<NewNiche />} />
          <Route path="/queue" element={<Queue />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/prompts" element={<PromptStudio />} />
          <Route path="/connections" element={<Connections />} />
        </Routes>
      </main>
    </div>
  )
}
