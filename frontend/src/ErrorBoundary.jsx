import React from 'react'

/**
 * Белый экран — худший вид поломки: человек видит пустоту и не знает, что
 * случилось и что делать. Любая ошибка внутри React без этого обработчика
 * размонтирует всё дерево и оставляет пустой <div id="root">.
 *
 * Здесь вместо пустоты показывается текст ошибки и два действия: перезагрузить
 * и проверить бэкенд. Этого достаточно, чтобы отличить «сервис спит» от
 * «сломан фронтенд».
 */
export default class ErrorBoundary extends React.Component {
  constructor (props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError (error) {
    return { error }
  }

  componentDidCatch (error, info) {
    // В консоль — полный стек: он нужен при разборе, но не на экране.
    console.error('[NEXUS] ошибка интерфейса:', error, info)
  }

  render () {
    if (!this.state.error) return this.props.children
    return (
      <div style={{ padding: 24, fontFamily: 'system-ui, sans-serif', color: '#e5e7eb', background: '#111827', minHeight: '100vh' }}>
        <h1 style={{ fontSize: 20, marginBottom: 12 }}>Интерфейс не открылся</h1>
        <p style={{ marginBottom: 12, opacity: 0.8 }}>
          Страница перестала отвечать из-за ошибки. Telegram-бот при этом
          работает: он живёт в том же сервисе, но не зависит от этой страницы.
        </p>
        <pre style={{ whiteSpace: 'pre-wrap', background: '#1f2937', padding: 12, borderRadius: 8, fontSize: 13 }}>
          {String(this.state.error?.message || this.state.error)}
        </pre>
        <div style={{ marginTop: 16, display: 'flex', gap: 12 }}>
          <button onClick={() => window.location.reload()} style={{ padding: '8px 14px', borderRadius: 8, border: 0, background: '#2563eb', color: '#fff', cursor: 'pointer' }}>
            Перезагрузить
          </button>
          <a href="/api/health" style={{ padding: '8px 14px', borderRadius: 8, background: '#374151', color: '#fff', textDecoration: 'none' }}>
            Проверить сервер
          </a>
        </div>
      </div>
    )
  }
}
