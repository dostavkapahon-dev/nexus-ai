import React, { useState, useEffect } from 'react'
import { Zap, Lock, Loader } from 'lucide-react'
import { auth } from '../lib/api'

function GoogleButton({ clientId, onToken }) {
  useEffect(() => {
    if (!clientId || !window.google) return
    window.google.accounts.id.initialize({
      client_id: clientId,
      callback: (res) => onToken(res.credential),
    })
    window.google.accounts.id.renderButton(
      document.getElementById('google-btn'),
      { theme: 'filled_black', size: 'large', width: 320, text: 'signin_with' }
    )
  }, [clientId])

  if (!clientId) return null
  return <div id="google-btn" className="flex justify-center" />
}

export default function Login() {
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [googleClientId, setGoogleClientId] = useState('')

  useEffect(() => {
    auth.googleClientId().then(r => {
      if (r.data.enabled) {
        setGoogleClientId(r.data.client_id)
        // Load Google Identity Services script
        if (!document.getElementById('gsi-script')) {
          const s = document.createElement('script')
          s.id = 'gsi-script'
          s.src = 'https://accounts.google.com/gsi/client'
          s.async = true
          document.head.appendChild(s)
        }
      }
    }).catch(() => {})
  }, [])

  const submit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const r = await auth.login(password)
      localStorage.setItem('nx_token', r.data.token)
      window.location.href = '/'
    } catch (err) {
      setError(err.response?.data?.detail || 'Ошибка входа')
    } finally {
      setLoading(false)
    }
  }

  const handleGoogleToken = async (credential) => {
    setLoading(true)
    setError('')
    try {
      const r = await auth.googleLogin(credential)
      localStorage.setItem('nx_token', r.data.token)
      window.location.href = '/'
    } catch (err) {
      setError(err.response?.data?.detail || 'Ошибка Google входа')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-nexus-bg flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 mb-4">
            <Zap className="text-purple-400 w-8 h-8" />
            <span className="text-2xl font-bold bg-gradient-to-r from-purple-400 to-cyan-400 bg-clip-text text-transparent">
              NEXUS AI
            </span>
          </div>
          <p className="text-nexus-muted text-sm">Введите пароль для входа</p>
        </div>

        <div className="glass rounded-xl p-6 space-y-4">
          <form onSubmit={submit} className="space-y-4">
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-nexus-muted" />
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="Пароль администратора"
                autoFocus
                className="w-full bg-nexus-card border border-nexus-border rounded-lg px-4 py-3 pl-10 text-sm text-nexus-text placeholder-nexus-muted focus:border-purple-500 outline-none"
              />
            </div>

            {error && (
              <div className="text-red-400 text-xs text-center bg-red-500/10 rounded-lg py-2 px-3">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading || !password}
              className="w-full py-3 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-sm font-medium transition flex items-center justify-center gap-2"
            >
              {loading ? <Loader className="w-4 h-4 animate-spin" /> : 'Войти'}
            </button>
          </form>

          {googleClientId && (
            <>
              <div className="flex items-center gap-3">
                <div className="flex-1 h-px bg-nexus-border" />
                <span className="text-xs text-nexus-muted">или</span>
                <div className="flex-1 h-px bg-nexus-border" />
              </div>
              <GoogleButton clientId={googleClientId} onToken={handleGoogleToken} />
            </>
          )}
        </div>

        <p className="text-center text-xs text-nexus-muted mt-4">
          Пароль задаётся в Render → Environment → <code className="text-purple-400">ADMIN_PASSWORD</code>
        </p>
      </div>
    </div>
  )
}
