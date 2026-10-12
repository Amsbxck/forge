import { useMemo } from 'react'
import { phaseFamilie } from '../utils/phasen'
import { knopfOptionen, wunschText } from '../utils/trainingsoptionen'

/** Knöpfe für die Wünsche, die eine Woche anders aussehen lassen.
 *
 *  Der Anlass: Einen Doppeltag zu bekommen heißt bisher, ihn zu tippen — und
 *  dafür muss man wissen, dass es ihn gibt und wie er heißt. Das Glossar
 *  darunter zeigt es, aber es ist zugeklappt.
 *
 *  **Keine Formatknöpfe.** Wie die Intervalle einer Woche aussehen, entscheidet
 *  die Rotation (`services/intervall_format.py`); sie liest, was zuletzt
 *  vorgegeben war, und wählt ein anderes Format. Ein Knopf daneben wäre eine
 *  zweite Quelle für dieselbe Entscheidung. Hier stehen deshalb nur Formen, bei
 *  denen die Woche eine andere Gestalt bekommt: die Doppeltage und die
 *  Blockwoche.
 *
 *  **Nichts wird gespeichert.** Jede Woche beginnt mit leerer Auswahl. Eine
 *  gemerkte Blockwoche, die sich stillschweigend wiederholt, wäre gefährlicher
 *  als bequem — die Studie hat vier Wochen untersucht, nicht eine Gewohnheit.
 *
 *  Die Auswahl wird **beim Absenden** zu Text (`wunschText`), nicht beim Klick
 *  in das Eingabefeld geschrieben — siehe `utils/trainingsoptionen.js`.
 */

const ACCENT = '#00d4ff'

export default function WunschKnoepfe({ phase, gewaehlt, onToggle, freitext }) {
  const familie = useMemo(() => phaseFamilie(phase), [phase])
  const optionen = useMemo(() => knopfOptionen(familie), [familie])

  if (!optionen.length) return null

  const vorschau = wunschText(gewaehlt, freitext)

  return (
    <div className="basis-full">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-[9px] font-mono tracking-widest text-[var(--text-muted)] shrink-0">
          DIESE WOCHE
        </span>
        {optionen.map(o => {
          const an = gewaehlt.has(o.id)
          return (
            <button
              key={o.id}
              type="button"
              onClick={() => onToggle(o.id)}
              title={o.kurz}
              className="text-[10px] font-mono tracking-wider px-2.5 py-1 rounded border transition-colors"
              style={{
                borderColor: an ? ACCENT : '#1e2228',
                color: an ? ACCENT : 'var(--text-muted)',
                background: an ? `${ACCENT}15` : '#0d0f17',
              }}
            >
              {an ? '✓ ' : '+ '}{o.kuerzel}
            </button>
          )
        })}
      </div>

      {/* Eine Vorschau, weil die Knöpfe den Text nicht mehr ins Feld
          schreiben. Ohne sie wüsste man nicht, was tatsächlich abgeschickt
          wird — und das ist bei einem Freitextwunsch die halbe Information. */}
      {vorschau && (
        <div className="mt-1.5 text-[10px] text-[var(--text-muted)] leading-snug">
          <span className="font-mono tracking-wider">WIRD GESENDET: </span>
          {vorschau}
        </div>
      )}
    </div>
  )
}
