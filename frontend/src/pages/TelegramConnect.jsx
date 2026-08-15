import React, { useState, useEffect } from 'react'
import { Send, CheckCircle, XCircle, Loader, Star, Trash2, RefreshCw, ExternalLink } from 'lucide-react'
import { telegram, publishing } from '../lib/api'

// Мастер подключения канала: бот → канал → права → публикация → тест.
// Каждый шаг отвечает на свой вопрос, поэтому провал видно сразу и понятно,
// что чинить, — а не «пост не вышел, разбирайтесь».
const STEPS = [
  { id: 1, title: 'Подключение бота' },
  { id: 2, title: 'Выбор канала' },
  { id: 3, title: 'Проверка прав' },
  { id: 4, title: 'Проверка публикации' },
  { id: 5, title: 'Тестовая публикация' },
]

const Card = ({ children, className = '' }) => (
  <div className={`bg-[#0d0d1c] border border-[#1c1c30] rounded-xl p-5 ${className}`}>{children}</div>
)

const Btn = ({ children, onClick, disabled, busy, variant = 'primary', className = '' }) => {
  const styles = {
    primary: 'bg-violet-600 hover:bg-violet-500 text-white',
    ghost: 'bg-[#12122a] hover:bg-[#1a1a35] text-[#c0c0e0] border border-[#1c1c30]',
    danger: 'bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/25',
  }[variant]
  return (
    <button onClick={onClick} disabled={disabled || busy}
      className={`px-4 py-2 rounded-lg text-sm font-medium transition disabled:opacity-40 ${styles} ${className}`}>
      {busy ? <Loader className="w-4 h-4 animate-spin inline" /> : children}
    </button>
  )
}

const Note = ({ ok, children }) => (
  <div className={`flex gap-2 items-start text-sm mt-3 p-3 rounded-lg ${
    ok ? 'bg-emerald-500/8 text-emerald-300' : 'bg-red-500/8 text-red-300'}`}>
    {ok ? <CheckCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
        : <XCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />}
    <div>{children}</div>
  </div>
)

export default function TelegramConnect() {
  const [step, setStep] = useState(1)
  const [busy, setBusy] = useState('')
  const [token, setToken] = useState('')
  const [bot, setBot] = useState(null)
  const [found, setFound] = useState([])
  const [hint, setHint] = useState('')
  const [chatId, setChatId] = useState('')
  const [check, setCheck] = useState(null)
  const [test, setTest] = useState(null)
  const [channels, setChannels] = useState([])
  const [auto, setAuto] = useState(null)

  const load = async () => {
    try {
      const [{ data: st }, { data: a }] = await Promise.all([
        telegram.status(), publishing.autoGet(),
      ])
      setBot(st.bot?.ok ? st.bot : null)
      setChannels(st.channels || [])
      setAuto(a)
      if (st.bot?.ok && step === 1) setStep(st.channels?.length ? 5 : 2)
    } catch (e) { /* страница должна открываться даже без бэкенда */ }
  }
  useEffect(() => { load() }, [])

  const run = async (name, fn) => {
    setBusy(name)
    try { return await fn() }
    catch (e) { return { data: { ok: false, error: e.response?.data?.detail || e.message } } }
    finally { setBusy('') }
  }

  const connectBot = async () => {
    const { data } = await run('bot', () => telegram.botConnect(token))
    setBot(data)
    if (data.ok) setStep(2)
  }

  const discover = async () => {
    const { data } = await run('discover', () => telegram.discover())
    setFound(data.items || [])
    setHint(data.hint || data.error || '')
  }

  const doCheck = async (id) => {
    const target = id || chatId
    setChatId(target)
    const { data } = await run('check', () => telegram.check(target))
    setCheck(data)
    setTest(null)
    setStep(data.ok ? 4 : 3)
  }

  const doTest = async () => {
    const { data } = await run('test', () => telegram.test(chatId))
    setTest(data)
    if (data.ok) setStep(5)
  }

  const addChannel = async () => {
    const { data } = await run('add', () => telegram.add(chatId))
    if (data.ok) { await load(); setCheck(null); setTest(null); setChatId('') }
    else setCheck({ ...(check || {}), ok: false, error: data.error, hint: data.hint })
  }

  const setMode = async (platform, mode) => {
    const { data } = await run('mode', () => publishing.autoSet({ platforms: { [platform]: mode } }))
    if (data.ok) setAuto({ ...auto, platforms: data.platforms, enabled: data.enabled })
  }

  const toggleAuto = async () => {
    const { data } = await run('toggle', () => publishing.autoSet({ enabled: !auto?.enabled }))
    if (data.ok) setAuto({ ...auto, ...data })
  }

  return (
    <div className="max-w-4xl space-y-5">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-sky-500 to-blue-600 flex items-center justify-center">
          <Send className="w-5 h-5 text-white" />
        </div>
        <div>
          <h1 className="text-xl font-bold">Telegram — подключение канала</h1>
          <p className="text-sm text-[#5a5a7a]">Бот, канал, права, тестовая публикация</p>
        </div>
      </div>

      {/* Шаги */}
      <div className="flex gap-2 flex-wrap">
        {STEPS.map(s => (
          <div key={s.id}
            className={`px-3 py-1.5 rounded-lg text-xs border ${
              step >= s.id ? 'border-violet-500/40 bg-violet-600/15 text-violet-300'
                           : 'border-[#1c1c30] text-[#5a5a7a]'}`}>
            {s.id}. {s.title}
          </div>
        ))}
      </div>

      {/* Шаг 1 — бот */}
      <Card>
        <div className="font-semibold mb-1">1. Подключение бота</div>
        <p className="text-xs text-[#5a5a7a] mb-3">
          Создайте бота у <a className="text-violet-400 inline-flex items-center gap-1"
            href="https://t.me/BotFather" target="_blank" rel="noreferrer">@BotFather
            <ExternalLink className="w-3 h-3" /></a> и вставьте токен.
        </p>
        <div className="flex gap-2">
          <input value={token} onChange={e => setToken(e.target.value)} type="password"
            placeholder="123456789:AA..."
            className="flex-1 bg-[#09091a] border border-[#1c1c30] rounded-lg px-3 py-2 text-sm outline-none focus:border-violet-500/50" />
          <Btn onClick={connectBot} busy={busy === 'bot'} disabled={!token.trim()}>Подключить</Btn>
        </div>
        {bot && (bot.ok
          ? <Note ok>Бот подключён: <b>{bot.username}</b> {bot.name && `(${bot.name})`}</Note>
          : <Note>{bot.error}</Note>)}
      </Card>

      {/* Шаг 2 — канал */}
      <Card>
        <div className="flex items-center justify-between mb-1">
          <div className="font-semibold">2. Выбор канала</div>
          <Btn variant="ghost" onClick={discover} busy={busy === 'discover'}>
            <RefreshCw className="w-3.5 h-3.5 inline mr-1" /> Найти каналы
          </Btn>
        </div>
        <p className="text-xs text-[#5a5a7a] mb-3">
          Добавьте бота администратором в канал с правом «Публикация сообщений».
        </p>
        {found.length > 0 && (
          <div className="space-y-2 mb-3">
            {found.map(c => (
              <button key={c.chat_id} onClick={() => doCheck(c.chat_id)}
                className={`w-full text-left px-3 py-2 rounded-lg border text-sm transition ${
                  chatId === c.chat_id ? 'border-violet-500/40 bg-violet-600/10'
                                       : 'border-[#1c1c30] hover:bg-[#12122a]'}`}>
                <span className="font-medium">{c.title || c.chat_id}</span>
                <span className="text-[#5a5a7a] ml-2">{c.username || c.chat_id}</span>
                {c.connected && <span className="text-emerald-400 ml-2 text-xs">подключён</span>}
              </button>
            ))}
          </div>
        )}
        {hint && <p className="text-xs text-amber-300/80 mb-3">{hint}</p>}
        <div className="flex gap-2">
          <input value={chatId} onChange={e => setChatId(e.target.value)}
            placeholder="@my_channel или -1001234567890"
            className="flex-1 bg-[#09091a] border border-[#1c1c30] rounded-lg px-3 py-2 text-sm outline-none focus:border-violet-500/50" />
          <Btn onClick={() => doCheck()} busy={busy === 'check'} disabled={!chatId.trim()}>
            Проверить
          </Btn>
        </div>
      </Card>

      {/* Шаги 3–4 — права и возможность публикации */}
      {check && (
        <Card>
          <div className="font-semibold mb-2">3–4. Права и публикация</div>
          {check.ok ? (
            <>
              <div className="text-sm space-y-1">
                <div><span className="text-[#5a5a7a]">Канал:</span> {check.chat?.title} {check.chat?.username}</div>
                <div><span className="text-[#5a5a7a]">Роль бота:</span> {check.status}</div>
                <div><span className="text-[#5a5a7a]">Права:</span> {(check.rights || []).join(', ') || '—'}</div>
              </div>
              {check.can_publish
                ? <Note ok>Бот может публиковать в этот канал.</Note>
                : <Note>{check.reason}. {check.hint}</Note>}
              {check.can_publish && (
                <div className="flex gap-2 mt-3">
                  <Btn onClick={doTest} busy={busy === 'test'} variant="ghost">
                    5. Тестовая публикация
                  </Btn>
                  <Btn onClick={addChannel} busy={busy === 'add'}>Добавить канал</Btn>
                </div>
              )}
            </>
          ) : <Note>{check.error} {check.hint}</Note>}
          {test && (test.ok
            ? <Note ok>Тестовое сообщение отправлено{test.deleted ? ' и удалено из канала' : ''}.</Note>
            : <Note>{test.error} {test.hint}</Note>)}
        </Card>
      )}

      {/* Подключённые каналы */}
      <Card>
        <div className="font-semibold mb-3">Подключённые каналы</div>
        {channels.length === 0
          ? <p className="text-sm text-[#5a5a7a]">Пока ни одного. Пройдите шаги выше.</p>
          : (
            <div className="space-y-2">
              {channels.map(c => (
                <div key={c.chat_id}
                  className="flex items-center justify-between px-3 py-2 rounded-lg border border-[#1c1c30]">
                  <div className="text-sm">
                    <span className="font-medium">{c.title || c.chat_id}</span>
                    <span className="text-[#5a5a7a] ml-2">{c.username || c.chat_id}</span>
                    {c.default && <span className="ml-2 text-xs text-amber-300">по умолчанию</span>}
                  </div>
                  <div className="flex gap-2">
                    {!c.default && (
                      <button title="Сделать основным"
                        onClick={async () => { await telegram.setDefault(c.chat_id); load() }}
                        className="text-[#5a5a7a] hover:text-amber-300"><Star className="w-4 h-4" /></button>
                    )}
                    <button title="Отключить"
                      onClick={async () => { await telegram.remove(c.chat_id); load() }}
                      className="text-[#5a5a7a] hover:text-red-400"><Trash2 className="w-4 h-4" /></button>
                  </div>
                </div>
              ))}
            </div>
          )}
      </Card>

      {/* Режимы автопубликации */}
      {auto && (
        <Card>
          <div className="flex items-center justify-between mb-3">
            <div>
              <div className="font-semibold">Автопубликация</div>
              <p className="text-xs text-[#5a5a7a]">Общий выключатель и режим каждой площадки</p>
            </div>
            <button onClick={toggleAuto}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium border ${
                auto.enabled ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                             : 'border-[#1c1c30] text-[#5a5a7a]'}`}>
              {auto.enabled ? 'ON' : 'OFF'}
            </button>
          </div>
          <div className="space-y-2">
            {Object.entries(auto.platforms || {}).map(([platform, mode]) => (
              <div key={platform} className="flex items-center justify-between">
                <span className="text-sm capitalize">{platform}</span>
                <div className="flex gap-1">
                  {[['manual', 'вручную'], ['confirm', 'подтверждение'], ['auto', 'автоматически']]
                    .map(([m, label]) => (
                    <button key={m} onClick={() => setMode(platform, m)}
                      className={`px-2.5 py-1 rounded-md text-xs border transition ${
                        mode === m ? 'border-violet-500/40 bg-violet-600/15 text-violet-300'
                                   : 'border-[#1c1c30] text-[#5a5a7a] hover:text-[#c0c0e0]'}`}>
                      {label}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
          {!auto.enabled && (
            <p className="text-xs text-amber-300/80 mt-3">
              Автопубликация выключена: посты готовятся, но ждут подтверждения.
            </p>
          )}
        </Card>
      )}
    </div>
  )
}
