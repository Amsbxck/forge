import { useEffect, useState } from 'react'
import { getPlannedByMonday } from '../services/api'
import { disciplineColor, disciplineLabel } from '../utils/colors'
import { isoTag, montagMitVersatz } from '../utils/dates'

// Kopf und Unterzeilen wie THIS WEEK und BREAKDOWN, damit die Kachel
// zwischen den beiden nicht mehr aus der Reihe fällt.
const LABEL = 'text-xs font-mono tracking-[0.25em] text-[var(--text-secondary)]'
const KOPF = 'text-[9px] font-mono tracking-[0.2em] text-[var(--text-muted)]'
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
  // Ob für diese Woche überhaupt ein Plan existiert. Ohne die Unterscheidung
  // stand „Für diese Woche liegt kein Plan vor" auch dann da, wenn nur der
  // heutige Tag leer war — mit einem Knopf, der den Plan neu erstellt hätte.
  const [wochePlan, setWochePlan] = useState(false)

  useEffect(() => {
    // Diese **und** die kommende Woche laden. "Morgen" ist am Sonntag der
    // Montag der nächsten Woche und lag deshalb gar nicht in den Daten — die
    // Zeile blieb an genau dem Tag leer, an dem man am ehesten vorausschaut.
    Promise.all([
      getPlannedByMonday(montagMitVersatz(0)).then(r => r.data || []).catch(() => []),
      getPlannedByMonday(montagMitVersatz(1)).then(r => r.data || []).catch(() => []),
    ])
      // 404/503 heißt: kein Plan für die Woche. Kein Fehler, nur nichts zu zeigen.
      .then(([diese, naechste]) => {
        setWochePlan(diese.length > 0)
        setRows([...diese, ...naechste])
      })
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

  const datumText = new Date().toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })
    .replace(',', '').toUpperCase()
  // Getönt in der Farbe der heutigen Sportart, wie THIS WEEK mit seinen
  // Sportfarben. Vorher ein Cyan-Schein — Cyan liest sich neben den
  // Sportfarben aber als Schwimmen, auch an einem Lauftag.
  const farbeHeute = heutige.length ? disciplineColor(heutige[0].discipline) : null

  return (
    <div className="rounded-xl p-5 sm:p-6 relative overflow-hidden"
         style={{
           // Hervorgehoben wie Zustand und HRV: dies ist der Tag, um den es
           // gerade geht, und in einer Reihe gleich aussehender Kacheln
           // verschwindet er sonst.
           background: farbeHeute
             ? `linear-gradient(115deg, ${farbeHeute}17 0%, ${farbeHeute}08 45%, transparent 75%), #111318`
             : '#111318',
           border: `1px solid ${farbeHeute ? `${farbeHeute}2a` : '#1e2228'}`,
         }}>
      <div>
        <div className="flex items-baseline justify-between gap-3 mb-4">
          <span className={LABEL}>TODAY</span>
          <span className="flex items-baseline gap-4">
            <span className="text-[10px] font-mono tracking-widest text-[var(--text-muted)]">{datumText}</span>
            <button
              onClick={onOpenPlan}
              className="text-[10px] font-mono tracking-widest text-[var(--text-muted)] hover:text-[#e8eaf0] transition-colors"
            >
              WEEK PLAN ▸
            </button>
          </span>
        </div>

        {heutige.length === 0 ? (
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div>
              <div className="text-3xl font-black leading-none text-[var(--text-secondary)]" style={DISPLAY}>
                {istRuhetag ? 'REST DAY' : 'NOTHING PLANNED'}
              </div>
              <div className="text-xs font-mono text-[var(--text-muted)] mt-2">
                {istRuhetag
                  ? 'Recovery is part of the plan — no training today.'
                  : wochePlan
                    ? 'The week plan has nothing for today.'
                    : 'There is no plan for this week yet.'}
              </div>
            </div>
            {!istRuhetag && !wochePlan && (
              <button
                onClick={onOpenPlan}
                className="px-4 py-2 rounded-lg text-[11px] font-mono font-bold tracking-wide flex-shrink-0"
                style={{ background: '#00d4ff20', border: '1px solid #00d4ff44', color: '#00d4ff' }}
              >
                CREATE PLAN
              </button>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            {heutige.map(s => {
              const farbe = disciplineColor(s.discipline)
              const ziele = targets(s)
              return (
                // Auf einer Grundlinie: Seit die Dauer groß in Barlow steht,
                // hingen Zone und TSS bei `items-start` oben neben der Zahl
                // statt auf ihrer Zeile.
                <div key={s.id} className="flex items-baseline gap-x-4 gap-y-2 flex-wrap">
                  <div className="flex items-baseline gap-3 min-w-0">
                    <span className="text-2xl font-black tracking-tight" style={{ ...DISPLAY, color: farbe }}>
                      {disciplineLabel(s.discipline).toUpperCase()}
                    </span>
                    {s.duration_min && (
                      <span className="flex items-baseline gap-1">
                        <span className="text-2xl font-black leading-none tabular-nums text-[#f2f4f8]" style={DISPLAY}>
                          {s.duration_min}
                        </span>
                        <span className="text-xs font-mono text-[var(--text-muted)]">min</span>
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
          <div className="mt-4 pt-3 border-t border-[#ffffff0f] flex items-center gap-x-3 gap-y-1.5 flex-wrap">
            <span className={KOPF}>TOMORROW</span>
            {morgenRuhetag ? (
              <span className="text-xs font-mono text-[var(--text-secondary)]">Rest day</span>
            ) : morgige.map(s => {
              const farbe = disciplineColor(s.discipline)
              return (
                <span key={s.id} className="flex items-baseline gap-1.5">
                  <span className="text-xs font-mono" style={{ color: farbe }}>
                    {disciplineLabel(s.discipline)}
                    {s.duration_min ? ` ${s.duration_min} min` : ''}
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
