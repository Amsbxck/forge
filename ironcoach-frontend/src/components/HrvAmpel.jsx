import { STATUS_COLOR } from '../utils/colors'

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
 */

const URTEIL = {
  green: 'NORMAL',
  yellow: 'LEICHT DARUNTER',
  red: 'UNTER DER SPANNE',
}

function Skala({ spanne, wert }) {
  const { rot_unter: rot, gruen_ab: ab, gruen_bis: bis } = spanne || {}
  if (!rot || !ab || !bis || bis <= rot) return null
  // Ein Viertel der Spanne Luft auf beiden Seiten, damit ein Wert knapp
  // außerhalb nicht am Rand klebt.
  const luft = (bis - rot) * 0.25
  const min = rot - luft
  const max = bis + luft
  const pos = v => `${Math.min(100, Math.max(0, ((v - min) / (max - min)) * 100))}%`
  const zonen = [
    [min, rot, STATUS_COLOR.red],
    [rot, ab, STATUS_COLOR.yellow],
    [ab, bis, STATUS_COLOR.green],
    [bis, max, `${STATUS_COLOR.green}55`],
  ]

  return (
    <div className="relative mt-2 h-1">
      {zonen.map(([von, zu, farbe]) => (
        <div
          key={von}
          className="absolute inset-y-0"
          style={{ left: pos(von), width: `calc(${pos(zu)} - ${pos(von)})`, background: farbe, opacity: 0.35 }}
        />
      ))}
      <div
        className="absolute -top-[3px] w-[3px] h-[10px] rounded-full -translate-x-1/2 transition-all duration-700"
        style={{ left: pos(wert), background: '#e8eaf0', boxShadow: '0 0 6px #e8eaf0aa' }}
        title={`Ø ${wert} ms · Spanne ${ab}–${bis}`}
      />
    </div>
  )
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
            {URTEIL[hrv.status] || 'NICHT AKTUELL'}
          </span>
        </div>
        <div className="mt-0.5 text-[9px] font-mono tracking-wider text-[var(--text-muted)]">
          HRV Ø 7 TAGE · {hrv.messungen} {hrv.messungen === 1 ? 'MESSUNG' : 'MESSUNGEN'}
          {hrv.letzter_wert != null && <> · ZULETZT {Math.round(hrv.letzter_wert)}</>}
        </div>
        <Skala spanne={hrv.spanne} wert={hrv.schnitt_7} />
      </div>
    </div>
  )
}
