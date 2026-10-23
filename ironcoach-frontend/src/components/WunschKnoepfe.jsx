import { useMemo } from 'react'
import { phaseFamilie } from '../utils/phasen'
import { knopfOptionen } from '../utils/trainingsoptionen'

/** Knöpfe für die Wünsche, die eine Woche anders aussehen lassen.
 *
 *  Der Anlass: Einen Doppeltag zu bekommen hieß bisher, ihn zu tippen — und
 *  dafür muss man wissen, dass es ihn gibt und wie er heißt. Das Glossar
 *  darunter zeigt es, aber es ist zugeklappt.
 *
 *  **Keine Formatknöpfe.** Wie die Intervalle einer Woche aussehen, entscheidet
 *  die Rotation (`services/intervall_format.py`); sie liest, was zuletzt
 *  vorgegeben war, und wählt ein anderes Format. Ein Knopf daneben wäre eine
 *  zweite Quelle für dieselbe Entscheidung. Hier stehen deshalb nur Formen, bei
 *  denen die Woche eine andere Gestalt bekommt: die Doppeltage und die
 *  Blockwoche. „Schwimmen + Kraft" ist keiner mehr — das macht der Coach bzw.
 *  die Doppeltag-Urne von selbst (`utils/trainingsoptionen.js`).
 *
 *  **Nichts wird gespeichert.** Jede Woche beginnt mit leerer Auswahl. Eine
 *  gemerkte Blockwoche, die sich stillschweigend wiederholt, wäre gefährlicher
 *  als bequem — die Studie hat vier Wochen untersucht, nicht eine Gewohnheit.
 *
 *  Nur die Knöpfe. Überschrift und die Vorschau „wird gesendet" stehen in
 *  `WunschKonsole`, weil die Vorschau Knöpfe **und** Freitext zeigt — sie
 *  gehört unter das Textfeld, nicht neben die Knöpfe.
 */

const ACCENT = '#00d4ff'

export default function WunschKnoepfe({ phase, gewaehlt, onToggle }) {
  const familie = useMemo(() => phaseFamilie(phase), [phase])
  const optionen = useMemo(() => knopfOptionen(familie), [familie])

  if (!optionen.length) return null

  return (
    <div className="flex flex-wrap gap-1.5">
      {optionen.map(o => {
        const an = gewaehlt.has(o.id)
        return (
          <button
            key={o.id}
            type="button"
            onClick={() => onToggle(o.id)}
            title={`${o.kurz}\n${o.bedingung}`}
            aria-pressed={an}
            className="text-[10px] font-mono tracking-wider px-2.5 py-1.5 rounded-md border transition-all"
            style={{
              borderColor: an ? ACCENT : '#1e2228',
              color: an ? ACCENT : 'var(--text-secondary)',
              background: an ? `${ACCENT}15` : '#0d0f17',
              boxShadow: an ? `0 0 12px ${ACCENT}22` : 'none',
            }}
          >
            {an ? '✓ ' : '+ '}{o.kuerzel}
          </button>
        )
      })}
    </div>
  )
}
