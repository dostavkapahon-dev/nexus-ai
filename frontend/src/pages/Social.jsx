import React, { useState, useEffect } from 'react'
import { Share2, RefreshCw, Loader, CheckCircle, XCircle, AlertTriangle, Link2 } from 'lucide-react'
import { social } from '../lib/api'

const ICONS = {
  instagram: '📸', threads: '🧵', telegram: '✈️',
  tiktok: '🎵', youtube: '▶️', vk: '🅥',
}

export default function Social() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState('')
  const [oauth, setOauth] = useState(null)

  const load = async () => {
    setLoading(true)
    try { setData((await social.health()).data) } catch {}
    setLoading(false)
  }
  useEffect(() => { load() }, [])

  const refresh = async (platform) => {
    setBusy(platform)
    try {
      const r = await social.refresh(platform)
      alert(r.data?.refreshed
        ? `Токен ${platform} продлён`
        : `Не удалось продлить: ${r.data?.error || r.data?.reason || '—'}`)
    } catch (e) { alert('Ошибка: ' + e.message) }
    setBusy(''); load()
  }

  const connectInstagram = async () => {
    try {
      const r = await social.oauthStart()
      if (r.data?.ok && r.data.url) window.location.href = r.data.url
      else setOauth(r.data?.error || 'Не удалось получить ссылку')
    } catch (e) { setOauth(e.message) }
  }

  const items = data?.platforms || []

  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-5 flex-wrap gap-2">
        <div>
          <h1 className="text-xl font-bold gradient-text flex items-center gap-2">
            <Share2 className="w-5 h-5 text-cyan-400" /> Площадки
          </h1>
          <p className="text-xs text-[#5a5a7a] mt-1">
            Прямое подключение через официальные API — состояние токенов и прав
          </p>
        </div>
        <div className="flex items-center gap-2">
          {data && (
            <span className="text-xs text-[#7a7a9a]">
              подключено {data.connected} из {data.total}
            </span>
          )}
          <button onClick={load} className="text-xs px-3 py-1.5 rounded-lg bg-[#0d0d1a] border border-[#1c1c30] text-[#c0c0e0]">
            {loading ? <Loader className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
          </button>
        </div>
      </div>

      <div className="card p-4 mb-4 border border-violet-500/25">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <div className="text-sm font-medium text-[#e8e8f5] flex items-center gap-2">
              <Link2 className="w-4 h-4 text-violet-400" /> Подключить Instagram через Facebook
            </div>
            <div className="text-[11px] text-[#5a5a7a] mt-1">
              Обычный OAuth вместо ручного копирования токена. Нужен аккаунт Business/Creator,
              привязанный к Facebook-странице.
            </div>
          </div>
          <button onClick={connectInstagram} className="btn-primary text-sm">Подключить</button>
        </div>
        {oauth && <div className="mt-2 text-xs text-amber-400">{oauth}</div>}
      </div>

      <div className="space-y-2">
        {items.map(p => {
          const warn = p.warning || (p.missing_permissions?.length
            ? 'не хватает прав: ' + p.missing_permissions.join(', ') : '')
          return (
            <div key={p.platform} className="card p-4">
              <div className="flex items-start gap-3">
                <span className="text-2xl">{ICONS[p.platform] || '🌐'}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-[#e8e8f5] capitalize">{p.platform}</span>
                    {p.ok
                      ? <CheckCircle className="w-4 h-4 text-green-400" />
                      : <XCircle className="w-4 h-4 text-[#5a5a7a]" />}
                    {p.account && <span className="text-xs text-[#9a9ac0]">{p.account}</span>}
                  </div>

                  {!p.configured && (
                    <div className="text-[11px] text-[#7a7a9a] mt-1">
                      Не настроено. Нужны ключи: <code className="text-amber-400">{(p.missing_env || []).join(', ')}</code>
                    </div>
                  )}
                  {p.configured && p.error && (
                    <div className="text-[11px] text-red-400 mt-1">⚠️ {p.error}</div>
                  )}
                  {p.ok && (
                    <div className="text-[11px] text-[#5a5a7a] mt-1">
                      Токен: {p.expires_at}
                      {p.days_left != null && ` · осталось ${p.days_left} дн.`}
                      {p.can_publish === false && ' · публикация недоступна'}
                    </div>
                  )}
                  {warn && (
                    <div className="text-[11px] text-amber-400 mt-1 flex items-center gap-1">
                      <AlertTriangle className="w-3 h-3" /> {warn}
                    </div>
                  )}
                </div>

                {p.configured && (
                  <button onClick={() => refresh(p.platform)} disabled={busy === p.platform}
                    className="text-xs px-2.5 py-1 rounded-lg bg-[#0d0d1a] border border-[#1c1c30] text-[#c0c0e0] disabled:opacity-50 shrink-0">
                    {busy === p.platform ? '...' : 'Продлить'}
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {data?.expiring_soon?.length > 0 && (
        <div className="card p-4 mt-4 border border-amber-500/30">
          <div className="text-sm text-amber-400 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4" />
            Скоро истекут токены: {data.expiring_soon.join(', ')}
          </div>
          <div className="text-[11px] text-[#7a7a9a] mt-1">
            Сервер продлевает их сам каждое утро, но можно нажать «Продлить» вручную.
          </div>
        </div>
      )}
    </div>
  )
}
