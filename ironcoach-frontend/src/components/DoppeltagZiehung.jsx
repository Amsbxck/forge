import HrvAmpel from './HrvAmpel'
import SegmentLeiste from './leisten/SegmentLeiste'

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
 *  dass „keiner" auch drin lag und warum etwa die Doppelschwelle fehlt. Die
 *  Leiste selbst ist ein gemeinsamer Baustein (`leisten/SegmentLeiste`).
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
  // Eine einzige Kugel ist keine Ziehung (Off Season, Deload) — dann keine Leiste.
  if (kugeln.length < 2) return null
  const treffer = aus ? null : (gezogen || 'kein')
  return (
    <div className="mt-4">
      <SegmentLeiste
        kopf="URNE"
        kopfRechts={`${kugeln.length} KUGELN`}
        treffer={treffer}
        markenZeile
        segmente={kugeln.map(([k, name]) => ({
          key: k,
          name,
          wert: gewichte[k],
          // Die gezogene in Akzent, die übrigen gedämpft; „keiner" schraffiert:
          // eine Kugel, aber keine Form.
          farbe: k === treffer ? ACCENT : k === 'kein' ? '#1a1e25' : '#173039',
          schraffiert: k === 'kein',
        }))}
      />
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
