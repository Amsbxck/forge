import { useCallback, useEffect, useRef, useState } from 'react'
// Über die gemeinsame Verbindung, nicht über eine eigene axios-Instanz: Die
// eigene hängte kein Token an, und mit Anmeldung (im Betrieb immer) kam der
// Verlauf beim Öffnen der Seite stets mit 401 zurück.
import { sendChat, clearChat, getBudget, getChatHistory, getHrvLage, getSaison } from '../services/api'
import { ACCENT, PHASE_COLOR, STATUS_COLOR, phaseColor } from '../utils/colors'
import { fehlerText } from '../utils/fehler'
import { blockName } from '../components/leisten/SaisonStrahl'

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

/** Zeitstempel des Servers (UTC, ohne Zonenangabe) als lokale Uhrzeit.
 *
 *  Heute nur die Uhrzeit, sonst mit Tag davor: Ein Verlauf über mehrere Tage
 *  liest sich sonst wie ein Gespräch, und „mach morgen locker" von vorgestern
 *  steht neben der Antwort von heute.
 */
function zeitpunkt(stempel) {
  if (!stempel) return null
  const mitZone = /Z|[+-]\d\d:?\d\d$/.test(stempel) ? stempel : `${stempel}Z`
  const d = new Date(mitZone)
  if (Number.isNaN(d.getTime())) return null
  const uhr = d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
  const heute = new Date()
  if (d.toDateString() === heute.toDateString()) return uhr
  const tag = d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })
  return `${tag} · ${uhr}`
}

/** Was der Coach gerade über dich weiß, in einer Zeile.
 *
 *  Der Coach antwortet mit Phase, Woche, HRV und Guthaben im Hinterkopf, der
 *  Athlet sah davon nichts. Fragt er „soll ich heute hart fahren?", hilft es,
 *  den 7-Tage-Schnitt und die Phase vor Augen zu haben, auf die sich die
 *  Antwort bezieht. Dieselben Quellen wie Dashboard und Plan
 *  (`/metrics/saison`, `/hrv/lage`, `/budget`), damit überall dieselbe Zahl
 *  steht. Fehlt eine, fällt nur ihr Teil weg.
 */
function KontextLeiste({ saison, hrv, budget }) {
  const teile = []
  if (saison) {
    if (saison.lage === 'off_season') {
      const phase = (saison.offseason_phase || 'Formerhalt').toLowerCase()
      teile.push({ key: 'phase', punkt: PHASE_COLOR.off, text: `OFF SEASON · ${phase === 'übergang' ? 'TRANSITION' : 'MAINTENANCE'}` })
    } else {
      // Der Block (Base 2, …) wie im Saisonstrahl, nicht nur die Phase.
      const inWoche = p => saison.aktuelle_woche >= p.von_woche && saison.aktuelle_woche <= p.bis_woche
      const phase = (saison.phasen || []).find(inWoche)
      const block = (phase?.teile || []).find(inWoche) || phase
      teile.push({
        key: 'phase',
        punkt: phaseColor(saison.grundlage ? 'grundlage' : block?.name),
        text: saison.grundlage ? 'PREP' : blockName(block?.name),
        zusatz: saison.aktuelle_woche ? `WEEK ${saison.aktuelle_woche}/${saison.total_weeks}` : null,
      })
    }
  }
  if (hrv?.schnitt_7 != null) {
    teile.push({
      key: 'hrv',
      text: 'HRV Ø 7',
      wert: `${Math.round(hrv.schnitt_7)} ms`,
      farbe: STATUS_COLOR[hrv.status] || '#8a909e',
    })
  }
  if (budget) {
    teile.push({
      key: 'budget',
      text: 'CREDIT',
      wert: `${budget.rest_eur.toFixed(2)} €`,
      farbe: budget.aufgebraucht ? STATUS_COLOR.red : ACCENT,
    })
  }
  if (!teile.length) return null

  return (
    <div className="flex items-center gap-x-4 gap-y-1 flex-wrap mb-3 text-[10px] font-mono tracking-widest text-[var(--text-muted)]">
      {teile.map(t => (
        <span key={t.key} className="flex items-center gap-1.5 whitespace-nowrap">
          {t.punkt && <span className="w-1.5 h-1.5 rounded-full" style={{ background: t.punkt }} />}
          <span style={t.punkt ? { color: t.punkt } : undefined}>{t.text}</span>
          {t.zusatz && <span className="tabular-nums text-[var(--text-secondary)]">{t.zusatz}</span>}
          {t.wert && <span className="tabular-nums font-bold" style={{ color: t.farbe }}>{t.wert}</span>}
        </span>
      ))}
    </div>
  )
}

function Message({ msg, isNew }) {
  const isUser = msg.role === 'user'
  const zeit = zeitpunkt(msg.created_at)
  return (
    <div className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}>
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
      {zeit && (
        <span className={`mt-1 text-[9px] font-mono tabular-nums text-[var(--text-muted)] opacity-70 ${isUser ? 'pr-1' : 'pl-1'}`}>
          {zeit}
        </span>
      )}
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

  // Der Verlauf lebt auf dem Server, nicht im Browser: Beim Öffnen der Seite
  // wird er geholt. Hier stand `.catch(() => {})` — scheiterte die Anfrage,
  // blieb die Seite einfach leer und sah aus, als sei das Gespräch verloren.
  // Ein stiller Fehler an genau der Stelle, an der man ihn am wenigsten
  // erkennt: Ein leerer Chat ist ein plausibler Zustand.
  const [verlaufFehler, setVerlaufFehler] = useState(null)
  const ladeVerlauf = useCallback(async () => {
    setVerlaufFehler(null)
    try {
      const r = await getChatHistory()
      setMessages(r.data)
    } catch (e) {
      setVerlaufFehler(
        e.response?.status
          ? `Verlauf nicht geladen (HTTP ${e.response.status}${e.response.data?.detail ? ': ' + e.response.data.detail : ''})`
          : 'Verlauf nicht geladen — keine Verbindung zum Server'
      )
    }
  }, [])

  useEffect(() => { ladeVerlauf() }, [ladeVerlauf])

  // Die Kontextleiste lädt getrennt vom Verlauf und still: Sie ist Beiwerk,
  // ein Fehler dort darf das Gespräch nicht blockieren.
  const [kontext, setKontext] = useState({})
  const ladeKontext = useCallback(async () => {
    const [saison, hrv, budget] = await Promise.allSettled([getSaison(), getHrvLage(), getBudget()])
    setKontext({
      saison: saison.status === 'fulfilled' ? saison.value.data : null,
      hrv: hrv.status === 'fulfilled' ? hrv.value.data : null,
      budget: budget.status === 'fulfilled' ? budget.value.data : null,
    })
  }, [])
  useEffect(() => { ladeKontext() }, [ladeKontext])

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
      // Die Antwort hat Guthaben gekostet; die Leiste soll den neuen Stand zeigen.
      ladeKontext()
      // Wave effect on container
      setWaving(true)
      setTimeout(() => setWaving(false), 600)
    } catch (e) {
      const text = e.code === 'ECONNABORTED'
        ? 'Die Antwort dauert ungewöhnlich lange. Lade die Seite gleich neu — falls der Coach einen Plan geändert hat, steht er dann schon im Wochenplan.'
        : fehlerText(e, 'Die Nachricht konnte nicht verarbeitet werden.')
      const errMsg = { role: 'assistant', content: 'Fehler: ' + text, id: Date.now() + 1 }
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
    // Mit Fehlerfang: Vorher blieb ein gescheitertes Löschen stumm, und der
    // Verlauf stand nach dem nächsten Laden wieder da.
    try {
      await clearChat()
      setMessages([])
      setNewMsgIndex(null)
      setVerlaufFehler(null)
    } catch (e) {
      setVerlaufFehler(fehlerText(e, 'Verlauf konnte nicht gelöscht werden.'))
    }
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
          <span className="text-xs font-mono text-[var(--text-muted)] tracking-widest">DEIN TRAINER</span>
        </div>
        {messages.length > 0 && (
          <button
            onClick={handleClear}
            className="text-xs font-mono text-[var(--text-muted)] hover:text-[#ef4444] transition-colors px-3 py-1.5 rounded-lg"
            style={{ border: '1px solid #1e2228' }}
          >
            VERLAUF LÖSCHEN
          </button>
        )}
      </div>

      <KontextLeiste {...kontext} />

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
              Frag nach Training, Erholung oder Rennstrategie — oder lass Tage im Plan umstellen.
            </p>
          </div>
        )}

        {verlaufFehler && (
          <div className="rounded-xl px-4 py-3 mb-3 font-mono text-[11px] flex items-center gap-3 flex-wrap"
               style={{ background: '#ef444412', border: '1px solid #ef444433', color: '#ef4444' }}>
            <span>{verlaufFehler}</span>
            <button onClick={ladeVerlauf}
                    className="px-2 py-1 rounded font-bold"
                    style={{ border: '1px solid #ef444455' }}>
              ERNEUT VERSUCHEN
            </button>
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
          placeholder="Frag deinen Coach …"
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
          SENDEN
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
