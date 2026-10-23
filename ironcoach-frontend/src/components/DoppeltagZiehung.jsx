import { useEffect, useState } from 'react'
import HrvAmpel from './HrvAmpel'

/** Der Doppeltag, den die App für diese Woche gezogen hat — vor dem Erstellen.
 *
 *  Die Form kommt aus einer Urne (`services/doppel_urne.py`), gewichtet nach
 *  HRV und Vorwochen und mit Athlet und Montag gesät: Was hier steht, ist
 *  genau das, was der Plan bekommt. Sie geht in den einen Erstell-Aufruf mit.
 *
 *  **Hier und nicht nach dem Erstellen.** Ein Zwischenentwurf schlug
 *  Doppeltage nach dem Erstellen zum Annehmen vor. Jede Annahme war ein
 *  zweiter Claude-Aufruf und fügte eine Einheit hinzu, statt die Woche
 *  umzubauen. Abschalten kostet hier nichts.
 *
 *  **Oben die HRV als Ampel** (`HrvAmpel`), weil sie das stärkste Gewicht in
 *  der Urne ist. Der Text darunter nennt deshalb nur noch den Rest
 *  (`hinweise`), nicht noch einmal „HRV normal".
 *
 *  **Der Balken ist die Urne.** Jedes Segment ist eine Kugel, so breit wie ihr
 *  Gewicht nach HRV und Rotation; das gezogene leuchtet, eine Marke darüber
 *  zeigt darauf. Ohne ihn wäre die Ziehung eine Behauptung — so sieht man,
 *  dass „keiner" auch drin lag und warum etwa die Doppelschwelle fehlt.
 *
 *  **Nichts wird gespeichert.** „Ohne Doppeltag" gilt für die angezeigte Woche.
 *  Eine gemerkte Abwahl würde sich still jede Woche wiederholen.
 */

const ACCENT = '#00d4ff'

// Kurz genug für ein Segment; die Reihenfolge ist fest, damit der Balken von
// Woche zu Woche vergleichbar bleibt.
const KUGELN = [
  ['schwimmen_als_zweite', 'Schwimmen'],
  ['locker_plus_qualitaet', 'Locker + Q'],
  ['langer_lauf_geteilt', 'Lauf teilen'],
  ['doppelschwelle_leicht', 'Doppelschwelle'],
  ['kein', 'keiner'],
]

function Urne({ gewichte, gezogen, aus }) {
  // Einlaufen beim ersten Zeichnen: Die Segmente wachsen von null auf ihr
  // Gewicht. Einmal, nicht bei jedem Neuzeichnen — sonst zuckt der Balken
  // bei jedem Tastendruck im Wunschfeld.
  const [da, setDa] = useState(false)
  useEffect(() => {
    const t = requestAnimationFrame(() => setDa(true))
    return () => cancelAnimationFrame(t)
  }, [])

  const kugeln = KUGELN.filter(([k]) => (gewichte?.[k] || 0) > 0)
  if (kugeln.length < 2) return null
  const summe = kugeln.reduce((s, [k]) => s + gewichte[k], 0)
  const treffer = aus ? null : (gezogen || 'kein')

  return (
    <div className="mt-4">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[9px] font-mono tracking-[0.2em] text-[var(--text-muted)]">URNE</span>
        <span className="text-[9px] font-mono text-[var(--text-muted)]">
          {kugeln.length} KUGELN
        </span>
      </div>

      {/* Die Marke über dem Treffer — eine eigene Zeile mit denselben
          Breiten, damit sie genau über ihrem Segment steht. */}
      <div className="flex gap-[3px] h-2">
        {kugeln.map(([k]) => (
          <div key={k} className="flex justify-center" style={{ flexGrow: gewichte[k], flexBasis: 0 }}>
            {k === treffer && (
              <span
                className="block w-0 h-0"
                style={{
                  borderLeft: '4px solid transparent',
                  borderRight: '4px solid transparent',
                  borderTop: `5px solid ${ACCENT}`,
                  filter: `drop-shadow(0 0 4px ${ACCENT})`,
                }}
              />
            )}
          </div>
        ))}
      </div>

      <div className="flex gap-[3px] h-2.5 mt-0.5">
        {kugeln.map(([k, name]) => {
          const an = k === treffer
          const anteil = Math.round((gewichte[k] / summe) * 100)
          return (
            <div
              key={k}
              title={`${name}: ${anteil} %`}
              className="relative h-full rounded-[3px] overflow-hidden transition-[flex-grow] duration-700 ease-out"
              style={{
                flexGrow: da ? gewichte[k] : 0.0001,
                flexBasis: 0,
                background: an
                  ? `linear-gradient(90deg, ${ACCENT}aa, ${ACCENT})`
                  : k === 'kein' ? '#1a1e25' : '#173039',
                boxShadow: an ? `0 0 12px ${ACCENT}88, inset 0 0 0 1px ${ACCENT}` : 'inset 0 0 0 1px #ffffff08',
                // Schraffiert für „keiner": eine Kugel, aber keine Form.
                backgroundImage: !an && k === 'kein'
                  ? 'repeating-linear-gradient(135deg, transparent 0 3px, #0a0c0f 3px 5px)'
                  : undefined,
              }}
            >
              {/* Ein Lichtstreif über den Treffer — die Kugel, die gefallen ist. */}
              {an && (
                <span
                  className="absolute inset-y-0 w-1/2"
                  style={{
                    background: 'linear-gradient(90deg, transparent, #ffffff66, transparent)',
                    animation: 'urne-glanz 2.8s ease-in-out infinite',
                  }}
                />
              )}
            </div>
          )
        })}
      </div>

      <div className="flex gap-[3px] mt-1.5">
        {kugeln.map(([k, name]) => {
          const an = k === treffer
          return (
            <div key={k} className="min-w-0" style={{ flexGrow: gewichte[k], flexBasis: 0 }}>
              <div
                className="text-[9px] font-mono truncate"
                style={{ color: an ? ACCENT : 'var(--text-secondary)' }}
              >
                {name}
              </div>
              <div className="text-[9px] font-mono tabular-nums" style={{ color: an ? `${ACCENT}bb` : 'var(--text-muted)' }}>
                {Math.round((gewichte[k] / summe) * 100)}%
              </div>
            </div>
          )
        })}
      </div>

      <style>{`
        @keyframes urne-glanz {
          0% { left: -50%; }
          60%, 100% { left: 110%; }
        }
      `}</style>
    </div>
  )
}

export default function DoppeltagZiehung({ ziehung, aus, ersetzt, onToggle }) {
  if (!ziehung) return null

  const gezogen = ziehung.form
  // Ein gewählter Doppeltag-Knopf oder eine Blockwoche ersetzt die Ziehung.
  // Zwei Doppeltage wären eine Verdichtung, die niemand bestellt hat.
  const aktiv = gezogen && !aus && !ersetzt
  // Ältere Antworten ohne `hinweise` (Backend noch nicht neu) zeigen den
  // ganzen Grund — lieber einmal „HRV normal" doppelt als gar keinen Grund.
  const hinweis = ziehung.hinweise ? ziehung.hinweise.join(' · ') : ziehung.grund

  return (
    <div>
      <HrvAmpel hrv={ziehung.hrv} />

      <div className={`flex items-baseline justify-between gap-2 ${ziehung.hrv ? 'mt-4' : ''}`}>
        <div
          className="text-xl font-bold tracking-wide leading-tight"
          style={{
            fontFamily: 'Barlow Condensed, sans-serif',
            color: aktiv ? '#e8eaf0' : 'var(--text-muted)',
            textDecoration: gezogen && !aktiv ? 'line-through' : 'none',
          }}
        >
          {gezogen ? ziehung.titel.toUpperCase() : 'KEIN DOPPELTAG'}
        </div>
        {gezogen && !ersetzt && (
          <button
            type="button"
            onClick={onToggle}
            className="shrink-0 text-[9px] font-mono tracking-widest px-2 py-1 rounded border transition-colors hover:text-[#e8eaf0]"
            style={{ borderColor: '#1e2228', color: 'var(--text-muted)', background: '#0d0f17' }}
          >
            {aus ? '+ DOCH MIT' : '× OHNE'}
          </button>
        )}
      </div>

      {ersetzt && gezogen ? (
        <div className="text-[10px] font-mono text-[var(--text-muted)] mt-1">
          ersetzt durch deine Auswahl
        </div>
      ) : hinweis && (
        <div className="text-[11px] text-[var(--text-secondary)] mt-1 leading-snug">
          {hinweis}
        </div>
      )}

      <Urne gewichte={ziehung.gewichte} gezogen={gezogen} aus={aus || ersetzt} />
    </div>
  )
}
