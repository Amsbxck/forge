import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  getCurrentPlan, generatePlan, getPlannedCurrent,
  getPlanByMonday, getPlannedByMonday,
  getWeekMetrics,
} from '../services/api'
import WeekCalendar from '../components/WeekCalendar'
import PlanExport from '../components/PlanExport'
import HealthStatus from '../components/HealthStatus'
import { montagMitVersatz } from '../utils/dates'
import { phaseColor } from '../utils/colors'

const CARD = 'bg-[#111318] border border-[#1e2228] rounded-xl'
const LABEL = 'text-xs font-mono tracking-widest text-[var(--text-secondary)]'

/** planned_sessions → Kalenderformat. Trägt die id, damit Drag & Drop speichern kann. */
function fromPlannedSessions(rows) {
  return rows.map(r => ({
    id: r.id,
    day: r.day_name,
    date: r.planned_date,
    session_type: r.discipline,
    training_type: r.training_type,
    intensity: r.intensity,
    duration_min: r.duration_min,
    notes: r.notes,
    details: r.details,
    status: r.status,
    replacement: r.replacement,
    replacement_min: r.replacement_min,
    moved_from_date: r.moved_from_date,
    targets: {
      tss: r.target_tss,
      watts_low: r.target_watts_low,
      watts_high: r.target_watts_high,
      pace_low_s_per_km: r.target_pace_low_s_per_km,
      pace_high_s_per_km: r.target_pace_high_s_per_km,
      hr_zone: r.target_hr_zone,
      distance_km: r.target_distance_km,
    },
  }))
}

/** Fallback auf den Claude-Rohoutput — für Pläne ohne Projektion. Ohne id, also nicht speicherbar. */
function fromPlanContent(days) {
  return (days || []).map(d => ({
    id: null,
    day: d.day,
    date: d.date,
    session_type: d.session_type,
    training_type: d.training_type,
    duration_min: d.duration_min,
    notes: d.notes,
    details: d.details,
    targets: d.targets,
  }))
}

export default function WeeklyPlan() {
  const [plan, setPlan] = useState(null)
  const [planned, setPlanned] = useState(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [requests, setRequests] = useState('')
  const [error, setError] = useState(null)
  // Versatz in Kalenderwochen: 0 = laufende, -1 = vorige, +1 = kommende.
  //
  // Vorher stand hier die Planwochennummer. Die entsteht aus `max(1, …)` und
  // ist vor dem Beginn des Aufbaus für jedes Datum 1 — "eine Woche vor"
  // führte dort auf Nummer 2, für die es nie einen Plan gibt, während die
  // kommende Woche unter derselben 1 lag wie die laufende.
  const [versatz, setVersatz] = useState(0)
  const [currentWeek, setCurrentWeek] = useState(null)
  // Zieldauer statt fester 33: Eine 14-Wochen-Vorbereitung ließ sich bis
  // Woche 33 durchblättern (alles leer), eine 40-Wochen-Saison brach bei 33 ab.
  const [totalWeeks, setTotalWeeks] = useState(null)
  const [notFound, setNotFound] = useState(false)

  const loadPlanned = useCallback(async (offset) => {
    try {
      const resp = offset === 0
        ? await getPlannedCurrent()
        : await getPlannedByMonday(montagMitVersatz(offset))
      setPlanned(resp.data?.length ? resp.data : null)
    } catch (e) {
      // 503 = Projektion noch nicht migriert. Kein Fehler für den Nutzer,
      // der Kalender fällt dann auf plan_content zurück.
      setPlanned(null)
    }
  }, [])

  const load = useCallback(async (offset = 0) => {
    setLoading(true)
    setError(null)
    setNotFound(false)
    try {
      const resp = offset === 0
        ? await getCurrentPlan()
        : await getPlanByMonday(montagMitVersatz(offset))
      setPlan(resp.data)
      // Die erste Antwort definiert, welche Woche "aktuell" ist.
      setCurrentWeek(prev => (prev == null && offset === 0 ? resp.data.week_number : prev))
      await loadPlanned(offset)
    } catch (e) {
      if (e.response?.status === 404) {
        setPlan(null)
        setPlanned(null)
        setNotFound(true)
      } else {
        setError('Failed to load plan')
      }
    } finally {
      setLoading(false)
    }
  }, [loadPlanned])

  const generate = async () => {
    setGenerating(true)
    setError(null)
    try {
      const resp = await generatePlan(requests)
      setPlan(resp.data)
      setWeek(null)
      await loadPlanned(null)
    } catch (e) {
      setError(e.response?.data?.detail || 'Generation failed')
    } finally {
      setGenerating(false)
    }
  }

  useEffect(() => { load(versatz) }, [versatz, load])

  const shownWeek = plan?.week_number ?? currentWeek
  // Gibt es für die betrachtete Woche keinen Plan, ist keine Wochennummer
  // bekannt — die des geladenen Plans wäre die einer anderen Woche. Dann
  // steht dort der Montag statt einer Nummer, die nicht stimmt.
  const wochenMarke = plan
    // Negative Nummern sind die Wochen vor dem Aufbaubeginn: 0 ist die Woche
    // unmittelbar davor, -7 die achte davor. Der Zusatz erklärt das, ohne
    // dass man die Rechnung kennen muss.
    ? (plan.week_number < 1 ? `WK ${plan.week_number} · VORLAUF` : `WK ${plan.week_number}`)
    : new Date(montagMitVersatz(versatz) + 'T00:00:00').toLocaleDateString('de-DE',
        { day: '2-digit', month: '2-digit' })
  // Am Versatz erkannt, nicht am Vergleich der Wochennummern: Vor dem
  // Beginn des Aufbaus tragen laufende und kommende Woche dieselbe Nummer,
  // und die Seite hielte die kommende für die laufende.
  const isCurrent = versatz === 0

  // Bevorzugt die normalisierten Einheiten — nur die tragen ids und Zielwerte.
  const calendarDays = useMemo(
    () => (planned ? fromPlannedSessions(planned) : fromPlanContent(plan?.plan_content?.days)),
    [planned, plan]
  )

  return (
    <div className="space-y-6 page-enter">

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-baseline gap-3">
          <h1
            className="text-3xl font-black tracking-tight text-[#e8eaf0]"
            style={{ fontFamily: 'Barlow Condensed, sans-serif' }}
          >
            WEEKLY PLAN
          </h1>

          {/* Wochennavigation — ein im Voraus erstellter Plan war sonst bis
              zum Wochenwechsel unsichtbar.

              Ohne Bedingung: Sie hing daran, dass eine Wochennummer bekannt
              ist, und die wird erst gesetzt, wenn ein Plan geladen werden
              konnte. Wer für die laufende Woche keinen Plan hat, bekam
              dadurch gar keine Pfeile — und damit keinen Weg zu der Woche,
              in der einer liegt. Gerade dann braucht man sie. */}
          <div className="flex items-center gap-1">
              {[
                { dir: -1, label: '‹', title: 'Woche zurück' },
                { dir: 1, label: '›', title: 'Woche vor' },
              ].map(({ dir, label, title }, i) => (
                <button
                  key={dir}
                  title={title}
                  // Nach vorn genau eine Woche: Weiter gibt es nichts zu
                  // sehen, weil Pläne immer nur für die kommende Woche
                  // entstehen. Nach hinten offen — dort liegt die Historie.
                  disabled={dir === 1 && versatz >= 1}
                  onClick={() => setVersatz(v => Math.min(1, v + dir))}
                  className={`px-2 py-0.5 rounded font-mono text-[var(--text-secondary)] transition-colors ${i === 1 ? 'order-3' : ''} ${dir === 1 && versatz >= 1 ? 'opacity-30 cursor-not-allowed' : 'hover:text-[#00d4ff]'}`}
                  style={{ border: '1px solid #1e2228' }}
                >
                  {label}
                </button>
              ))}
              <span className="text-lg font-mono order-2 px-1"
                    style={{ color: versatz === 0 ? 'var(--text-muted)' : '#00d4ff' }}>
                {wochenMarke}
                {versatz === 1 && <span className="text-[10px] ml-1">KOMMENDE</span>}
            {versatz < 0 && <span className="text-[10px] ml-1">VERGANGEN</span>}
            </span>
          </div>

          {!isCurrent && (
            <button
              onClick={() => setVersatz(0)}
              className="text-[10px] font-mono px-2 py-1 rounded tracking-wide"
              style={{ background: '#00d4ff15', border: '1px solid #00d4ff33', color: '#00d4ff' }}
            >
              {currentWeek != null ? `ZURÜCK ZU WK ${currentWeek}` : 'ZURÜCK ZU DIESER WOCHE'}
            </button>
          )}
        </div>

        <div className="flex gap-2 items-center flex-wrap">
          <input
            value={requests}
            onChange={e => setRequests(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !generating && generate()}
            placeholder="Special requests (optional)"
            className="rounded-lg px-3 py-2 text-sm font-mono text-[#e8eaf0] placeholder-[var(--text-muted)] outline-none transition-colors w-64"
            style={{
              background: '#111318',
              border: '1px solid #1e2228',
            }}
            onFocus={e => { e.target.style.borderColor = '#00d4ff44' }}
            onBlur={e => { e.target.style.borderColor = '#1e2228' }}
          />
          <button
            onClick={generate}
            disabled={generating || !isCurrent}
            title={isCurrent
              ? 'Plan für die aktuelle Woche generieren'
              : `Generieren erstellt immer für die laufende Woche (WK ${currentWeek})`}
            className="relative px-4 py-2 rounded-lg text-sm font-mono font-bold tracking-wide transition-all disabled:opacity-40 disabled:cursor-not-allowed"
            style={{
              background: generating ? '#00d4ff15' : '#00d4ff20',
              border: '1px solid #00d4ff44',
              color: '#00d4ff',
            }}
            onMouseEnter={e => { if (!generating) e.currentTarget.style.background = '#00d4ff30' }}
            onMouseLeave={e => { e.currentTarget.style.background = generating ? '#00d4ff15' : '#00d4ff20' }}
          >
            {generating ? (
              <span className="flex items-center gap-2">
                <span className="inline-flex gap-0.5">
                  {[0, 1, 2].map(i => (
                    <span
                      key={i}
                      className="w-1 h-1 rounded-full bg-[#00d4ff]"
                      style={{ animation: `pulse 1.2s ease-in-out ${i * 0.2}s infinite` }}
                    />
                  ))}
                </span>
                GENERATING
              </span>
            ) : 'GENERATE PLAN'}
          </button>
          {plan && <PlanExport plan={plan} />}
        </div>
      </div>

      {/* Gesundheit steht über dem Plan: wer krank ist, muss zuerst wissen,
          ob der Plan darunter überhaupt noch gilt. */}
      <HealthStatus variant="bar" onChanged={() => {
        load(versatz)
        // Die Neuplanung läuft im Hintergrund und braucht etwa eine halbe
        // Minute — deshalb ein zweiter Blick, sonst steht hier noch der
        // alte Plan und man hält die Anpassung für ausgefallen.
        setTimeout(() => load(versatz), 30000)
      }} />

      {/* Error */}
      {error && (
        <div className="rounded-xl p-4 font-mono text-sm" style={{ background: '#ef444415', border: '1px solid #ef444430', color: '#ef4444' }}>
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="text-[var(--text-secondary)] font-mono text-sm py-8 text-center tracking-widest">
          LOADING...
        </div>
      )}

      {/* Empty state */}
      {!loading && !plan && !error && (
        <div className={`${CARD} p-10 text-center`}>
          <div
            className="text-2xl font-black text-[var(--text-muted)] mb-2"
            style={{ fontFamily: 'Barlow Condensed, sans-serif' }}
          >
            {notFound && !isCurrent ? 'KEIN PLAN FÜR DIESE WOCHE' : 'NO PLAN YET'}
          </div>
          <p className="text-sm font-mono text-[var(--text-muted)]">
            {notFound && !isCurrent
              ? 'Für diese Woche wurde noch kein Plan erstellt.'
              : 'Click Generate Plan to create your weekly training schedule.'}
          </p>
        </div>
      )}

      {/* Plan */}
      {plan && (
        <div className="space-y-5">

          {/* Coaching brief card */}
          <div
            className="rounded-xl p-5 relative overflow-hidden"
            style={{ background: '#111318', border: '1px solid #1e2228', borderLeft: '3px solid #00d4ff' }}
          >
            {/* Single diagonal light beam */}
            <div
              className="absolute pointer-events-none"
              style={{
                top: '-60px', left: '-60px',
                width: '220px', height: '220px',
                background: 'linear-gradient(135deg, #00d4ff0e 0%, transparent 55%)',
                transform: 'rotate(-10deg)',
              }}
            />
            <div className="relative z-10">
              <div className="flex flex-wrap gap-4 mb-3">
                <div>
                  <div className={`${LABEL} mb-0.5`}>PHASE</div>
                  <div
                    className="text-sm font-bold"
                    style={{
                      fontFamily: 'Barlow Condensed, sans-serif',
                      color: phaseColor(plan.plan_phase),
                    }}
                  >
                    {plan.plan_phase?.toUpperCase()}
                  </div>
                </div>
                <div>
                  <div className={`${LABEL} mb-0.5`}>PERIOD</div>
                  <div className="text-sm font-mono text-[var(--text-secondary)]">
                    {plan.week_start} – {plan.week_end}
                  </div>
                </div>
              </div>

              {plan.plan_content?.coaching_comment && (
                <p className="text-sm text-[#e8eaf0] leading-relaxed">
                  {plan.plan_content.coaching_comment}
                </p>
              )}

              {plan.adjustments_applied?.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {plan.adjustments_applied.map((adj, i) => (
                    <span
                      key={i}
                      className="text-xs font-mono px-2 py-0.5 rounded-full"
                      style={{ background: '#00d4ff15', color: '#00d4ff', border: '1px solid #00d4ff25' }}
                    >
                      {adj}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Calendar */}
          <WeekCalendar days={calendarDays} onPersisted={loadPlanned} />
        </div>
      )}

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 0.3; transform: scale(0.8); }
          50% { opacity: 1; transform: scale(1); }
        }
      `}</style>
    </div>
  )
}
