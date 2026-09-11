import { useState } from 'react'
import Modal from './Modal'
import { changePassword, setToken } from '../services/api'

const LABEL = 'text-[10px] font-mono tracking-widest text-[var(--text-secondary)]'
const DISPLAY = { fontFamily: 'Barlow Condensed, sans-serif' }
const FIELD = 'rounded-lg px-3 py-2 text-sm font-mono text-[#e8eaf0] placeholder-[var(--text-muted)] outline-none w-full'
const FIELD_STYLE = { background: '#0d0f17', border: '1px solid #1e2228' }

export default function PasswordChange() {
  const [open, setOpen] = useState(false)
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [repeat, setRepeat] = useState('')
  const [state, setState] = useState('idle')
  const [error, setError] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    setError(null)
    if (next !== repeat) {
      setError('Die beiden neuen Passwörter stimmen nicht überein')
      return
    }
    setState('saving')
    try {
      const { data } = await changePassword(current, next)
      // Der Server schickt ein frisches Token — sonst hinge die Sitzung am
      // alten Passwort und liefe beim nächsten Neuladen in eine Abmeldung.
      setToken(data.access_token)
      setState('done')
      setCurrent(''); setNext(''); setRepeat('')
    } catch (err) {
      const detail = err.response?.data?.detail
      setError(
        typeof detail === 'string' ? detail
          : Array.isArray(detail) ? (detail[0]?.msg || 'Eingabe ungültig')
          : 'Änderung fehlgeschlagen'
      )
      setState('idle')
    }
  }

  return (
    <div className="bg-[#111318] border border-[#1e2228] rounded-xl p-5">
      <button
        onClick={() => { setOpen(true); setState('idle'); setError(null) }}
        className="w-full flex items-center justify-between gap-3"
      >
        <span>
          <span className="text-lg font-black tracking-tight text-[#e8eaf0] block text-left" style={DISPLAY}>
            PASSWORT
          </span>
          <span className="text-xs text-[var(--text-secondary)]">
            {state === 'done' ? 'Geändert.' : 'Zugangsdaten ändern'}
          </span>
        </span>
        <span className="text-[10px] font-mono text-[var(--text-muted)]">ÄNDERN ▸</span>
      </button>

      <Modal
        open={open} onClose={() => setOpen(false)}
        title="PASSWORT ÄNDERN" subtitle="Du bleibst danach angemeldet"
        width="max-w-sm"
      >
        <form onSubmit={submit} className="space-y-3">
          <label className="block">
            <span className={`${LABEL} block mb-1`}>AKTUELLES PASSWORT</span>
            <input type="password" required autoComplete="current-password"
                   className={FIELD} style={FIELD_STYLE}
                   value={current} onChange={e => setCurrent(e.target.value)} />
          </label>
          <label className="block">
            <span className={`${LABEL} block mb-1`}>NEUES PASSWORT (MIND. 8 ZEICHEN)</span>
            <input type="password" required minLength={8} autoComplete="new-password"
                   className={FIELD} style={FIELD_STYLE}
                   value={next} onChange={e => setNext(e.target.value)} />
          </label>
          <label className="block">
            <span className={`${LABEL} block mb-1`}>NEUES PASSWORT WIEDERHOLEN</span>
            <input type="password" required autoComplete="new-password"
                   className={FIELD} style={FIELD_STYLE}
                   value={repeat} onChange={e => setRepeat(e.target.value)} />
          </label>

          {error && (
            <div className="rounded-lg px-3 py-2 font-mono text-[11px]"
                 style={{ background: '#ef444415', border: '1px solid #ef444430', color: '#ef4444' }}>
              {error}
            </div>
          )}
          {state === 'done' && (
            <div className="rounded-lg px-3 py-2 font-mono text-[11px]"
                 style={{ background: '#22c55e12', border: '1px solid #22c55e33', color: '#22c55e' }}>
              ✓ Passwort geändert — du bleibst angemeldet.
            </div>
          )}

          <button type="submit" disabled={state === 'saving'}
                  className="px-4 py-2 rounded-lg text-sm font-mono font-bold disabled:opacity-40"
                  style={{ background: '#00d4ff20', border: '1px solid #00d4ff44', color: '#00d4ff' }}>
            {state === 'saving' ? 'ÄNDERT…' : 'PASSWORT ÄNDERN'}
          </button>
        </form>
      </Modal>
    </div>
  )
}
