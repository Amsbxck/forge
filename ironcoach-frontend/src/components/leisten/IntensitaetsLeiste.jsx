import { useEffect, useState } from 'react'
import { HR_ZONE_COLOR, HR_ZONE_LABEL } from '../../utils/colors'

/** Die Pulszonen der Woche: wie viel der Trainingszeit in welcher Zone lag.
 *
 *  Unter jedem Stück steht seine Zone mit dem Anteil, Zonen ohne Zeit fehlen
 *  ganz. Nach Dauer gewichtet (`/metrics/week`, `hr_zones_avg`).
 *
 *  Vorher stand hier eine 80/20-Leiste: eine Marke bei 80 %, „TARGET 80 / 20"
 *  und EASY/HARD darunter. Direkt unter AVG HR las Amir die Marke als seinen
 *  Durchschnittspuls (141 bpm ist bei ihm Z1, die Marke stand im Z2-Stück).
 *  Auch beschriftet blieb sie eine zweite Aussage neben den Zonen. Amir hat
 *  sie gestrichen: nur noch die Anteile, ohne Ziel und ohne Erklärsatz.
 */

// Damit die Beschriftung eines kleinen Anteils („Z4 3 %") nicht in die
// nächste läuft. Verzerrt nur sehr kleine Stücke ein wenig.
const MIN_BREITE = '2.75rem'

export default function IntensitaetsLeiste({ zonen }) {
  const [da, setDa] = useState(false)
  useEffect(() => {
    const t = requestAnimationFrame(() => setDa(true))
    return () => cancelAnimationFrame(t)
  }, [])

  if (!zonen) return null
  const segmente = HR_ZONE_LABEL
    .map((name, i) => ({ name, farbe: HR_ZONE_COLOR[i], wert: Math.max(0, Number(zonen[`z${i + 1}`]) || 0) }))
    .filter(s => s.wert > 0)
  const summe = segmente.reduce((a, s) => a + s.wert, 0)
  if (!summe) return null

  return (
    <div>
      <div className="text-[9px] font-mono tracking-[0.2em] text-[var(--text-muted)] mb-2">
        TIME IN ZONES · THIS WEEK
      </div>
      <div className="flex gap-[3px]">
        {segmente.map(s => {
          const anteil = Math.round((s.wert / summe) * 100)
          return (
            <div key={s.name} className="transition-[flex-grow] duration-700 ease-out"
                 style={{ flexGrow: da ? s.wert : 0.0001, flexBasis: 0, minWidth: MIN_BREITE }}>
              <div className="h-2.5 rounded-[3px]"
                   style={{ background: s.farbe, boxShadow: 'inset 0 0 0 1px #ffffff08' }} />
              <div className="mt-1.5 text-[9px] font-mono tracking-widest whitespace-nowrap" style={{ color: s.farbe }}>
                {s.name}{' '}
                <span className="text-[#e8eaf0] tabular-nums text-sm" style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>
                  {anteil} %
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
