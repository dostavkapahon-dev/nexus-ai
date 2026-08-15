import React from 'react'
import { Routes, Route, NavLink, Navigate } from 'react-router-dom'
import { Home as HomeIcon, Zap, Activity, Plug, Bot, Calendar, Settings as Cog, KeyRound, LogOut } from 'lucide-react'
import Home from './pages/Home'
import CommandCenter from './pages/CommandCenter'
import ConnectionsHub from './pages/ConnectionsHub'
import Agents from './pages/Agents'
import Content from './pages/Content'
import Settings from './pages/Settings'
import Credentials from './pages/Credentials'
import Research from './pages/Research'
import Strategy from './pages/Strategy'
import Performance from './pages/Performance'
import Login from './pages/Login'
import { auth } from './lib/api'

// Семь разделов вместо восемнадцати. Всё, что раньше было отдельным пунктом,
// живёт внутри одного из них: очереди — в «Контенте», ключи и площадки —
// в «Подключениях», промпты, расходы и здоровье — в «Настройках».
const NAV = [
  { to: '/',            icon: HomeIcon, label: 'Главная' },
  { to: '/hq',          icon: Activity, label: 'Командный центр' },
  { to: '/connections', icon: Plug,     label: 'Подключения' },
  { to: '/agents',      icon: Bot,      label: 'Агенты' },
  { to: '/content',     icon: Calendar, label: 'Контент' },
  { to: '/settings',    icon: Cog,      label: 'Настройки' },
  { to: '/credentials', icon: KeyRound, label: 'API / Credentials' },
]

// Старые адреса остаются рабочими: они у пользователя в закладках и в ссылках
// из Telegram. Убрать можно, когда станет видно, что по ним больше не ходят.
const LEGACY_REDIRECTS = [
  ['/dash', '/'],
  ['/health', '/settings?tab=health'],
  ['/cost', '/settings?tab=cost'],
  ['/prompts', '/settings?tab=prompts'],
  ['/agent', '/settings?tab=agent'],
  ['/new', '/settings'],
  ['/analytics', '/'],
  ['/director', '/hq'],
  ['/queue', '/content?tab=plan'],
  ['/publishing', '/content?tab=publications'],
  ['/tasks', '/content?tab=tasks'],
  ['/social', '/connections?tab=platforms'],
  ['/bot', '/connections?tab=telegram'],
  ['/telegram', '/connections?tab=telegram'],
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
          <Route path="/"            element={<Home />} />
          <Route path="/hq"          element={<CommandCenter />} />
          <Route path="/connections" element={<ConnectionsHub />} />
          <Route path="/agents"      element={<Agents />} />
          <Route path="/content"     element={<Content />} />
          <Route path="/settings"    element={<Settings />} />
          <Route path="/credentials" element={<Credentials />} />
          {/* Не в меню, но со своей ценностью и ссылками из командного центра. */}
          <Route path="/research"    element={<Research />} />
          <Route path="/strategy"    element={<Strategy />} />
          <Route path="/performance" element={<Performance />} />
          {LEGACY_REDIRECTS.map(([from, to]) => (
            <Route key={from} path={from} element={<Navigate to={to} replace />} />
          ))}
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
