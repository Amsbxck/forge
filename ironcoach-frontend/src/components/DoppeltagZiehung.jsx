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
 *  **Der Balken ist die Urne.** Jedes Segment ist eine Kugel, so breit wie ihr
 *  Gewicht nach HRV und Rotation; das gezogene leuchtet. Ohne ihn wäre die
 *  Ziehung eine Behauptung — so sieht man, dass „keiner" auch drin lag und
 *  warum etwa die Doppelschwelle fehlt.
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
  const kugeln = KUGELN.filter(([k]) => (gewichte?.[k] || 0) > 0)
  if (kugeln.length < 2) return null
  const summe = kugeln.reduce((s, [k]) => s + gewichte[k], 0)

  return (
    <div className="mt-3">
      <div className="flex h-1.5 rounded-full overflow-hidden gap-px bg-[#0a0c0f]">
        {kugeln.map(([k, name]) => {
          const treffer = !aus && k === (gezogen || 'kein')
          return (
            <div
              key={k}
              title={`${name}: ${Math.round((gewichte[k] / summe) * 100)} %`}
              className="h-full transition-all duration-500"
              style={{
                flexGrow: gewichte[k],
                background: treffer ? ACCENT : k === 'kein' ? '#2a2f38' : '#1e3a44',
                boxShadow: treffer ? `0 0 10px ${ACCENT}` : 'none',
                // Gestrichelt für „keiner": eine Kugel, aber keine Form.
                backgroundImage: !treffer && k === 'kein'
                  ? 'repeating-linear-gradient(135deg, transparent 0 3px, #0a0c0f 3px 5px)'
                  : 'none',
              }}
            />
          )
        })}
      </div>
      <div className="flex gap-px mt-1">
        {kugeln.map(([k, name]) => (
          <span
            key={k}
            className="text-[9px] font-mono truncate"
            style={{
              flexGrow: gewichte[k],
              flexBasis: 0,
              color: !aus && k === (gezogen || 'kein') ? ACCENT : 'var(--text-muted)',
            }}
          >
            {name}
          </span>
        ))}
      </div>
    </div>
  )
}

export default function DoppeltagZiehung({ ziehung, aus, ersetzt, onToggle }) {
  if (!ziehung) return null

  const gezogen = ziehung.form
  // Ein gewählter Doppeltag-Knopf oder eine Blockwoche ersetzt die Ziehung.
  // Zwei Doppeltage wären eine Verdichtung, die niemand bestellt hat.
  const aktiv = gezogen && !aus && !ersetzt

  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
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
      ) : ziehung.grund && (
        <div className="text-[11px] text-[var(--text-secondary)] mt-1 leading-snug">
          {ziehung.grund}
        </div>
      )}

      <Urne gewichte={ziehung.gewichte} gezogen={gezogen} aus={aus || ersetzt} />
    </div>
  )
}
