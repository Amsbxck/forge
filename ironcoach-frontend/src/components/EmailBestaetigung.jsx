import { useState } from 'react'
import { resendVerification } from '../services/api'

/**
 * Hinweis, solange die Adresse nicht bestätigt ist.
 *
 * Ohne ihn ist die Lage für einen neuen Athleten unerklärlich: Das
 * Willkommensfenster wartet auf die Bestätigung, bleibt also aus — und auf
 * dem Dashboard steht dann nichts, was das erklärt. Der Weg nach vorn ist
 * eine Mail im Postfach, von der er nichts weiss.
 */
export default function EmailBestaetigung({ email }) {
  const [status, setStatus] = useState(null)   // null | 'sendet' | 'ok' | 'fehler'

  const erneut = async () => {
    setStatus('sendet')
    try {
      await resendVerification()
      setStatus('ok')
    } catch {
      setStatus('fehler')
    }
  }

  return (
    <div
      className="rounded-xl p-4 flex items-start gap-3 flex-wrap"
      style={{ background: '#111318', border: '1px solid #1e2228', borderLeft: '3px solid #f59e0b' }}
    >
      <div className="min-w-0 flex-1">
        <div className="text-sm font-bold text-[#e8eaf0]">Bitte bestätige deine E-Mail</div>
        <p className="text-[13px] text-[var(--text-secondary)] mt-1 leading-relaxed">
          Wir haben einen Link an <span className="font-mono text-[var(--text-primary)]">{email}</span> geschickt.
          Erst danach geht es mit der Einrichtung weiter — Ziel, Zonen und Testwoche.
          Schau auch im Spam-Ordner nach.
        </p>
        {status === 'ok' && (
          <p className="text-[12px] font-mono mt-2" style={{ color: '#22c55e' }}>
            ✓ Neue Mail ist unterwegs
          </p>
        )}
        {status === 'fehler' && (
          <p className="text-[12px] font-mono mt-2" style={{ color: '#ef4444' }}>
            ✕ Konnte nicht gesendet werden — bitte später erneut versuchen
          </p>
        )}
      </div>
      <button
        onClick={erneut}
        disabled={status === 'sendet'}
        className="px-3 py-1.5 rounded-lg text-[12px] font-mono tracking-wide disabled:opacity-40 flex-shrink-0"
        style={{ background: '#f59e0b20', border: '1px solid #f59e0b44', color: '#f59e0b' }}
      >
        {status === 'sendet' ? 'SENDET…' : 'ERNEUT SENDEN'}
      </button>
    </div>
  )
}
