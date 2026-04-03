import { useEffect, useRef, useState } from 'react'
import { sendChat, clearChat } from '../services/api'
import axios from 'axios'

const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || '' })

export default function Chat() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    api.get('/api/chat/history').then(r => setMessages(r.data)).catch(() => {})
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const send = async () => {
    const msg = input.trim()
    if (!msg || loading) return
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: msg, id: Date.now() }])
    setLoading(true)
    try {
      const resp = await sendChat(msg)
      setMessages(resp.data.history)
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Fehler: ' + (e.response?.data?.detail || 'Unbekannter Fehler'), id: Date.now() + 1 }])
    } finally {
      setLoading(false)
    }
  }

  const handleClear = async () => {
    await clearChat()
    setMessages([])
  }

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Coach Chat</h1>
        {messages.length > 0 && (
          <button onClick={handleClear} className="text-xs text-gray-500 hover:text-gray-300">Chat löschen</button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto space-y-3 mb-4 bg-gray-900 rounded-xl p-4">
        {messages.length === 0 && (
          <p className="text-gray-500 text-center py-8">Stelle eine Frage an deinen Triathlon-Coach...</p>
        )}
        {messages.map((msg, i) => (
          <div key={msg.id || i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[80%] rounded-xl px-4 py-2 text-sm leading-relaxed ${
              msg.role === 'user'
                ? 'bg-brand-600 text-white'
                : 'bg-gray-800 text-gray-100'
            }`}>
              {msg.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-800 rounded-xl px-4 py-2 text-gray-400 text-sm">Denkt nach...</div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="flex gap-2">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && !e.shiftKey && send()}
          placeholder="Nachricht eingeben..."
          className="flex-1 bg-gray-800 rounded-xl px-4 py-3 text-sm border border-gray-700 focus:outline-none focus:border-brand-500"
        />
        <button
          onClick={send}
          disabled={loading || !input.trim()}
          className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white px-5 py-3 rounded-xl font-medium text-sm transition-colors"
        >
          Senden
        </button>
      </div>
    </div>
  )
}
