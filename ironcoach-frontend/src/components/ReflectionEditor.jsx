import { useEffect, useState } from 'react'
import { updateReflection } from '../services/api'

/** Reflexion zu einer Einheit schreiben.
 *
 *  Eine Fassung für beide Orte — Detailansicht und aufgeklappte Kachel im
 *  Dashboard. Zwei Kopien hätten früher oder später unterschiedlich
 *  gespeichert.
 *
 *  Der Text geht beim Speichern sofort nach Obsidian. Steht in der Note
 *  bereits etwas, das dort geschrieben wurde, hat das Vorrang — deshalb kann
 *  die Antwort einen anderen Text zurückgeben als den abgeschickten.
 */
export default function ReflectionEditor({ session, rows = 3, onSaved }) {
  const [text, setText] = useState(session.reflection || '')
  const [state, setState] = useState('idle')   // idle | saving | saved | error
  const [hinweis, setHinweis] = useState(null)

  // Wechselt die Einheit, muss der Text mitwechseln.
  useEffect(() => {
    setText(session.reflection || '')
    setState('idle')
    setHinweis(null)
  }, [session.id, session.reflection])

  const save = async () => {
    setState('saving')
    try {
      const { data } = await updateReflection(session.id, text)
      const zurueck = data?.reflection || ''
      if (zurueck !== text) {
        // Der Vault hatte eine neuere Fassung. Sie kommentarlos anzuzeigen
        // sähe aus, als wäre das Speichern fehlgeschlagen.
        setText(zurueck)
        setHinweis('Im Vault stand eine neuere Fassung — sie hat Vorrang und steht jetzt hier.')
      }
      setState('saved')
      setTimeout(() => setState(s => (s === 'saved' ? 'idle' : s)), 2500)
      onSaved?.(data)
    } catch {
      setState('error')
    }
  }

  const dirty = text !== (session.reflection || '')

  return (
    <div>
      <textarea
        value={text}
        onChange={e => setText(e.target.value)}
        rows={rows}
        placeholder="Wie hat es sich angefühlt? Was war anders als geplant? Verpflegung, Schlaf, Kopf …"
        className="w-full rounded-lg px-3 py-2 text-sm text-[#e8eaf0] placeholder-[var(--text-muted)] outline-none resize-y leading-relaxed"
        style={{ background: '#0d0f17', border: '1px solid #1e2228' }}
      />
      <div className="flex items-center gap-3 mt-2 flex-wrap">
        <button
          onClick={save} disabled={!dirty || state === 'saving'}
          className="px-3 py-1.5 rounded-lg text-[11px] font-mono tracking-wide disabled:opacity-30"
          style={{ background: '#00d4ff18', border: '1px solid #00d4ff33', color: '#00d4ff' }}
        >
          {state === 'saving' ? 'SPEICHERT…' : 'SPEICHERN'}
        </button>
        {state === 'saved' && <span className="text-[11px] font-mono" style={{ color: '#22c55e' }}>✓ gespeichert</span>}
        {state === 'error' && <span className="text-[11px] font-mono" style={{ color: '#ef4444' }}>Speichern fehlgeschlagen</span>}
        <span className="text-[10px] font-mono text-[var(--text-muted)]">
          Der Coach liest das bei der nächsten Planung mit.
          {session.obsidian_path && ' Was in Obsidian steht, hat Vorrang.'}
        </span>
      </div>
      {hinweis && (
        <div className="text-[10px] font-mono mt-2" style={{ color: '#eab308' }}>{hinweis}</div>
      )}
    </div>
  )
}
