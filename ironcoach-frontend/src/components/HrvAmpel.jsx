import { STATUS_COLOR } from '../utils/colors'
import SpannenSkala, { hrvZonen } from './leisten/SpannenSkala'

/** Die HRV als Ampel neben der Doppeltag-Ziehung.
 *
 *  Vorher stand dort „HRV normal" als erster Teil des Grundes — richtig, aber
 *  man musste lesen, um es zu sehen. Jetzt der Schnitt der letzten sieben
 *  Tage in der Ampelfarbe. Mehr braucht es nicht: Ein Gehäuse mit drei Lampen
 *  wirkte zu verspielt, ein senkrechter Farbstrich davor doppelte nur, was
 *  Zahl und Skala schon zeigen.
 *
 *  **Die Farbe ist das Urteil der Urne, nicht des Schnitts.** Sie kommt aus
 *  `doppel_urne._hrv_status` (jüngste Messung der letzten drei Tage) — genau
 *  dem Wert, mit dem die Urne gewichtet hat. Der Schnitt ist die Zahl dazu.
 *  Eine eigene Ampel für den Schnitt wäre eine zweite, die der ersten
 *  widersprechen kann.
 *
 *  Die Skala darunter zeigt, wo der Schnitt in der eigenen Spanne liegt
 *  (rot unter, gelb dazwischen, grün im Band). Ohne Spanne fällt sie weg.
 *  Sie ist ein gemeinsamer Baustein (`leisten/SpannenSkala`), damit die HRV
 *  im Dashboard und im Chat genauso aussieht.
 */

export const HRV_URTEIL = {
  green: 'NORMAL',
  yellow: 'SLIGHTLY LOW',
  red: 'BELOW RANGE',
}

export default function HrvAmpel({ hrv }) {
  if (!hrv) return null
  const farbe = STATUS_COLOR[hrv.status]
  const aktiv = farbe || 'var(--text-muted)'

  return (
    <div
      className="rounded-lg px-3 py-2.5"
      style={{
        background: farbe ? `linear-gradient(90deg, ${farbe}14, transparent 70%)` : '#0d0f17',
        border: `1px solid ${farbe ? `${farbe}33` : '#1e2228'}`,
      }}
    >
      <div className="min-w-0">
        <div className="flex items-baseline gap-1.5">
          <span
            className="text-[26px] leading-none font-bold tabular-nums"
            style={{
              fontFamily: 'Barlow Condensed, sans-serif',
              color: aktiv,
              textShadow: farbe ? `0 0 14px ${farbe}55` : 'none',
            }}
          >
            {Math.round(hrv.schnitt_7)}
          </span>
          <span className="text-[10px] font-mono text-[var(--text-muted)]">ms</span>
          <span
            className="ml-auto text-[9px] font-mono tracking-widest"
            style={{ color: aktiv }}
          >
            {HRV_URTEIL[hrv.status] || 'NOT CURRENT'}
          </span>
        </div>
        <div className="mt-0.5 text-[9px] font-mono tracking-wider text-[var(--text-muted)]">
          HRV Ø 7 DAYS · {hrv.messungen} {hrv.messungen === 1 ? 'MEASUREMENT' : 'MEASUREMENTS'}
          {hrv.letzter_wert != null && <> · LAST {Math.round(hrv.letzter_wert)}</>}
        </div>
        <SpannenSkala
          zonen={hrvZonen(hrv.spanne)}
          marken={[{
            wert: hrv.schnitt_7,
            titel: `Ø ${hrv.schnitt_7} ms · range ${hrv.spanne?.gruen_ab}–${hrv.spanne?.gruen_bis}`,
          }]}
        />
      </div>
    </div>
  )
}
