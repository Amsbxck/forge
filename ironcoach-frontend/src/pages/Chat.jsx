import { useEffect, useRef, useState } from 'react'
import { sendChat, clearChat } from '../services/api'
import axios from 'axios'

const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || '' })

function TypingIndicator() {
  return (
    <div className="flex justify-start pl-0">
      <div
        className="rounded-xl px-4 py-3 flex items-center gap-1.5"
        style={{ background: '#111318', border: '1px solid #1e2228' }}
      >
        {[0, 1, 2].map(i => (
          <span
            key={i}
            className="w-1.5 h-1.5 rounded-full"
            style={{
              background: '#00d4ff',
              animation: `chatPulse 1.4s ease-in-out ${i * 0.2}s infinite`,
            }}
          />
        ))}
      </div>
    </div>
  )
}

function Message({ msg, isNew }) {
  const isUser = msg.role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className="max-w-[78%] rounded-xl px-4 py-2.5 text-sm leading-relaxed font-mono"
        style={isUser ? {
          background: '#00d4ff18',
          border: '1px solid #00d4ff35',
          color: '#e8eaf0',
          // Break the right edge — asymmetric
          marginRight: '-6px',
          borderTopRightRadius: '4px',
        } : {
          background: '#111318',
          border: '1px solid #1e2228',
          color: '#e8eaf0',
          borderTopLeftRadius: '4px',
          animation: isNew ? 'msgSlideIn 0.25s ease forwards' : 'none',
        }}
      >
        {msg.content}
      </div>
    </div>
  )
}

export default function Chat() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [waving, setWaving] = useState(false)
  const [newMsgIndex, setNewMsgIndex] = useState(null)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)
  const containerRef = useRef(null)

  useEffect(() => {
    api.get('/api/chat/history').then(r => setMessages(r.data)).catch(() => {})
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const send = async () => {
    const msg = input.trim()
    if (!msg || loading) return
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: msg, id: Date.now() }])
    setLoading(true)
    try {
      const resp = await sendChat(msg)
      const history = resp.data.history
      setNewMsgIndex(history.length - 1)
      setMessages(history)
      // Wave effect on container
      setWaving(true)
      setTimeout(() => setWaving(false), 600)
    } catch (e) {
      const errMsg = { role: 'assistant', content: 'Error: ' + (e.response?.data?.detail || 'Unknown error'), id: Date.now() + 1 }
      setMessages(prev => {
        setNewMsgIndex(prev.length)
        return [...prev, errMsg]
      })
    } finally {
      setLoading(false)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }

  const handleClear = async () => {
    await clearChat()
    setMessages([])
    setNewMsgIndex(null)
  }

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] page-enter">

      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-baseline gap-3">
          <h1
            className="text-3xl font-black tracking-tight text-[#e8eaf0]"
            style={{ fontFamily: 'Barlow Condensed, sans-serif' }}
          >
            COACH
          </h1>
          <span className="text-xs font-mono text-[var(--text-muted)] tracking-widest">AI ASSISTANT</span>
        </div>
        {messages.length > 0 && (
          <button
            onClick={handleClear}
            className="text-xs font-mono text-[var(--text-muted)] hover:text-[#ef4444] transition-colors px-3 py-1.5 rounded-lg"
            style={{ border: '1px solid #1e2228' }}
          >
            CLEAR CHAT
          </button>
        )}
      </div>

      {/* Message area */}
      <div
        ref={containerRef}
        className="flex-1 overflow-y-auto space-y-3 mb-4 rounded-xl p-4 relative"
        style={{
          background: '#0d0f17',
          border: '1px solid #1e2228',
          transition: 'box-shadow 0.3s ease',
          boxShadow: waving ? 'inset 0 0 40px #00d4ff08' : 'none',
        }}
      >
        {/* Wave pulse overlay */}
        {waving && (
          <div
            className="absolute inset-0 rounded-xl pointer-events-none"
            style={{ animation: 'waveEffect 0.6s ease forwards', zIndex: 1 }}
          />
        )}

        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full py-10 text-center">
            <div
              className="text-4xl font-black text-[#1e2228] mb-2"
              style={{ fontFamily: 'Barlow Condensed, sans-serif' }}
            >
              FORGE COACH
            </div>
            <p className="text-xs font-mono text-[var(--text-muted)] tracking-wide">
              Ask anything about your training, recovery, or race strategy.
            </p>
          </div>
        )}

        {messages.map((msg, i) => (
          <Message key={msg.id || i} msg={msg} isNew={i === newMsgIndex} />
        ))}
        {loading && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>

      {/* Input row */}
      <div className="flex gap-2">
        <input
          ref={inputRef}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && !e.shiftKey && send()}
          placeholder="Ask your coach..."
          className="flex-1 rounded-xl px-4 py-3 text-sm font-mono text-[#e8eaf0] placeholder-[var(--text-muted)] outline-none transition-colors"
          style={{ background: '#111318', border: '1px solid #1e2228' }}
          onFocus={e => { e.target.style.borderColor = '#00d4ff44' }}
          onBlur={e => { e.target.style.borderColor = '#1e2228' }}
        />
        <button
          onClick={send}
          disabled={loading || !input.trim()}
          className="px-5 py-3 rounded-xl font-mono font-bold text-sm tracking-wide transition-all disabled:opacity-30"
          style={{ background: '#00d4ff20', border: '1px solid #00d4ff44', color: '#00d4ff' }}
          onMouseEnter={e => { if (!e.currentTarget.disabled) e.currentTarget.style.background = '#00d4ff30' }}
          onMouseLeave={e => { e.currentTarget.style.background = '#00d4ff20' }}
        >
          SEND
        </button>
      </div>

      <style>{`
        @keyframes chatPulse {
          0%, 100% { opacity: 0.3; transform: translateY(0); }
          50%       { opacity: 1;   transform: translateY(-3px); }
        }
        @keyframes msgSlideIn {
          from { opacity: 0; transform: translateX(-8px); }
          to   { opacity: 1; transform: translateX(0); }
        }
        @keyframes waveEffect {
          0%   { background: transparent; }
          30%  { background: radial-gradient(ellipse at center, #00d4ff06 0%, transparent 70%); }
          100% { background: transparent; }
        }
      `}</style>
    </div>
  )
}
