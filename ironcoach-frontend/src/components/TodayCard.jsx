import { useEffect, useState } from 'react'
import { getPlannedByMonday, getPlannedCurrent } from '../services/api'
import { disciplineColor, disciplineLabel } from '../utils/colors'
import { isoTag, montagMitVersatz } from '../utils/dates'

const LABEL = 'text-[10px] font-mono tracking-widest text-[var(--text-secondary)]'
const DISPLAY = { fontFamily: 'Barlow Condensed, sans-serif' }

const INTENSITY_LABEL = {
  base: 'Base / Endurance',
  sweet_spot: 'Sweet Spot',
  threshold: 'Threshold',
  vo2max: 'VO₂max',
}

function paceText(low, high) {
  const fmt = s => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`
  if (low && high && low !== high) return `${fmt(high)}–${fmt(low)} /km`
  return `${fmt(low || high)} /km`
}

/** Zielwerte in einer Zeile — Watt, Pace, Zone, Distanz, je nachdem was
 *  geplant ist. Ohne sie wäre die Kachel nur ein Terminhinweis. */
function targets(session) {
  const out = []
  if (session.target_watts_low || session.target_watts_high) {
    const { target_watts_low: lo, target_watts_high: hi } = session
    out.push(lo && hi && lo !== hi ? `${lo}–${hi} W` : `${lo || hi} W`)
  }
  if (session.target_pace_low_s_per_km || session.target_pace_high_s_per_km) {
    out.push(paceText(session.target_pace_low_s_per_km, session.target_pace_high_s_per_km))
  }
  if (session.target_distance_km) out.push(`${session.target_distance_km} km`)
  if (session.target_hr_zone) out.push(session.target_hr_zone)
  if (session.target_tss) out.push(`${session.target_tss} TSS`)
  return out
}

/** Die heutige Einheit.
 *
 *  Das Dashboard beantwortete bisher alles außer der Frage, mit der man es
 *  morgens öffnet: was steht heute an? Dafür musste man auf die Planseite
 *  wechseln.
 */
export default function TodayCard({ onOpenPlan }) {
  const [rows, setRows] = useState(null)

  useEffect(() => {
    // Diese **und** die kommende Woche laden. "Morgen" ist am Sonntag der
    // Montag der nächsten Woche und lag deshalb gar nicht in den Daten — die
    // Zeile blieb an genau dem Tag leer, an dem man am ehesten vorausschaut.
    Promise.all([
      getPlannedCurrent().then(r => r.data || []).catch(() => []),
      getPlannedByMonday(montagMitVersatz(1)).then(r => r.data || []).catch(() => []),
    ])
      // 404/503 heißt: kein Plan für die Woche. Kein Fehler, nur nichts zu zeigen.
      .then(([diese, naechste]) => setRows([...diese, ...naechste]))
      .catch(() => setRows([]))
  }, [])

  if (rows === null) return null

  // Lokales Datum, nicht UTC: `toISOString()` liefert den UTC-Tag, und
  // östlich von Greenwich ist der zwischen Mitternacht und zwei Uhr noch der
  // vorige. Die Kachel zeigte dann nachts die Einheit von gestern als "heute".
  const heute = isoTag(new Date())
  const morgenDatum = new Date()
  morgenDatum.setDate(morgenDatum.getDate() + 1)
  const morgen = isoTag(morgenDatum)

  const heutige = rows.filter(r => r.planned_date === heute && r.discipline !== 'rest')
  const morgige = rows.filter(r => r.planned_date === morgen && r.discipline !== 'rest')
  const istRuhetag = rows.some(r => r.planned_date === heute) && heutige.length === 0
  // Ein Ruhetag morgen ist eine Auskunft, kein Nichts: Er unterscheidet sich
  // davon, dass für morgen noch kein Plan vorliegt.
  const morgenRuhetag = rows.some(r => r.planned_date === morgen) && morgige.length === 0

  const wochentag = new Date().toLocaleDateString('de-DE', { weekday: 'long' })

  return (
    <div className="rounded-xl p-5 relative overflow-hidden"
         style={{
           background: '#111318',
           // Hervorgehoben wie Zustand und HRV: dies ist der Tag, um den es
           // gerade geht, und in einer Reihe gleich aussehender Kacheln
           // verschwindet er sonst.
           border: `1px solid ${heutige.length ? '#00d4ff3a' : '#1e2228'}`,
           boxShadow: heutige.length ? '0 0 24px -10px #00d4ff' : 'none',
         }}>
      <div className="absolute inset-0 pointer-events-none" style={{
        background: 'radial-gradient(ellipse 55% 90% at 88% 12%, #00d4ff14 0%, transparent 70%)',
      }} />

      <div className="relative z-10">
        <div className="flex items-baseline justify-between gap-3 mb-3">
          <span className={LABEL}>TODAY · {wochentag.toUpperCase()}</span>
          <button
            onClick={onOpenPlan}
            className="text-[10px] font-mono text-[var(--text-muted)] hover:text-[#00d4ff] transition-colors"
          >
            WOCHENPLAN ▸
          </button>
        </div>

        {heutige.length === 0 ? (
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div>
              <div className="text-3xl font-black leading-none text-[var(--text-secondary)]" style={DISPLAY}>
                {istRuhetag ? 'RUHETAG' : 'NICHTS GEPLANT'}
              </div>
              <div className="text-xs font-mono text-[var(--text-muted)] mt-2">
                {istRuhetag
                  ? 'Erholung ist Teil des Plans — kein Training heute.'
                  : 'Für diese Woche liegt kein Plan vor.'}
              </div>
            </div>
            {!istRuhetag && (
              <button
                onClick={onOpenPlan}
                className="px-4 py-2 rounded-lg text-[11px] font-mono font-bold tracking-wide flex-shrink-0"
                style={{ background: '#00d4ff20', border: '1px solid #00d4ff44', color: '#00d4ff' }}
              >
                PLAN ERSTELLEN
              </button>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            {heutige.map(s => {
              const farbe = disciplineColor(s.discipline)
              const ziele = targets(s)
              return (
                <div key={s.id} className="flex items-start gap-4 flex-wrap">
                  <div className="flex items-baseline gap-3 min-w-0">
                    <span className="text-2xl font-black tracking-tight" style={{ ...DISPLAY, color: farbe }}>
                      {disciplineLabel(s.discipline, s.sport_type).toUpperCase()}
                    </span>
                    {s.duration_min && (
                      <span className="text-lg font-mono tabular-nums text-[#e8eaf0]">
                        {s.duration_min} min
                      </span>
                    )}
                    {s.intensity && (
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded"
                            style={{ background: `${farbe}14`, border: `1px solid ${farbe}33`, color: farbe }}>
                        {INTENSITY_LABEL[s.intensity] || s.intensity}
                      </span>
                    )}
                  </div>

                  {ziele.length > 0 && (
                    <div className="flex gap-3 flex-wrap items-baseline">
                      {ziele.map((z, i) => (
                        <span key={i} className="text-sm font-mono tabular-nums text-[#e8eaf0]">{z}</span>
                      ))}
                    </div>
                  )}

                  {s.notes && (
                    <div className="text-xs text-[var(--text-secondary)] leading-relaxed w-full">{s.notes}</div>
                  )}
                </div>
              )
            })}
          </div>
        )}

        {/* Morgen als Zeile: es geht um die Vorbereitung, nicht um Details.
            Die Intensität steht dabei — sie ist der Grund, warum man
            vorausschaut. Vor einer VO₂max-Einheit legt man sich früher hin. */}
        {(morgige.length > 0 || morgenRuhetag) && (
          <div className="mt-4 pt-3 border-t border-[#1e2228] flex items-center gap-x-3 gap-y-1.5 flex-wrap">
            <span className="text-[10px] font-mono tracking-widest text-[var(--text-muted)]">MORGEN</span>
            {morgenRuhetag ? (
              <span className="text-xs font-mono text-[var(--text-secondary)]">Ruhetag</span>
            ) : morgige.map(s => {
              const farbe = disciplineColor(s.discipline)
              return (
                <span key={s.id} className="flex items-baseline gap-1.5">
                  <span className="text-xs font-mono" style={{ color: farbe }}>
                    {disciplineLabel(s.discipline, s.sport_type)}
                    {s.duration_min ? ` ${s.duration_min}min` : ''}
                  </span>
                  {s.intensity && (
                    <span className="text-[9px] font-mono px-1 py-0.5 rounded"
                          style={{ background: `${farbe}14`, border: `1px solid ${farbe}33`, color: farbe }}>
                      {INTENSITY_LABEL[s.intensity] || s.intensity}
                    </span>
                  )}
                </span>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
