import { useCallback, useEffect, useState } from 'react'
import { getBudget, getBudgetUsage } from '../services/api'
import SegmentLeiste from './leisten/SegmentLeiste'

const CARD = 'bg-[#111318] border border-[#1e2228] rounded-xl'
const DISPLAY = { fontFamily: 'Barlow Condensed, sans-serif' }

const ART = { plan: 'Weekly plan', plan_adjust: 'Adjustment', chat: 'Coach chat' }

// Ruhige Abstufung statt bunter Kategorien: Es geht um „wofür ging es weg",
// nicht um eine Ampel. Der Plan als teuerster Posten in der Akzentfarbe.
const ART_FARBE = { plan: '#00d4ff', plan_adjust: '#0e7490', chat: '#5b6475' }

/** Wie oft reicht der Rest noch — je Art aus dem eigenen Schnitt.
 *
 *  „or", nicht „and": Der Rest reicht für das eine **oder** das andere.
 *
 *  „1,84 € übrig" sagt einem Athleten wenig, „≈ 9 Pläne" sagt ihm, ob er sich
 *  Sorgen machen muss. Gerechnet mit dem eigenen Schnitt (`je_art` aus
 *  `/budget`, ohne offene Reservierungen), nicht mit einem festen Preis: Ein
 *  Plan mit langem Verlauf kostet mehr als einer im ersten Monat. Ohne
 *  bisherigen Aufruf einer Art fehlt ihr Schnitt, dann steht sie nicht da.
 */
function reichweite(stand) {
  const je = stand.je_art || {}
  return [['plan', 'plans', 'plan'], ['chat', 'chats', 'chat']]
    .filter(([art]) => je[art]?.schnitt_eur > 0)
    .map(([art, mehrzahl, einzahl]) => {
      const n = Math.floor(stand.rest_eur / je[art].schnitt_eur)
      return `${n.toLocaleString('en-GB')} ${n === 1 ? einzahl : mehrzahl}`
    })
}

/** Guthaben für die Plangenerierung.
 *
 *  Alle Athleten laufen über einen gemeinsamen API-Schlüssel, aber jeder
 *  verbraucht sein eigenes Guthaben. Ohne sichtbaren Stand bemerkt man das
 *  Ende erst, wenn ein Plan nicht mehr erstellt wird — deshalb steht hier,
 *  was übrig ist und wofür es verbraucht wurde.
 */
export default function ApiBudget() {
  const [stand, setStand] = useState(null)
  const [verlauf, setVerlauf] = useState([])
  const [offen, setOffen] = useState(false)

  const laden = useCallback(async () => {
    try {
      const [b, v] = await Promise.all([getBudget(), getBudgetUsage()])
      setStand(b.data)
      setVerlauf(v.data || [])
    } catch { /* still */ }
  }, [])
  useEffect(() => { laden() }, [laden])

  if (!stand) return null

  const anteil = stand.guthaben_eur > 0
    ? Math.min(1, stand.verbraucht_eur / stand.guthaben_eur)
    : 1
  const farbe = stand.aufgebraucht ? '#ef4444' : anteil > 0.8 ? '#f59e0b' : '#00d4ff'
  const reicht = stand.aufgebraucht ? [] : reichweite(stand)
  const segmente = Object.entries(stand.je_art || {}).map(([art, w]) => ({
    key: art,
    name: ART[art] || art,
    wert: w.summe_eur,
    farbe: ART_FARBE[art] || '#3a4150',
  }))

  return (
    <div className={`${CARD} p-5`}>
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          {/* Kopf wie die übrigen Kacheln; die Farbe des Stands trägt die Zahl. */}
          <div className="text-xs font-mono tracking-[0.25em] text-[var(--text-secondary)] mb-3">
            COACH CREDIT
          </div>
          <div className="font-black leading-none mt-2"
               style={{ ...DISPLAY, color: farbe, fontSize: 'clamp(2.4rem, 5vw, 3.2rem)' }}>
            {stand.rest_eur.toFixed(2)}
            <span className="text-lg font-normal text-[var(--text-secondary)] ml-1">€ left</span>
          </div>
          <div className="text-[10px] font-mono text-[var(--text-muted)] mt-1.5">
            {stand.verbraucht_eur.toFixed(2)} € of{' '}
            {stand.guthaben_eur.toFixed(2)} € used · {stand.aufrufe} calls
          </div>
          {reicht.length > 0 && (
            <div className="text-[11px] font-mono text-[var(--text-secondary)] mt-1">
              enough for ≈ <span className="tabular-nums" style={{ color: farbe }}>{reicht.join(' or ')}</span>
            </div>
          )}
        </div>
        {verlauf.length > 0 && (
          <button onClick={() => setOffen(o => !o)}
                  className="text-[10px] font-mono text-[var(--text-muted)] hover:text-[#00d4ff]">
            {offen ? 'CLOSE' : 'VIEW USAGE'}
          </button>
        )}
      </div>

      {/* Balken: der Rest ist wichtiger als die Zahl, weil er zeigt, wie
          lange es noch reicht. */}
      <div className="h-1.5 rounded-full overflow-hidden mt-4" style={{ background: '#0d0f17' }}>
        <div className="h-full rounded-full transition-all"
             style={{ width: `${anteil * 100}%`, background: farbe }} />
      </div>

      {/* Wofür das Verbrauchte ging. Erst ab zwei Arten: Eine einzige wäre
          eine volle Leiste mit „100 %" und sagt nichts. */}
      {segmente.filter(x => x.wert > 0).length >= 2 && (
        <div className="mt-4">
          <SegmentLeiste segmente={segmente} kopf="USAGE BY KIND" />
        </div>
      )}

      {stand.aufgebraucht && (
        <div className="mt-4 rounded-lg px-3 py-2.5 text-xs leading-relaxed"
             style={{ background: '#ef444412', border: '1px solid #ef444433', color: '#ef4444' }}>
          Credit used up. New weekly plans and chat replies are only possible
          again after a top-up. Everything else (sessions, analysis, reflections)
          keeps working.
        </div>
      )}

      {offen && (
        <div className="mt-4 pt-4 border-t border-[#1e2228] space-y-1">
          {verlauf.map((z, i) => (
            <div key={i} className="flex items-center gap-3 text-[11px] font-mono">
              <span className="text-[var(--text-muted)] w-24 flex-shrink-0">
                {z.datum ? lokalerTag(z.datum) : '—'}
              </span>
              <span className="text-[var(--text-secondary)] flex-1">{ART[z.art] || z.art}</span>
              <span className="text-[var(--text-muted)] tabular-nums hidden sm:block">
                {z.token_ein.toLocaleString('en-GB')} in / {z.token_aus.toLocaleString('en-GB')} out
              </span>
              <span className="text-[#e8eaf0] tabular-nums w-16 text-right">
                {z.kosten_eur.toFixed(3)} €
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}


/** Zeitstempel des Servers (UTC, oft ohne Zonenangabe) als lokaler Tag.
 *  `slice(0, 10)` zeigte den UTC-Tag — kurz nach Mitternacht den Vortag. */
function lokalerTag(stempel) {
  const mitZone = /Z|[+-]\d\d:?\d\d$/.test(stempel) ? stempel : `${stempel}Z`
  const d = new Date(mitZone)
  return Number.isNaN(d.getTime()) ? stempel.slice(0, 10) : d.toLocaleDateString('de-DE')
}
