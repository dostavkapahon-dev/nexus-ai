import React from 'react'
import { Routes, Route, NavLink, Navigate } from 'react-router-dom'
import { Zap, LayoutDashboard, PlusCircle, List, Rocket, Cpu, BarChart2, Plug, LogOut, Bot } from 'lucide-react'
import Control from './pages/Control'
import Dashboard from './pages/Dashboard'
import NewNiche from './pages/NewNiche'
import Queue from './pages/Queue'
import PromptStudio from './pages/PromptStudio'
import Connections from './pages/Connections'
import Analytics from './pages/Analytics'
import Director from './pages/Director'
import Login from './pages/Login'
import { auth } from './lib/api'

const NAV = [
  { to: '/',            icon: Rocket,          label: 'Центр управления' },
  { to: '/director',    icon: Bot,             label: 'Дирижёр' },
  { to: '/queue',       icon: List,            label: 'Очередь' },
  { to: '/connections', icon: Plug,            label: 'Ключи API' },
  { to: '/dash',        icon: LayoutDashboard, label: 'Ниши' },
]

function RequireAuth({ children }) {
  return localStorage.getItem('nx_token') ? children : <Navigate to="/login" replace />
}

function Sidebar() {
  const logout = () => { auth.logout(); window.location.href = '/login' }
  return (
    <aside className="w-52 border-r border-[#1c1c30] flex flex-col fixed h-full z-10 bg-[#09091a]">
      <div className="px-5 py-5 border-b border-[#1c1c30]">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-600 to-cyan-500 flex items-center justify-center">
            <Zap className="w-4 h-4 text-white" />
          </div>
          <div>
            <div className="font-bold text-sm tracking-wide gradient-text">NEXUS AI</div>
            <div className="text-[10px] text-[#5a5a7a] mt-px">Контент 24/7</div>
          </div>
        </div>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {NAV.map(({ to, icon: Icon, label }) => (
          <NavLink key={to} to={to} end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all ${
                isActive
                  ? 'bg-violet-600/15 text-violet-300 border border-violet-500/25 font-medium'
                  : 'text-[#5a5a7a] hover:text-[#c0c0e0] hover:bg-[#111120]'
              }`
            }
          >
            <Icon className="w-4 h-4 flex-shrink-0" />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="px-3 py-4 border-t border-[#1c1c30]">
        <button onClick={logout}
          className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs text-[#5a5a7a] hover:text-red-400 hover:bg-red-500/8 transition w-full">
          <LogOut className="w-3.5 h-3.5" /> Выйти
        </button>
        <div className="text-[10px] text-[#3a3a55] text-center mt-2">v2.0 · Pakhon</div>
      </div>
    </aside>
  )
}

function Layout() {
  return (
    <div className="flex min-h-screen bg-[#07070f]">
      <Sidebar />
      <main className="flex-1 ml-52 p-6 overflow-auto min-h-screen">
        <Routes>
          <Route path="/"            element={<Control />} />
          <Route path="/dash"        element={<Dashboard />} />
          <Route path="/director"    element={<Director />} />
          <Route path="/new"         element={<NewNiche />} />
          <Route path="/queue"       element={<Queue />} />
          <Route path="/analytics"   element={<Analytics />} />
          <Route path="/prompts"     element={<PromptStudio />} />
          <Route path="/connections" element={<Connections />} />
        </Routes>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/*" element={<RequireAuth><Layout /></RequireAuth>} />
    </Routes>
  )
}
