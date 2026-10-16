import { useState } from 'react'
import { resendVerification } from '../services/api'

/** Bestätigungsmail erneut anfordern — für den Hinweis und das Sperrfenster.
 *
 *  Gemeinsam, damit beide dieselbe Rückmeldung geben. Ausgewertet wird
 *  `angenommen` aus der Antwort, nicht nur, dass die Anfrage durchging:
 *  Vorher meldete jeder 2xx „Neue Mail ist unterwegs", auch wenn der
 *  Mailanbieter abgelehnt hatte — ein Haken für eine Mail, die nie kam.
 *
 *  status: null | 'sendet' | 'ok' | 'abgelehnt' | 'warten' | 'fehler'
 */
export function useErneutSenden() {
  const [status, setStatus] = useState(null)
  const [detail, setDetail] = useState(null)

  const senden = async () => {
    setStatus('sendet')
    setDetail(null)
    try {
      const { data } = await resendVerification()
      setStatus(data?.angenommen ? 'ok' : 'abgelehnt')
      return data
    } catch (e) {
      if (e.response?.status === 429) {
        setStatus('warten')
        setDetail(e.response.data?.detail || null)
      } else {
        setStatus('fehler')
      }
      return null
    }
  }

  return { status, detail, senden }
}

/** Die Rückmeldung zum Senden, einmal formuliert. */
export function SendeStatus({ status, detail }) {
  if (status === 'ok') {
    return (
      <p className="text-[12px] font-mono mt-2" style={{ color: '#22c55e' }}>
        ✓ Neue Mail ist unterwegs
      </p>
    )
  }
  if (status === 'abgelehnt' || status === 'fehler') {
    return (
      <p className="text-[12px] font-mono mt-2 leading-relaxed" style={{ color: '#ef4444' }}>
        ✕ Die Mail konnte nicht verschickt werden. Versuche es in ein paar
        Minuten erneut.
      </p>
    )
  }
  if (status === 'warten') {
    return (
      <p className="text-[12px] font-mono mt-2" style={{ color: '#f59e0b' }}>
        {detail || 'Bitte warte eine Minute, bevor du eine neue Mail anforderst.'}
      </p>
    )
  }
  return null
}

/**
 * Hinweis, solange die Adresse nicht bestätigt ist.
 *
 * Seit es das Sperrfenster vor der App gibt, sieht ihn nur noch, wer trotz
 * fehlender Bestätigung hineindarf — ein Admin. Für alle anderen erscheint
 * `BestaetigungsSperre` statt der App.
 */
export default function EmailBestaetigung({ email }) {
  const { status, detail, senden } = useErneutSenden()

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
        <SendeStatus status={status} detail={detail} />
      </div>
      <button
        onClick={senden}
        disabled={status === 'sendet'}
        className="px-3 py-1.5 rounded-lg text-[12px] font-mono tracking-wide disabled:opacity-40 flex-shrink-0"
        style={{ background: '#f59e0b20', border: '1px solid #f59e0b44', color: '#f59e0b' }}
      >
        {status === 'sendet' ? 'SENDET…' : 'ERNEUT SENDEN'}
      </button>
    </div>
  )
}
