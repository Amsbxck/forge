import { useCallback, useEffect, useState } from 'react'
import { resetPassword, setToken, verifyEmail } from '../services/api'

const DISPLAY = { fontFamily: 'Barlow Condensed, sans-serif' }
const FIELD_STYLE = { background: '#0d0f17', border: '1px solid #1e2228' }
const LABEL = 'text-[10px] font-mono tracking-widest text-[var(--text-secondary)] block mb-1'

function Rahmen({ children }) {
  return (
    <div className="min-h-screen flex items-center justify-center px-4" style={{ background: '#07080f' }}>
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="text-5xl font-black tracking-widest select-none"
               style={{ ...DISPLAY, color: '#00d4ff', letterSpacing: '0.15em', textShadow: '0 0 30px #00d4ff44' }}>
            FORGE
          </div>
          <div className="text-[10px] font-mono tracking-widest text-[var(--text-muted)] mt-1">IRONCOACH AI</div>
        </div>
        <div className="rounded-xl p-6 space-y-4" style={{ background: '#111318', border: '1px solid #1e2228' }}>
          {children}
        </div>
      </div>
    </div>
  )
}

function Fehler({ text }) {
  if (!text) return null
  return (
    <div className="rounded-lg px-3 py-2 font-mono text-xs"
         style={{ background: '#ef444415', border: '1px solid #ef444430', color: '#ef4444' }}>
      {text}
    </div>
  )
}

function meldung(err, fallback) {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail[0]?.msg || fallback
  return fallback
}

/** Bestätigungslink aus der Willkommensmail.
 *
 *  Der Link meldet gleich an: wer sein Postfach öffnen konnte, hat die
 *  Adresse belegt — ihn danach noch ein Passwort eintippen zu lassen wäre
 *  eine Hürde ohne Gewinn.
 */
export function VerifyPage({ onAuthenticated }) {
  const [state, setState] = useState('laeuft')   // laeuft | ok | fehler
  const [fehler, setFehler] = useState(null)

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get('token')
    if (!token) { setState('fehler'); setFehler('Im Link fehlt das Token.'); return }
    verifyEmail(token)
      .then(({ data }) => {
        setToken(data.access_token)
        setState('ok')
        // Kurz stehenlassen, damit die Bestätigung wahrgenommen wird.
        setTimeout(() => { window.history.replaceState({}, '', '/'); onAuthenticated(data) }, 1200)
      })
      .catch(err => { setState('fehler'); setFehler(meldung(err, 'Bestätigung fehlgeschlagen')) })
  }, [onAuthenticated])

  return (
    <Rahmen>
      {state === 'laeuft' && (
        <p className="font-mono text-xs tracking-widest text-[var(--text-muted)] text-center py-4">PRÜFT LINK…</p>
      )}
      {state === 'ok' && (
        <div className="text-center py-2">
          <div className="text-2xl font-black" style={{ ...DISPLAY, color: '#22c55e' }}>ADRESSE BESTÄTIGT</div>
          <p className="text-xs font-mono text-[var(--text-muted)] mt-2">Du wirst angemeldet…</p>
        </div>
      )}
      {state === 'fehler' && (
        <>
          <div className="text-xl font-black text-[#e8eaf0]" style={DISPLAY}>LINK UNGÜLTIG</div>
          <Fehler text={fehler} />
          <p className="text-[11px] font-mono text-[var(--text-muted)] leading-relaxed">
            Melde dich an und fordere im Profil eine neue Bestätigung an.
          </p>
          <a href="/" className="block text-center py-2.5 rounded-lg text-sm font-mono font-bold tracking-wide"
             style={{ background: '#00d4ff20', border: '1px solid #00d4ff44', color: '#00d4ff' }}>
            ZUR ANMELDUNG
          </a>
        </>
      )}
    </Rahmen>
  )
}

/** Neues Passwort über den Link aus der Mail setzen. */
export function ResetPage({ onAuthenticated }) {
  const [token] = useState(() => new URLSearchParams(window.location.search).get('token'))
  const [passwort, setPasswort] = useState('')
  const [wiederholung, setWiederholung] = useState('')
  const [fehler, setFehler] = useState(null)
  const [busy, setBusy] = useState(false)

  const submit = useCallback(async (e) => {
    e.preventDefault()
    if (passwort !== wiederholung) { setFehler('Die beiden Passwörter stimmen nicht überein.'); return }
    setFehler(null); setBusy(true)
    try {
      const { data } = await resetPassword(token, passwort)
      setToken(data.access_token)
      window.history.replaceState({}, '', '/')
      onAuthenticated(data)
    } catch (err) {
      setFehler(meldung(err, 'Zurücksetzen fehlgeschlagen'))
    } finally { setBusy(false) }
  }, [token, passwort, wiederholung, onAuthenticated])

  if (!token) {
    return (
      <Rahmen>
        <div className="text-xl font-black text-[#e8eaf0]" style={DISPLAY}>LINK UNVOLLSTÄNDIG</div>
        <p className="text-[11px] font-mono text-[var(--text-muted)]">Im Link fehlt das Token.</p>
        <a href="/" className="block text-center py-2.5 rounded-lg text-sm font-mono font-bold tracking-wide"
           style={{ background: '#00d4ff20', border: '1px solid #00d4ff44', color: '#00d4ff' }}>
          ZUR ANMELDUNG
        </a>
      </Rahmen>
    )
  }

  return (
    <Rahmen>
      <form onSubmit={submit} className="space-y-4">
        <div>
          <div className="text-xl font-black text-[#e8eaf0]" style={DISPLAY}>NEUES PASSWORT</div>
          <p className="text-[11px] font-mono text-[var(--text-muted)] mt-1">
            Danach werden alle angemeldeten Geräte abgemeldet.
          </p>
        </div>

        <label className="block">
          <span className={LABEL}>NEUES PASSWORT (MIND. 8 ZEICHEN)</span>
          <input type="password" required minLength={8} autoComplete="new-password" autoFocus
                 className="rounded-lg px-3 py-2 text-sm font-mono text-[#e8eaf0] outline-none w-full"
                 style={FIELD_STYLE} value={passwort} onChange={e => setPasswort(e.target.value)} />
        </label>

        <label className="block">
          <span className={LABEL}>WIEDERHOLEN</span>
          <input type="password" required autoComplete="new-password"
                 className="rounded-lg px-3 py-2 text-sm font-mono text-[#e8eaf0] outline-none w-full"
                 style={FIELD_STYLE} value={wiederholung} onChange={e => setWiederholung(e.target.value)} />
        </label>

        <Fehler text={fehler} />

        <button type="submit" disabled={busy}
                className="w-full py-2.5 rounded-lg text-sm font-mono font-bold tracking-wide disabled:opacity-40"
                style={{ background: '#00d4ff20', border: '1px solid #00d4ff44', color: '#00d4ff' }}>
          {busy ? '…' : 'PASSWORT SETZEN'}
        </button>
      </form>
    </Rahmen>
  )
}
