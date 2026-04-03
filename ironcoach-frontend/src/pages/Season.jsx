import { useEffect, useState, useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import axios from 'axios'

const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || '' })

export default function Season() {
  const [items, setItems] = useState([])
  const [uploading, setUploading] = useState(false)
  const [label, setLabel] = useState('')
  const [text, setText] = useState('')
  const [tab, setTab] = useState('pdf')
  const [expanded, setExpanded] = useState(null)
  const [fullText, setFullText] = useState({})

  const load = async () => {
    const resp = await api.get('/api/season')
    setItems(resp.data)
  }

  useEffect(() => { load() }, [])

  const onDrop = useCallback(async (accepted) => {
    if (!accepted.length || !label.trim()) return
    setUploading(true)
    try {
      const form = new FormData()
      form.append('file', accepted[0])
      form.append('label', label)
      await api.post('/api/season/pdf', form, { headers: { 'Content-Type': 'multipart/form-data' } })
      setLabel('')
      load()
    } catch (e) {
      alert(e.response?.data?.detail || 'Upload fehlgeschlagen')
    } finally {
      setUploading(false)
    }
  }, [label])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    maxFiles: 1,
  })

  const addText = async () => {
    if (!label.trim() || !text.trim()) return
    await api.post('/api/season/text', { label, text })
    setLabel('')
    setText('')
    load()
  }

  const deleteItem = async (id) => {
    await api.delete(`/api/season/${id}`)
    load()
  }

  const loadFullText = async (id) => {
    if (fullText[id]) {
      setExpanded(expanded === id ? null : id)
      return
    }
    const resp = await api.get(`/api/season/${id}/text`)
    setFullText(prev => ({ ...prev, [id]: resp.data.text }))
    setExpanded(id)
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <h1 className="text-2xl font-bold">Saisonplan & Referenzpläne</h1>
      <p className="text-gray-400 text-sm">Lade deine Wochenpläne (PDF) oder paste Text-Pläne — Claude nutzt diese als Kontext beim Generieren und im Chat.</p>

      {/* Upload Form */}
      <div className="bg-gray-900 rounded-xl p-5 space-y-4">
        <div className="flex gap-2">
          {['pdf', 'text'].map(t => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${tab === t ? 'bg-brand-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-gray-100'}`}>
              {t === 'pdf' ? 'PDF hochladen' : 'Text einfügen'}
            </button>
          ))}
        </div>

        <input
          value={label}
          onChange={e => setLabel(e.target.value)}
          placeholder="Bezeichnung (z.B. '33-Wochen-Plan', 'Schwimmplan KW1-10')"
          className="w-full bg-gray-800 rounded-lg px-3 py-2 text-sm border border-gray-700 focus:outline-none focus:border-brand-500"
        />

        {tab === 'pdf' ? (
          <div {...getRootProps()} className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${isDragActive ? 'border-brand-500 bg-brand-500/10' : 'border-gray-700 hover:border-gray-500'} ${!label.trim() ? 'opacity-50 pointer-events-none' : ''}`}>
            <input {...getInputProps()} />
            {uploading ? <p className="text-gray-400">Wird verarbeitet...</p>
              : isDragActive ? <p className="text-brand-500 font-medium">PDF ablegen</p>
              : <div>
                  <p className="text-gray-300 font-medium mb-1">PDF hier ablegen</p>
                  <p className="text-gray-500 text-sm">oder klicken zum Auswählen{!label.trim() ? ' (erst Bezeichnung eingeben)' : ''}</p>
                </div>}
          </div>
        ) : (
          <div className="space-y-3">
            <textarea
              value={text}
              onChange={e => setText(e.target.value)}
              placeholder="Plan hier einfügen..."
              rows={8}
              className="w-full bg-gray-800 rounded-lg px-3 py-2 text-sm border border-gray-700 focus:outline-none focus:border-brand-500 resize-y"
            />
            <button
              onClick={addText}
              disabled={!label.trim() || !text.trim()}
              className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium"
            >
              Speichern
            </button>
          </div>
        )}
      </div>

      {/* List */}
      <div className="space-y-3">
        {items.length === 0 && <p className="text-gray-500 text-sm">Noch keine Pläne hinterlegt.</p>}
        {items.map(item => (
          <div key={item.id} className="bg-gray-900 rounded-xl p-4 space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className={`text-xs px-2 py-0.5 rounded-full ${item.content_type === 'pdf' ? 'bg-red-900/40 text-red-300' : 'bg-blue-900/40 text-blue-300'}`}>
                  {item.content_type.toUpperCase()}
                </span>
                <span className="font-medium">{item.label}</span>
                {item.filename && <span className="text-xs text-gray-500">{item.filename}</span>}
              </div>
              <div className="flex gap-3">
                <button onClick={() => loadFullText(item.id)} className="text-xs text-gray-400 hover:text-brand-400">
                  {expanded === item.id ? 'Einklappen' : 'Anzeigen'}
                </button>
                <button onClick={() => deleteItem(item.id)} className="text-xs text-red-500 hover:text-red-400">Löschen</button>
              </div>
            </div>
            <p className="text-gray-500 text-xs leading-relaxed">{item.text_preview}</p>
            {expanded === item.id && fullText[item.id] && (
              <pre className="text-xs text-gray-300 bg-gray-800 rounded-lg p-3 overflow-y-auto max-h-64 whitespace-pre-wrap">
                {fullText[item.id]}
              </pre>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
