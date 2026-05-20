import React, { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Send, Trash2, Edit3, Loader, CheckCircle, Clock, AlertCircle, Image, Wand2 } from 'lucide-react'
import { queue as queueApi, niches as nichesApi } from '../lib/api'

const STATUS_ICON = {
  pending: <Clock className="w-3 h-3 text-nexus-muted" />,
  generated: <CheckCircle className="w-3 h-3 text-green-400" />,
  published: <CheckCircle className="w-3 h-3 text-cyan-400" />,
  failed: <AlertCircle className="w-3 h-3 text-red-400" />
}
const STATUS_COLOR = { pending: 'text-nexus-muted', generated: 'text-green-400', published: 'text-cyan-400', failed: 'text-red-400' }

function ContentModal({ item, onClose, onSave }) {
  const [text, setText] = useState(item.content?.text || '')
  const [saving, setSaving] = useState(false)

  const save = async () => {
    setSaving(true)
    await queueApi.update(item.id, { text_reviewed: text })
    onSave(text)
    setSaving(false)
    onClose()
  }

  return (
    <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4">
      <div className="glass rounded-2xl w-full max-w-2xl max-h-[90vh] flex flex-col">
        <div className="p-4 border-b border-nexus-border flex items-center justify-between">
          <div>
            <h3 className="font-semibold">{item.topic}</h3>
            <p className="text-xs text-nexus-muted">{item.platform} · День {item.day_number}</p>
          </div>
          <button onClick={onClose} className="text-nexus-muted hover:text-nexus-text">✕</button>
        </div>
        {item.content?.image_url && (
          <div className="p-4 border-b border-nexus-border">
            <img src={item.content.image_url} alt="" className="w-full h-48 object-cover rounded-lg" />
          </div>
        )}
        <div className="p-4 flex-1">
          <textarea value={text} onChange={e => setText(e.target.value)}
            className="w-full h-48 bg-nexus-card border border-nexus-border rounded-lg p-3 text-sm text-nexus-text resize-none focus:border-purple-500 outline-none" />
          {item.content?.score && (
            <div className="mt-2 text-xs text-nexus-muted">
              Оценка: <span className={`font-bold ${item.content.score >= 8 ? 'text-green-400' : item.content.score >= 6 ? 'text-yellow-400' : 'text-red-400'}`}>{item.content.score}/10</span>
            </div>
          )}
        </div>
        <div className="p-4 border-t border-nexus-border flex gap-2">
          <button onClick={onClose} className="flex-1 py-2 rounded-lg border border-nexus-border text-nexus-muted text-sm hover:border-nexus-text transition">Отмена</button>
          <button onClick={save} disabled={saving} className="flex-1 py-2 rounded-lg bg-purple-600 text-white text-sm hover:bg-purple-500 transition disabled:opacity-50 flex items-center justify-center gap-2">
            {saving ? <Loader className="w-4 h-4 animate-spin" /> : 'Сохранить'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function Queue() {
  const [searchParams] = useSearchParams()
  const [items, setItems] = useState([])
  const [niches, setNiches] = useState([])
  const [selectedNiche, setSelectedNiche] = useState(searchParams.get('niche_id') || '')
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState(null)
  const [actionId, setActionId] = useState(null)

  useEffect(() => { nichesApi.list().then(r => setNiches(r.data)) }, [])

  const load = async () => {
    setLoading(true)
    try {
      const r = await queueApi.list(selectedNiche ? { niche_id: selectedNiche } : {})
      setItems(r.data)
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [selectedNiche])

  const handleGenerate = async (id) => {
    setActionId(id)
    await queueApi.generate(id)
    setTimeout(load, 3000)
    setActionId(null)
  }

  const handlePublish = async (id) => {
    setActionId(id)
    await queueApi.publish(id)
    setTimeout(load, 2000)
    setActionId(null)
  }

  const handleDelete = async (id) => {
    if (!confirm('Удалить?')) return
    await queueApi.delete(id)
    setItems(p => p.filter(i => i.id !== id))
  }

  return (
    <div>
      {modal && (
        <ContentModal item={modal} onClose={() => setModal(null)}
          onSave={(text) => setItems(p => p.map(i => i.id === modal.id ? { ...i, content: { ...i.content, text } } : i))} />
      )}

      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Очередь контента</h1>
        <select value={selectedNiche} onChange={e => setSelectedNiche(e.target.value)}
          className="bg-nexus-card border border-nexus-border rounded-lg px-3 py-2 text-sm text-nexus-text focus:border-purple-500 outline-none">
          <option value="">Все ниши</option>
          {niches.map(n => <option key={n.id} value={n.id}>{n.name}</option>)}
        </select>
      </div>

      {loading ? (
        <div className="text-center text-nexus-muted py-12">Загрузка...</div>
      ) : items.length === 0 ? (
        <div className="text-center py-20 text-nexus-muted">
          <Clock className="w-10 h-10 mx-auto mb-3 opacity-40" />
          <p>Очередь пуста. Создайте нишу чтобы начать.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map(item => (
            <div key={item.id} className="glass rounded-xl p-4">
              <div className="flex items-start gap-4">
                <div className="text-center min-w-[48px]">
                  <div className="text-lg font-bold text-purple-400">{item.day_number}</div>
                  <div className="text-xs text-nexus-muted">день</div>
                  <span className="text-xs px-1.5 py-0.5 rounded bg-nexus-card text-nexus-muted capitalize mt-1 inline-block">{item.platform}</span>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    {STATUS_ICON[item.status]}
                    <span className={`text-xs ${STATUS_COLOR[item.status]}`}>{item.status}</span>
                    <span className="text-xs text-nexus-muted">·</span>
                    <span className="text-xs text-nexus-muted capitalize">{item.format}</span>
                  </div>
                  <p className="text-sm font-medium text-nexus-text truncate">{item.topic}</p>
                  {item.hook && <p className="text-xs text-nexus-muted mt-0.5 italic truncate">"{item.hook}"</p>}
                  {item.content?.text && <p className="text-xs text-nexus-muted mt-2 line-clamp-2">{item.content.text}</p>}
                  {item.content?.image_url && (
                    <div className="flex items-center gap-1 mt-1 text-xs text-cyan-400">
                      <Image className="w-3 h-3" /> Изображение готово
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-1.5">
                  {item.status === 'pending' && (
                    <button onClick={() => handleGenerate(item.id)} disabled={actionId === item.id}
                      className="p-2 rounded-lg bg-purple-600/20 hover:bg-purple-600/40 text-purple-300 transition disabled:opacity-50">
                      {actionId === item.id ? <Loader className="w-4 h-4 animate-spin" /> : <Wand2 className="w-4 h-4" />}
                    </button>
                  )}
                  {item.content && (
                    <button onClick={() => setModal(item)} className="p-2 rounded-lg bg-nexus-card hover:bg-nexus-border text-nexus-muted hover:text-nexus-text transition">
                      <Edit3 className="w-4 h-4" />
                    </button>
                  )}
                  {item.status === 'generated' && (
                    <button onClick={() => handlePublish(item.id)} disabled={actionId === item.id}
                      className="p-2 rounded-lg bg-cyan-600/20 hover:bg-cyan-600/40 text-cyan-300 transition disabled:opacity-50">
                      {actionId === item.id ? <Loader className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                    </button>
                  )}
                  <button onClick={() => handleDelete(item.id)} className="p-2 rounded-lg hover:bg-red-900/30 text-nexus-muted hover:text-red-400 transition">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
