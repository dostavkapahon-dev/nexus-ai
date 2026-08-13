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
  const [browser, setBrowser] = useState(null)
  const [session, setSession] = useState(null)
  const [igToken, setIgToken] = useState('')
  const [igResult, setIgResult] = useState(null)
  const [hook, setHook] = useState(null)
  const [copied, setCopied] = useState('')

  const load = async () => {
    setLoading(true)
    try { setData((await social.health()).data) } catch {}
    try { setBrowser((await social.browserStatus()).data) } catch {}
    try { setHook((await social.webhookConfig()).data) } catch {}
    setLoading(false)
  }

  // Значения длинные, и опечатка при перепечатывании даёт у Meta безликое
  // «couldn't be validated» — поэтому только копированием.
  const copy = async (what, value) => {
    try { await navigator.clipboard.writeText(value); setCopied(what) }
    catch { setCopied('') }
    setTimeout(() => setCopied(''), 1500)
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

  // Токен уже выдан в панели Meta — гонять его через OAuth незачем.
  const connectByToken = async () => {
    setBusy('token'); setIgResult(null)
    try {
      const r = await social.connectInstagramToken(igToken.trim())
      setIgResult(r.data)
      if (r.data?.ok) { setIgToken(''); load() }
    } catch (e) { setIgResult({ ok: false, error: e.message }) }
    setBusy('')
  }

  const checkSession = async () => {
    setBusy('session'); setSession(null)
    try { setSession((await social.browserSession('instagram')).data) }
    catch (e) { setSession({ ok: false, error: e.message }) }
    setBusy('')
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
        {/* Основной путь — по токену из панели Meta. Facebook для него не нужен. */}
        <div>
          <div className="text-sm font-medium text-[#e8e8f5] flex items-center gap-2">
            <Link2 className="w-4 h-4 text-violet-400" /> Подключить Instagram
          </div>
          <div className="text-[11px] text-[#9a9ac0] mt-1 mb-2">
            Приложение Meta → Instagram → «API setup with Instagram login» → шаг 2
            «Generate token» → кнопкой <b className="text-[#c0c0e0]">Copy</b> скопируйте
            токен <code className="mx-1 px-1 rounded bg-[#111120] text-cyan-300">IGAA…</code>
            и вставьте сюда. Страница Facebook не нужна.
          </div>
          <div className="flex gap-2 flex-wrap">
            <input
              value={igToken}
              onChange={(e) => setIgToken(e.target.value)}
              type="password"
              placeholder="IGAAxxxxxxxx… (Instagram User Access Token)"
              className="flex-1 min-w-[220px] text-xs px-3 py-2 rounded-lg bg-[#0d0d1a] border border-[#1c1c30] text-[#c0c0e0]"
            />
            <button onClick={connectByToken} disabled={!igToken.trim() || busy === 'token'}
              className="text-sm px-3 py-2 rounded-lg bg-[#111120] border border-[#1c1c30] text-[#c0c0e0] disabled:opacity-40">
              {busy === 'token' ? 'Проверяю…' : 'Подключить по токену'}
            </button>
          </div>
          {igResult && (
            <div className={`mt-2 text-xs ${igResult.ok ? 'text-green-400' : 'text-amber-400'}`}>
              {igResult.ok
                ? `Подключено${igResult.username ? ' @' + igResult.username : ''} · ID ${igResult.account_id} · ${igResult.note}`
                : `${igResult.error}${igResult.token_looks_like ? ' · вставленная строка: ' + igResult.token_looks_like : ''}`}
            </div>
          )}

          {/* Путь через Facebook оставлен, но убран с первого плана: он нужен
              только для Business Discovery (разбор чужих аккаунтов через API). */}
          <div className="mt-3 pt-3 border-t border-[#1c1c30] text-[11px] text-[#5a5a7a]">
            Нужен разбор чужих аккаунтов через Business Discovery? Это работает только
            через Страницу Facebook —{' '}
            <button onClick={connectInstagram} className="text-violet-400 hover:underline">
              подключить через Facebook
            </button>
            . Для публикации и комментариев не требуется.
            {oauth && <div className="mt-1 text-amber-400">{oauth}</div>}
          </div>
        </div>
      </div>

      {/* Готовые значения для панели Meta: составлять руками их больше не нужно. */}
      <div className="card p-4 mb-4 border border-cyan-500/25">
        <div className="text-sm font-medium text-[#e8e8f5] mb-1">
          💬 Комментарии в реальном времени (необязательно)
        </div>
        <div className="text-[11px] text-[#5a5a7a] mb-3">
          Без этого комментарии разбираются раз в 4 часа. Вставьте оба значения в
          панели Meta → Instagram → Webhooks, поля <b>comments</b> и <b>mentions</b>.
        </div>

        {hook?.callback_url ? (
          <div className="space-y-2">
            {[['Callback URL', hook.callback_url, 'url'],
              ['Verify token', hook.verify_token, 'token']].map(([label, value, key]) => (
              <div key={key}>
                <div className="text-[10px] text-[#5a5a7a] mb-1">{label}</div>
                <div className="flex gap-2">
                  <code className="flex-1 min-w-0 text-[11px] px-2 py-1.5 rounded-lg bg-[#0d0d1a] border border-[#1c1c30] text-cyan-300 truncate">
                    {value}
                  </code>
                  <button onClick={() => copy(key, value)}
                    className="text-[11px] px-2.5 py-1.5 rounded-lg bg-[#111120] border border-[#1c1c30] text-[#c0c0e0] shrink-0">
                    {copied === key ? 'Скопировано' : 'Копировать'}
                  </button>
                </div>
              </div>
            ))}
            {!hook.app_secret_set && (
              <div className="text-[11px] text-amber-400 mt-1">
                ⚠️ Не задан Instagram app secret — события будут отклоняться по подписи.
                Ключи API → Instagram.
              </div>
            )}
          </div>
        ) : (
          <div className="text-[11px] text-amber-400">
            {hook?.error || 'Загружаю…'}
          </div>
        )}
      </div>

      {/* Путь без ключей Meta: публикация через веб-интерфейс на сервере. */}
      <div className="card p-4 mb-4 border border-amber-500/25">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <div className="text-sm font-medium text-[#e8e8f5] flex items-center gap-2">
              🍪 Публикация без ключей API (браузер на сервере)
            </div>
            <div className="text-[11px] text-[#5a5a7a] mt-1">
              {browser?.has_cookies
                ? `Cookies загружены: ${browser.domains.join(', ')} · режим ${browser.mode} · публикация ${browser.publish_mode}`
                : 'Cookies не заданы. Ключи API → «Браузерная сессия» — вставьте экспорт из расширения.'}
            </div>
          </div>
          <button onClick={checkSession} disabled={busy === 'session'}
            className="text-sm px-3 py-1.5 rounded-lg bg-[#0d0d1a] border border-[#1c1c30] text-[#c0c0e0]">
            {busy === 'session' ? 'Проверяю…' : 'Проверить сессию'}
          </button>
        </div>
        {session && (
          <div className={`mt-2 text-xs ${session.logged_in ? 'text-green-400' : 'text-amber-400'}`}>
            {session.logged_in
              ? 'Сессия жива — публиковать можно без токенов Meta.'
              : `Не залогинены: ${session.hint || session.error || 'проверьте cookies'}`}
          </div>
        )}
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
