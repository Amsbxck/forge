import { useMemo, useState } from 'react'
import { ACCENT, DISCIPLINE_COLOR, DISCIPLINE_LABEL, phaseColor } from '../../utils/colors'
import { isoTag, parseTag } from '../../utils/dates'
import { SPORTEN, montagVon, stunden, wochenSummen } from '../../utils/einheiten'
import { phaseFamilie } from '../../utils/phasen'
import { blockName } from './SaisonStrahl'

/** Stunden je Woche, gestapelt nach Sportart, mit dem Phasenband darunter.
 *
 *  Ersetzt das Monats-Stufendiagramm der Verlauf-Seite. Das summierte nur
 *  innerhalb eines Monats auf und begann am Ersten wieder bei null — wie
 *  sich der Umfang über einen Aufbau entwickelt, ließ sich daraus nicht
 *  ablesen. Geplant wird in Wochen, also wird in Wochen gezeigt.
 *
 *  Das **Phasenband** kommt aus den Wochenplänen (`plan_phase` je
 *  `week_start`), nicht aus einer Rechnung: Es zeigt, was in der Woche
 *  tatsächlich geplant war, auch über einen Zielwechsel hinweg. Wochen ohne
 *  Plan bleiben leer. Die **Deload-Dreiecke** kommen aus `/metrics/saison`
 *  und gibt es deshalb nur für die laufende Saison — gespeichert wird der
 *  Deload am Plan nicht.
 */

const OPTIONEN = [12, 26, 52]
const HOEHE = 120

function phasenName(phase) {
  return phaseFamilie(phase) === 'off' ? 'OFF SEASON' : blockName(phase)
}

export default function WochenVolumen({ sessions, plaene, saison }) {
  const [anzahl, setAnzahl] = useState(26)
  const [hover, setHover] = useState(null)

  const { wochen, max } = useMemo(() => {
    const summen = wochenSummen(sessions)
    const phaseJeWoche = Object.fromEntries((plaene || []).map(p => [p.week_start, p.plan_phase]))
    const deload = new Set((saison?.deload || []).map(d => d.montag))
    const jetzt = parseTag(montagVon(isoTag(new Date())))
    const liste = []
    for (let i = anzahl - 1; i >= 0; i--) {
      const d = new Date(jetzt)
      d.setDate(jetzt.getDate() - i * 7)
      const montag = isoTag(d)
      liste.push({
        montag,
        summe: summen[montag],
        phase: phaseJeWoche[montag] || null,
        deload: deload.has(montag),
        jetzt: i === 0,
      })
    }
    return { wochen: liste, max: Math.max(1, ...liste.map(w => w.summe?.min || 0)) }
  }, [sessions, plaene, saison, anzahl])

  const fuge = anzahl > 26 ? 1 : 3
  // Phasenwechsel: dort steht der Name, so breit wie die Phase dauert.
  const laeufe = []
  wochen.forEach((w, i) => {
    const vorher = laeufe[laeufe.length - 1]
    if (vorher && vorher.phase === w.phase) vorher.bis = i
    else laeufe.push({ phase: w.phase, von: i, bis: i })
  })
  const breite = 100 / wochen.length
  const gezeigt = hover || wochen[wochen.length - 1]

  return (
    <div>
      <div className="flex items-center justify-between gap-3 mb-3">
        <span className="text-[9px] font-mono tracking-[0.2em] text-[var(--text-muted)]">WEEKLY VOLUME · HOURS</span>
        <div className="flex rounded-lg p-0.5" style={{ background: '#0d0f14', border: '1px solid #1e2228' }}>
          {OPTIONEN.map(n => (
            <button
              key={n}
              onClick={() => setAnzahl(n)}
              className="px-2.5 py-1 rounded-md text-[10px] font-mono tracking-widest transition-colors"
              style={{
                color: anzahl === n ? ACCENT : '#8a909e',
                background: anzahl === n ? `${ACCENT}1f` : 'transparent',
                boxShadow: anzahl === n ? `inset 0 0 0 1px ${ACCENT}44` : 'none',
              }}
            >
              {n}W
            </button>
          ))}
        </div>
      </div>

      {/* Säulen. Oben eine feine Linie auf Höhe der stärksten Woche, mit
          ihrer Stundenzahl — die eine Achse, die man braucht. */}
      <div className="relative" style={{ height: HOEHE }}>
        <div className="absolute inset-x-0 top-0 border-t border-dashed border-[#1e2228]" />
        <span className="absolute right-0 -top-3.5 text-[9px] font-mono tabular-nums text-[var(--text-muted)]">
          {stunden(max)}
        </span>
        <div className="absolute inset-0 flex items-end" style={{ gap: fuge }}>
          {wochen.map(w => {
            const hoehe = ((w.summe?.min || 0) / max) * 100
            const an = hover?.montag === w.montag
            return (
              <div
                key={w.montag}
                className="relative flex-1 h-full flex flex-col-reverse cursor-default"
                onMouseEnter={() => setHover(w)}
                onMouseLeave={() => setHover(null)}
              >
                <div
                  className="w-full flex flex-col-reverse rounded-t-[2px] overflow-hidden transition-[height] duration-700 ease-out"
                  style={{
                    height: `${hoehe}%`,
                    // Weiß statt ACCENT: Cyan um blaue Schwimmanteile las
                    // sich als Teil der Säule.
                    boxShadow: w.jetzt ? '0 0 0 1px #e8eaf0, 0 0 10px #ffffff33' : 'none',
                    opacity: hover && !an ? 0.55 : 1,
                  }}
                >
                  {SPORTEN.filter(s => w.summe?.jeSport[s]).map(s => (
                    <div
                      key={s}
                      style={{
                        height: `${(w.summe.jeSport[s] / w.summe.min) * 100}%`,
                        background: DISCIPLINE_COLOR[s] || DISCIPLINE_COLOR.other,
                        opacity: 0.85,
                      }}
                    />
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Phasenband: je Woche ein Streifen in der Farbe des Plans */}
      <div className="relative flex mt-1.5 h-1.5" style={{ gap: fuge }}>
        {wochen.map(w => (
          <div
            key={w.montag}
            className="flex-1 h-full rounded-[1px]"
            style={{ background: w.phase ? phaseColor(w.phase) : 'transparent', opacity: 0.75 }}
          />
        ))}
      </div>
      {/* Phasennamen am Wechsel, Deload-Dreiecke und Monate darunter */}
      <div className="relative h-3.5 mt-1">
        {laeufe.filter(l => l.phase).map(l => (
          <span
            key={`${l.phase}-${l.von}`}
            className="absolute text-[8px] font-mono tracking-wider truncate"
            style={{ left: `${l.von * breite}%`, width: `${(l.bis - l.von + 1) * breite}%`, color: phaseColor(l.phase) }}
          >
            {phasenName(l.phase)}
          </span>
        ))}
      </div>
      <div className="relative h-3">
        {wochen.map((w, i) => (
          <span key={w.montag}>
            {w.deload && (
              <span
                className="absolute -translate-x-1/2 top-0 block w-0 h-0"
                title="Deload"
                style={{
                  left: `${(i + 0.5) * breite}%`,
                  borderLeft: '3px solid transparent', borderRight: '3px solid transparent', borderBottom: '4px solid #a7aebd',
                }}
              />
            )}
            {parseTag(w.montag).getDate() <= 7 && (
              <span className="absolute top-0 text-[8px] font-mono text-[var(--text-muted)] whitespace-nowrap"
                    style={{ left: `${i * breite}%`, paddingTop: w.deload ? 4 : 0 }}>
                {parseTag(w.montag).toLocaleDateString('en-GB', { month: 'short' }).toUpperCase()}
              </span>
            )}
          </span>
        ))}
      </div>

      {/* Was unter dem Zeiger liegt — ohne Zeiger die laufende Woche */}
      <div className="mt-2 h-5 flex items-center gap-x-3 text-[10px] font-mono text-[var(--text-secondary)] overflow-hidden whitespace-nowrap">
        <span className="text-[#e8eaf0]">
          {gezeigt.jetzt && !hover ? 'THIS WEEK' : `WEEK OF ${parseTag(gezeigt.montag).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }).toUpperCase()}`}
        </span>
        <span>{stunden(gezeigt.summe?.min)}</span>
        <span>{Math.round(gezeigt.summe?.tss || 0)} TSS</span>
        {gezeigt.phase && <span style={{ color: phaseColor(gezeigt.phase) }}>{phasenName(gezeigt.phase)}</span>}
        {gezeigt.deload && <span className="text-[var(--text-muted)]">DELOAD</span>}
        <span className="hidden sm:flex gap-3 text-[var(--text-muted)]">
          {SPORTEN.filter(s => gezeigt.summe?.jeSport[s]).map(s => (
            <span key={s} style={{ color: DISCIPLINE_COLOR[s] }}>
              {(DISCIPLINE_LABEL[s] || s).toUpperCase()} {stunden(gezeigt.summe.jeSport[s])}
            </span>
          ))}
        </span>
      </div>
    </div>
  )
}
