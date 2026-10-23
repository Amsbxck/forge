import { useEffect, useState } from 'react'
import { HR_ZONE_COLOR, HR_ZONE_LABEL } from '../../utils/colors'

/** Die Pulszonen der Woche mit der 80/20-Marke.
 *
 *  Ersetzt im BREAKDOWN die reine Zonenleiste. Fünf Anteile allein sagen
 *  nicht, ob die Woche locker genug war; die übliche Faustregel für
 *  Ausdauer ist rund 80 % locker, 20 % fordernd. Locker heißt hier Z1 und
 *  Z2, fordernd Z3 bis Z5 — Z3 zählt mit, weil gerade das „mittelharte"
 *  Training die lockeren Einheiten verdrängt.
 *
 *  Bewusst ohne Urteil in Rot: Eine Rennwoche oder eine Testwoche darf
 *  härter sein, und die Zonen kommen aus dem Puls, nicht aus dem Plan.
 *  Die Anteile sind nach Dauer gewichtet (`/metrics/week`, `hr_zones_avg`).
 */

export const LOCKER_ZIEL = 80

/** Anteile locker (Z1–2) und fordernd (Z3–5) in Prozent, auf 100 gerechnet.
 *  `null`, wenn keine Zonen da sind. */
export function easyHard(zonen) {
  if (!zonen) return null
  const w = k => Math.max(0, Number(zonen[k]) || 0)
  const locker = w('z1') + w('z2')
  const hart = w('z3') + w('z4') + w('z5')
  const summe = locker + hart
  if (!summe) return null
  const easy = Math.round((locker / summe) * 100)
  return { easy, hard: 100 - easy }
}

export default function IntensitaetsLeiste({ zonen }) {
  const [da, setDa] = useState(false)
  useEffect(() => {
    const t = requestAnimationFrame(() => setDa(true))
    return () => cancelAnimationFrame(t)
  }, [])

  const anteile = easyHard(zonen)
  if (!anteile) return null
  const segmente = HR_ZONE_LABEL.map((name, i) => ({
    name, farbe: HR_ZONE_COLOR[i], wert: Math.max(0, Number(zonen[`z${i + 1}`]) || 0),
  }))
  const summe = segmente.reduce((a, s) => a + s.wert, 0)

  return (
    <div>
      <div className="flex items-baseline justify-between mb-2">
        <span className="text-[9px] font-mono tracking-[0.2em] text-[var(--text-muted)]">INTENSITY · 80/20</span>
        <span className="text-[9px] font-mono tracking-widest text-[var(--text-muted)]">TARGET {LOCKER_ZIEL} / {100 - LOCKER_ZIEL}</span>
      </div>

      <div className="relative pt-3">
        {/* Die Marke bei 80 %: Bis dorthin sollte die Leiste Z1–Z2 sein. */}
        <div className="absolute top-0 bottom-0 -translate-x-1/2 flex flex-col items-center pointer-events-none"
             style={{ left: `${LOCKER_ZIEL}%` }}>
          <span className="block w-0 h-0"
                style={{ borderLeft: '3px solid transparent', borderRight: '3px solid transparent', borderTop: '4px solid #e8eaf0' }} />
          <span className="w-px flex-1 mt-0.5" style={{ background: '#e8eaf0', opacity: 0.6 }} />
        </div>
        <div className="flex gap-[3px] h-2.5">
          {segmente.filter(s => s.wert > 0).map(s => (
            <div key={s.name} title={`${s.name}: ${Math.round((s.wert / summe) * 100)} %`}
                 className="h-full rounded-[3px] transition-[flex-grow] duration-700 ease-out"
                 style={{ flexGrow: da ? s.wert : 0.0001, flexBasis: 0, background: s.farbe, boxShadow: 'inset 0 0 0 1px #ffffff08' }} />
          ))}
        </div>
      </div>

      <div className="flex items-baseline justify-between mt-2 text-[10px] font-mono tracking-widest">
        <span className="text-[var(--text-muted)]">
          EASY <span className="text-[#e8eaf0] tabular-nums text-sm" style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>{anteile.easy} %</span>
          <span className="ml-1 text-[9px]">Z1–2</span>
        </span>
        <span className="text-[var(--text-muted)]">
          <span className="mr-1 text-[9px]">Z3–5</span>
          HARD <span className="text-[#e8eaf0] tabular-nums text-sm" style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>{anteile.hard} %</span>
        </span>
      </div>
    </div>
  )
}
