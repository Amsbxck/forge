import { useState } from 'react'
import { forgotPassword, login, register, setToken } from '../services/api'

const DISPLAY = { fontFamily: 'Barlow Condensed, sans-serif' }
const FIELD_STYLE = { background: '#0d0f17', border: '1px solid #1e2228' }

export default function Login({ onAuthenticated }) {
  const [mode, setMode] = useState('login')   // login | register | forgot
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState(null)
  const [hinweis, setHinweis] = useState(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setError(null)
    setHinweis(null)
    setBusy(true)
    try {
      if (mode === 'forgot') {
        const { data } = await forgotPassword(email)
        setHinweis(data.message)
        setBusy(false)
        return
      }
      const { data } = mode === 'login'
        ? await login(email, password)
        : await register(email, password, name || null)
      setToken(data.access_token)
      onAuthenticated(data)
    } catch (err) {
      const detail = err.response?.data?.detail
      setError(
        typeof detail === 'string'
          ? detail
          : Array.isArray(detail)
            // Pydantic liefert eine Liste — die erste Meldung reicht dem Nutzer.
            ? detail[0]?.msg || 'Eingabe ungültig'
            : 'Anmeldung fehlgeschlagen'
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4" style={{ background: '#07080f' }}>
      <div className="w-full max-w-sm">
        {/* Wortmarke wie in der Navigation */}
        <div className="text-center mb-8">
          <div
            className="text-5xl font-black tracking-widest select-none"
            style={{ ...DISPLAY, color: '#00d4ff', letterSpacing: '0.15em', textShadow: '0 0 30px #00d4ff44' }}
          >
            FORGE
          </div>
          <div className="text-[10px] font-mono tracking-widest text-[var(--text-muted)] mt-1">
            IRONCOACH AI
          </div>
        </div>

        <form
          onSubmit={submit}
          className="rounded-xl p-6 space-y-4"
          style={{ background: '#111318', border: '1px solid #1e2228' }}
        >
          <div className="flex gap-1 p-0.5 rounded-lg" style={{ background: '#0d0f17' }}>
            {[
              { key: 'login', label: 'ANMELDEN' },
              { key: 'register', label: 'KONTO ANLEGEN' },
            ].map(t => (
              <button
                key={t.key}
                type="button"
                onClick={() => { setMode(t.key); setError(null); setHinweis(null) }}
                className="flex-1 py-1.5 rounded-md text-[11px] font-mono tracking-wide transition-all"
                style={{
                  background: mode === t.key ? '#00d4ff20' : 'transparent',
                  color: mode === t.key ? '#00d4ff' : 'var(--text-muted)',
                  border: mode === t.key ? '1px solid #00d4ff33' : '1px solid transparent',
                }}
              >
                {t.label}
              </button>
            ))}
          </div>

          {mode === 'register' && (
            <label className="block">
              <span className="text-[10px] font-mono tracking-widest text-[var(--text-secondary)] block mb-1">NAME</span>
              <input
                className="rounded-lg px-3 py-2 text-sm font-mono text-[#e8eaf0] placeholder-[var(--text-muted)] outline-none w-full"
                style={FIELD_STYLE} value={name} onChange={e => setName(e.target.value)}
                placeholder="Wie sollen wir dich nennen?" autoComplete="name"
              />
            </label>
          )}

          <label className="block">
            <span className="text-[10px] font-mono tracking-widest text-[var(--text-secondary)] block mb-1">E-MAIL</span>
            <input
              type="email" required autoComplete="email"
              className="rounded-lg px-3 py-2 text-sm font-mono text-[#e8eaf0] placeholder-[var(--text-muted)] outline-none w-full"
              style={FIELD_STYLE} value={email} onChange={e => setEmail(e.target.value)}
              placeholder="du@beispiel.de"
            />
          </label>

          {mode !== 'forgot' && (
          <label className="block">
            <span className="text-[10px] font-mono tracking-widest text-[var(--text-secondary)] block mb-1">
              PASSWORT{mode === 'register' ? ' (MIND. 8 ZEICHEN)' : ''}
            </span>
            <input
              type="password" required minLength={mode === 'register' ? 8 : undefined}
              autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
              className="rounded-lg px-3 py-2 text-sm font-mono text-[#e8eaf0] placeholder-[var(--text-muted)] outline-none w-full"
              style={FIELD_STYLE} value={password} onChange={e => setPassword(e.target.value)}
              placeholder="••••••••"
            />
          </label>
          )}

          {hinweis && (
            <div className="rounded-lg px-3 py-2 font-mono text-xs leading-relaxed"
                 style={{ background: '#22c55e12', border: '1px solid #22c55e33', color: '#22c55e' }}>
              {hinweis}
            </div>
          )}

          {error && (
            <div className="rounded-lg px-3 py-2 font-mono text-xs"
                 style={{ background: '#ef444415', border: '1px solid #ef444430', color: '#ef4444' }}>
              {error}
            </div>
          )}

          <button
            type="submit" disabled={busy}
            className="w-full py-2.5 rounded-lg text-sm font-mono font-bold tracking-wide transition-all disabled:opacity-40"
            style={{ background: '#00d4ff20', border: '1px solid #00d4ff44', color: '#00d4ff' }}
          >
            {busy ? '…' : mode === 'login' ? 'ANMELDEN'
              : mode === 'register' ? 'KONTO ANLEGEN'
              : 'LINK ANFORDERN'}
          </button>

          {mode === 'login' && (
            <button type="button"
                    onClick={() => { setMode('forgot'); setError(null); setHinweis(null) }}
                    className="w-full text-[10px] font-mono text-[var(--text-muted)] hover:text-[#00d4ff] transition-colors">
              PASSWORT VERGESSEN?
            </button>
          )}

          {mode === 'forgot' && (
            <>
              <p className="text-[10px] font-mono text-[var(--text-muted)] leading-relaxed">
                Wir schicken dir einen Link zum Zurücksetzen. Er gilt zwei Stunden
                und lässt sich einmal verwenden.
              </p>
              <button type="button"
                      onClick={() => { setMode('login'); setError(null); setHinweis(null) }}
                      className="w-full text-[10px] font-mono text-[var(--text-muted)] hover:text-[#00d4ff] transition-colors">
                ZURÜCK ZUR ANMELDUNG
              </button>
            </>
          )}

          {mode === 'register' && (
            <p className="text-[10px] font-mono text-[var(--text-muted)] leading-relaxed">
              Für ein neues Konto. Eine bereits vergebene E-Mail wird abgelehnt —
              ein bestehendes Konto lässt sich nicht auf diesem Weg übernehmen.
            </p>
          )}
        </form>
      </div>
    </div>
  )
}
