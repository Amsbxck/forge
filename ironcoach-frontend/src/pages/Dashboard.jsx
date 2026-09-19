import { useEffect, useState } from 'react'
import { getWeekMetrics, getLatestHrv, getHrv, getSessions, getProfile, getIntakeStatus, getMe } from '../services/api'
import HRVInput from '../components/HRVInput'
import HealthStatus from '../components/HealthStatus'
import HRVHistoryChart from '../components/HRVHistoryChart'
import PerformanceChart from '../components/PerformanceChart'
import HRZoneChart from '../components/HRZoneChart'
import Onboarding from '../components/Onboarding'
import IntakeDialog from '../components/IntakeDialog'
import EmailBestaetigung from '../components/EmailBestaetigung'
import Glossary from '../components/Glossary'
import TodayCard from '../components/TodayCard'
import SportIcon from '../components/SportIcon'
import { daysUntil, kalenderwoche } from '../utils/dates'
import SessionDetail from '../components/SessionDetail'
import ReflectionEditor from '../components/ReflectionEditor'
import { calculatePMC, formColor, formLabel } from '../components/PerformanceChart'
import { useNavigate } from 'react-router-dom'

import {
  DISCIPLINE_COLOR, DISCIPLINE_LABEL, HR_ZONE_COLOR, HR_ZONE_LABEL,
  STATUS_COLOR as HRV_COLOR, disciplineColor, disciplineLabel, phaseColor,
} from '../utils/colors'

const HRV_TEXT = {
  green: 'Normal session as planned',
  yellow: 'Possible — reduce intensity',
  red: 'Reduce intensity or rest',
}

// ─── Glossary ─────────────────────────────────────────────────────────────────

// ─── Main Dashboard ───────────────────────────────────────────────────────────

export default function Dashboard() {
  const navigate = useNavigate()
  // Angeklickte Einheit — öffnet die Detailansicht mit dem Reflexionsfeld.
  const [offeneEinheit, setOffeneEinheit] = useState(null)
  // Angeklickte Sportart filtert die Einheitenliste darunter.
  const [gewaehlteDisziplin, setGewaehlteDisziplin] = useState(null)
  const [metrics, setMetrics] = useState(null)
  const [hrv, setHrv] = useState(null)
  const [hrvHistory, setHrvHistory] = useState([])
  const [sessions, setSessions] = useState([])
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  // Willkommensfenster für neue Konten. `null` heißt: noch nicht geprüft —
  // ohne diesen dritten Zustand blitzte das Fenster bei jedem Laden kurz auf.
  const [intakeFaellig, setIntakeFaellig] = useState(null)
  // Konto nur für den Bestätigungshinweis. Getrennt vom Profil, weil die
  // Bestätigung am Konto hängt und nicht am Athletenprofil.
  const [konto, setKonto] = useState(null)

  const load = async () => {
    setLoading(true)
    try {
      const [m, h, hh, s, p] = await Promise.all([
        getWeekMetrics(),
        getLatestHrv().catch(() => ({ data: null })),
        getHrv(90).catch(() => ({ data: [] })),
        getSessions().catch(() => ({ data: [] })),
        getProfile().catch(() => ({ data: null })),
      ])
      // Bewusst nach den übrigen Daten und mit eigenem Fehlerfang: Ein
      // Ausfall dieser Abfrage darf das Dashboard nicht leer lassen.
      getIntakeStatus()
        .then(({ data }) => setIntakeFaellig(!!data?.faellig))
        .catch(() => setIntakeFaellig(false))
      getMe().then(({ data }) => setKonto(data)).catch(() => setKonto(null))
      setMetrics(m.data)
      setHrv(h.data)
      setHrvHistory(Array.isArray(hh.data) ? hh.data : [])
      setSessions(Array.isArray(s.data) ? s.data : [])
      setProfile(p.data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  if (loading) return (
    <div className="flex items-center justify-center py-20 text-[var(--text-secondary)]">
      <div className="text-sm font-mono tracking-widest">LOADING...</div>
    </div>
  )

  const status = hrv?.hrv_status || 'green'
  const statusColor = HRV_COLOR[status]

  // Form (TSB) aus derselben Funktion wie das Diagramm weiter unten — eine
  // zweite Rechnung würde früher oder später eine andere Zahl zeigen.
  // Der Durchschnittspuls gehört zur Wochenbilanz, nicht zur Bereitschaft:
  // er beschreibt, wie hart trainiert wurde, nicht wie erholt man ist.
  const avgHr = metrics?.avg_hr
  const hrZoneIndex = !avgHr || !profile ? null
    : avgHr <= profile.z1_hr_max ? 0
    : avgHr <= profile.z2_hr_max ? 1
    : avgHr <= profile.z3_hr_max ? 2
    : avgHr <= profile.z4_hr_max ? 3
    : 4
  const hrColor = hrZoneIndex == null ? '#e8eaf0' : HR_ZONE_COLOR[hrZoneIndex]

  const pmc = calculatePMC(sessions)
  const form = pmc.length ? pmc[pmc.length - 1].tsb : null
  const formFarbe = formColor(form)
  const formText = formLabel

  const fmtTime = (min) => { const h = Math.floor(min/60), m = min%60; return h > 0 ? `${h}h${m>0?` ${m}m`:''}` : `${m}m` }

  // Reihenfolge der geplanten Disziplinen; alles andere hängt sich hinten an.
  // Eine feste Liste hätte jede fremde Sportart verschluckt — eine
  // StairMaster-Einheit stand in History und Zonen, fehlte hier aber
  // vollständig, obwohl sie stattgefunden hat.
  const DISC_ORDER = ['swim', 'bike', 'run', 'brick', 'gym', 'hike', 'other']

  // Nach Kalenderwoche, nicht nach Planwochennummer. Über die Nummer
  // gefiltert zeigte der Breakdown bei jedem Athleten, dessen Aufbau noch
  // nicht begonnen hat, sämtliche jemals absolvierten Einheiten: Vor dem
  // Startdatum bekommt jede Einheit die Nummer 1, und die laufende Woche
  // ist dann ebenfalls 1. Dieselbe Korrektur wie im Backend — hier stand
  // sie ein zweites Mal.
  const { von: wocheVon, bis: wocheBis } = kalenderwoche()
  const weekSessions = sessions.filter(
    s => !s.deleted_at && s.session_date >= wocheVon && s.session_date <= wocheBis
  )
  const totals = { count: 0, km: 0, min: 0 }
  const byDisc = {}
  weekSessions.forEach(s => {
    const d = s.discipline?.toLowerCase()
    totals.count++; totals.km += s.distance_km || 0; totals.min += s.duration_min || 0
    if (!byDisc[d]) {
      byDisc[d] = { count: 0, km: 0, min: 0, dates: [], reflektiert: 0, sport_type: s.sport_type }
    }
    byDisc[d].count++; byDisc[d].km += s.distance_km || 0; byDisc[d].min += s.duration_min || 0
    byDisc[d].dates.push(s.session_date)
    if (s.reflection) byDisc[d].reflektiert++
  })

  // Aus den tatsächlich absolvierten Einheiten aufgebaut, nicht aus einer
  // Aufzählung im Code.
  const discEntries = Object.keys(byDisc)
    .sort((a, b) => {
      const ia = DISC_ORDER.indexOf(a), ib = DISC_ORDER.indexOf(b)
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib)
    })
    .map(d => [d, {
      label: disciplineLabel(d, byDisc[d].sport_type),
      color: disciplineColor(d),
    }])

  const CARD = 'bg-[#111318] border border-[#1e2228] rounded-xl'
  const LABEL = 'text-xs font-mono tracking-widest text-[var(--text-secondary)]'
  const SECTION_TITLE = 'text-xs font-mono tracking-widest text-[var(--text-secondary)] mb-4'

  return (
    <div className="space-y-4 page-enter">
      {/* Liegt vor dem übrigen Inhalt: Das Dashboard ist dahinter sichtbar,
          aber abgedunkelt — der Athlet sieht, wohin er kommt, kann es aber
          noch nicht bedienen. */}
      <IntakeDialog open={intakeFaellig === true} name={profile?.name} onFertig={() => { setIntakeFaellig(false); load() }} />

      {/* Vor der Checkliste: Solange die Adresse unbestätigt ist, ist der
          erste Schritt nicht das Ziel, sondern das Postfach. */}
      {konto && konto.email_verified === false && <EmailBestaetigung email={konto.email} />}

      <Onboarding warten={intakeFaellig !== false} />

      {/* Page header — rechts der laufende Tag. Die TODAY-Kachel nennt den
          Wochentag, aber nirgends stand bisher das Datum. */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
      <div>
        <h1 className="text-3xl font-black tracking-tight text-[#e8eaf0]" style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>
          DASHBOARD
        </h1>
        {/* Nach dem Renntag zählt keine Wochennummer mehr auf ein Ziel hin,
            das schon gelaufen ist — dann steht hier Off Season und der
            Hinweis auf das nächste Ziel. */}
        {metrics?.season_state === 'off_season' ? (
          <h2 className="text-3xl font-black tracking-tight"
              style={{ fontFamily: 'Barlow Condensed, sans-serif', color: phaseColor('Off Season') }}>
            OFF SEASON
            {metrics.race_date && (
              <span className="ml-3 text-sm font-mono tracking-widest text-[var(--text-muted)]">
                {Math.abs(daysUntil(metrics.race_date))} TAGE SEIT DEM RENNEN
              </span>
            )}
          </h2>
        ) : metrics?.season_state === 'base_period' ? (
          /* Ziel steht, der Aufbau beginnt später. Hier eine Wochennummer zu
             zeigen wäre falsch: Diese Wochen zählen nicht auf den Plan. */
          /* Die Überschrift ist hier selbst der Phasenname, also trägt sie
             auch dessen Farbe — im dritten Zweig steht die Phase dagegen als
             eigener Zusatz neben der Wochennummer. */
          <h2 className="text-3xl font-black tracking-tight"
              style={{ fontFamily: 'Barlow Condensed, sans-serif', color: phaseColor('Grundlage') }}>
            GRUNDLAGE
            {metrics.plan_start_date && (
              <span className="ml-3 text-sm font-mono tracking-widest text-[var(--text-muted)]">
                AUFBAU AB {metrics.plan_start_date.slice(8, 10)}.{metrics.plan_start_date.slice(5, 7)}.{metrics.plan_start_date.slice(0, 4)}
                {' · '}NOCH {Math.max(0, Math.ceil(daysUntil(metrics.plan_start_date) / 7))} WOCHEN
              </span>
            )}
          </h2>
        ) : metrics?.week_number ? (
          <h2 className="text-3xl font-black tracking-tight text-[#e8eaf0]" style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>
            WEEK {metrics.week_number}
            {metrics.total_weeks && (
              <span className="text-[var(--text-muted)]"> / {metrics.total_weeks}</span>
            )}
            {metrics.phase && (
              <span className="ml-3" style={{ color: phaseColor(metrics.phase) }}>
                {metrics.phase.toUpperCase()}
              </span>
            )}
            {/* Wie weit ist es noch — die Zahl, nach der man beim Öffnen als
                Erstes sucht, stand bisher nur im Profil. */}
            {metrics.race_date && daysUntil(metrics.race_date) >= 0 && (
              <span className="ml-3 text-sm font-mono tracking-widest text-[var(--text-secondary)]">
                {daysUntil(metrics.race_date) === 0
                  ? 'HEUTE IST RENNTAG'
                  : `NOCH ${daysUntil(metrics.race_date)} TAGE`}
              </span>
            )}
          </h2>
        ) : null}
      </div>

        <div className="text-right">
          <div className="text-2xl font-black tracking-tight text-[#e8eaf0]"
               style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>
            {new Date().toLocaleDateString('de-DE', { weekday: 'long' }).toUpperCase()}
          </div>
          <div className="text-xs font-mono text-[var(--text-muted)] tabular-nums">
            {new Date().toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })}
          </div>
        </div>
      </div>

      {/* ── Umfang der Woche: Anzahl, Zeit, Strecke ──
          Ganz oben, weil es die Fakten sind — was tatsächlich passiert ist,
          bevor es um Bewertung und Bereitschaft geht. */}
      <div className={`${CARD} p-5`}>
        <div className={SECTION_TITLE}>THIS WEEK</div>
        <div className="grid grid-cols-3 gap-3">
          {[
            { label: 'SESSIONS', value: totals.count },
            { label: 'TIME',     value: fmtTime(totals.min) },
            { label: 'DISTANCE', value: totals.km.toFixed(1), unit: 'km' },
          ].map(({ label, value, unit, color, hint }) => (
            <div key={label} className="text-center">
              <div className={`${LABEL} mb-1.5`}>{label}</div>
              <div className="text-5xl font-black leading-none font-mono"
                   style={{ color: color || '#e8eaf0', fontFamily: 'Barlow Condensed, sans-serif' }}>
                {value}
              </div>
              {(unit || hint) && (
                <div className="text-xs text-[var(--text-secondary)] font-mono mt-1">
                  {[unit, hint].filter(Boolean).join(' · ')}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* ── Wie es dir geht: HRV und Gesundheitszustand ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* HRV — zwei Spalten, weil Ring, Einordnung und Eingabe nebeneinander stehen */}
        <div
          className={`${CARD} p-5 lg:col-span-2 flex items-center gap-4 relative overflow-hidden`}
          style={{ transition: 'box-shadow 0.6s ease' }}
        >
          {/* Status radial glow — the whole card breathes with readiness */}
          <div
            className="absolute inset-0 pointer-events-none"
            style={{
              background: `radial-gradient(ellipse 60% 80% at 18% 50%, ${statusColor}0e 0%, transparent 70%)`,
              animation: 'hrvGlow 3s ease-in-out infinite',
            }}
          />

          {/* Ring */}
          <div className="relative flex-shrink-0 z-10">
            {/* Breathing outer ring */}
            <div
              className="absolute inset-0 rounded-full"
              style={{
                boxShadow: `0 0 18px 4px ${statusColor}30`,
                animation: 'hrvBreath 3s ease-in-out infinite',
              }}
            />
            <svg width="64" height="64" viewBox="0 0 72 72">
              <circle cx="36" cy="36" r="30" fill="none" stroke="#1e2228" strokeWidth="5" />
              <circle
                cx="36" cy="36" r="30"
                fill="none" stroke={statusColor} strokeWidth="5"
                strokeDasharray={`${2 * Math.PI * 30}`}
                strokeDashoffset={`${2 * Math.PI * 30 * (1 - Math.min(Math.max((hrv?.rmssd || 61) - 61, 0) / (99 - 61), 1))}`}
                strokeLinecap="round"
                transform="rotate(-90 36 36)"
                style={{ filter: `drop-shadow(0 0 6px ${statusColor}88)`, transition: 'stroke-dashoffset 0.6s ease' }}
              />
            </svg>
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="font-mono font-bold text-base" style={{ color: statusColor }}>
                {hrv ? Math.round(hrv.rmssd) : '–'}
              </span>
            </div>
          </div>

          {/* Text */}
          <div className="flex-1 min-w-0 z-10">
            <div className={LABEL}>HRV TODAY</div>
            <div className="text-xl font-bold mt-1 mb-1" style={{ color: statusColor, fontFamily: 'Barlow Condensed, sans-serif' }}>
              {HRV_TEXT[status]}
            </div>
            {hrv && (
              <div className="text-xs font-mono text-[var(--text-secondary)]">
                {hrv.measured_at} · {hrv.rmssd} ms rMSSD
                {hrv.readiness_score != null && ` · ${hrv.readiness_score} Body Battery`}
              </div>
            )}
          </div>

          <div className="flex-shrink-0">
            <HRVInput onSaved={load} />
          </div>
        </div>

        <HealthStatus variant="tile" onChanged={load} />
      </div>

      {/* ── Heute: die Frage, mit der man das Dashboard öffnet ── */}
      <TodayCard onOpenPlan={() => navigate('/plan')} />

      {/* ── Aufschlüsselung der Woche ── */}
      {discEntries.length > 0 && (
        <div className={`${CARD} p-5`}>
          <div className={SECTION_TITLE}>
            BREAKDOWN <span className="text-[var(--text-muted)]">· SPORTART ANKLICKEN FÜR INSIGHTS UND REFLEXION</span>
          </div>

          {/* Discipline cards */}
          {/* Disziplinen links, Zonenverteilung rechts: dieselbe Woche einmal
              nach Sportart und einmal nach Intensität. Untereinander ließ
              jede der beiden die halbe Breite leer. */}
          {/* Feste Breite für die Zonen statt halbe-halbe: das Diagramm braucht
              nicht mehr, und die Disziplinkarten passen dadurch in eine Reihe
              statt in zwei mit einer angebrochenen. */}
          <div className="grid gap-5"
               style={metrics?.hr_zones_avg
                 ? { gridTemplateColumns: 'minmax(0, 1fr) minmax(300px, 340px)' }
                 : undefined}>
          <div className="grid gap-3 content-start"
               style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))' }}>
            {discEntries.map(([disc, cfg]) => {
              const s = byDisc[disc]
              const aktiv = gewaehlteDisziplin === disc
              return (
                <button
                  key={disc}
                  onClick={() => setGewaehlteDisziplin(aktiv ? null : disc)}
                  title={aktiv ? 'Filter aufheben' : `Nur ${cfg.label} zeigen`}
                  className="rounded-xl p-4 text-left transition-all"
                  style={{
                    background: aktiv ? `${cfg.color}1c` : `${cfg.color}0a`,
                    border: `1px solid ${cfg.color}${aktiv ? '66' : '25'}`,
                    borderLeft: `3px solid ${cfg.color}`,
                  }}
                >
                  <div className="flex items-center gap-1.5 text-xs font-mono font-semibold mb-2.5"
                       style={{ color: cfg.color }}>
                    <SportIcon discipline={disc} size={15} />
                    <span className="flex-1 min-w-0 truncate">{cfg.label}</span>
                    <span className="text-[var(--text-muted)]">{aktiv ? '▴' : '▾'}</span>
                  </div>
                  <div className="text-3xl font-black leading-none mb-2 font-mono" style={{ color: cfg.color, fontFamily: 'Barlow Condensed, sans-serif' }}>{s.count}</div>
                  <div className="space-y-0.5">
                    <div className="text-sm font-mono text-[#e8eaf0]">{fmtTime(s.min)}</div>
                    {s.km > 0 && <div className="text-xs font-mono text-[var(--text-secondary)]">{s.km.toFixed(1)} km</div>}
                    {/* An welchen Tagen — ohne das ist „2 Einheiten" nur eine
                        Zahl und man muss unten nachsehen. */}
                    <div className="text-[10px] font-mono text-[var(--text-secondary)] pt-1">
                      {s.dates
                        .slice()
                        .sort()
                        .map(d => new Date(d + 'T00:00:00').toLocaleDateString('de-DE', { weekday: 'short' }))
                        .join(' · ')}
                    </div>
                    {/* Wie viele Einheiten schon eine Reflexion haben —
                        sonst muss man jede Kachel aufklappen, um es zu sehen. */}
                    <div className="text-[10px] font-mono pt-0.5"
                         style={{ color: s.reflektiert === s.count ? '#22c55e' : 'var(--text-muted)' }}>
                      {s.reflektiert === s.count
                        ? '✓ reflektiert'
                        : `${s.reflektiert}/${s.count} reflektiert`}
                    </div>
                  </div>
                </button>
              )
            })}
          </div>

          {metrics?.hr_zones_avg && (
            <div className="lg:border-l lg:border-[#1e2228] lg:pl-5">
              {/* Belastung und Durchschnittspuls gehören zur Zusammensetzung
                  der Woche, nicht zu ihrem Umfang — neben Anzahl und Strecke
                  standen sie ohne erkennbaren Bezug. */}
              {/* Belastung, Puls und Form gleichmäßig über der Zonenverteilung:
                  drei Zahlen zur selben Woche, gleich gewichtet. */}
              <div className="grid grid-cols-3 gap-3 mb-4 pb-4 border-b border-[#1e2228]">
                {[
                  { label: 'TSS', wert: metrics?.total_tss ?? 0, farbe: '#e8eaf0', zusatz: null },
                  {
                    label: 'Ø PULS', wert: avgHr ?? '–', farbe: hrColor,
                    zusatz: avgHr ? (hrZoneIndex == null ? 'bpm' : `bpm · ${HR_ZONE_LABEL[hrZoneIndex]}`) : null,
                  },
                  {
                    label: 'FORM · TSB',
                    wert: form == null ? '–' : `${form > 0 ? '+' : ''}${form}`,
                    farbe: formFarbe,
                    zusatz: form == null ? null : formText(form).toUpperCase(),
                  },
                ].map(({ label, wert, farbe, zusatz }) => (
                  <div key={label}>
                    <div className={LABEL}>{label}</div>
                    <div className="text-3xl font-black font-mono leading-none mt-1"
                         style={{ color: farbe, fontFamily: 'Barlow Condensed, sans-serif' }}>
                      {wert}
                    </div>
                    {zusatz && (
                      <div className="text-[10px] font-mono mt-1" style={{ color: farbe, opacity: 0.75 }}>
                        {zusatz}
                      </div>
                    )}
                  </div>
                ))}
              </div>
              <div className={`${LABEL} mb-3`}>HR ZONES · WEEK AVERAGE</div>
              <HRZoneChart zones={metrics.hr_zones_avg} />
            </div>
          )}
          </div>

          {/* Aufgeklappte Sportart: alles zu diesen Einheiten an einer Stelle
              — Abweichung vom Plan und das Feld für die Reflexion. Eine
              zweite Liste unter den Kacheln hätte dieselbe Information ein
              weiteres Mal aufgeführt. */}
          {gewaehlteDisziplin && (
            <div className="mt-5 pt-5 border-t border-[#1e2228] space-y-3">
              {[...weekSessions]
                .filter(s => s.discipline?.toLowerCase() === gewaehlteDisziplin)
                .sort((a, b) => (a.session_date < b.session_date ? 1 : -1))
                .map(s => {
                  const farbe = DISCIPLINE_COLOR[gewaehlteDisziplin] || '#8a909e'
                  const tag = new Date(s.session_date + 'T00:00:00')
                    .toLocaleDateString('de-DE', {
                      weekday: 'long', day: '2-digit', month: '2-digit', year: 'numeric',
                    })
                  return (
                    <div key={s.id} className="rounded-xl p-4"
                         style={{ background: '#0d0f17', border: `1px solid ${farbe}22` }}>
                      <div className="flex items-baseline justify-between gap-3 flex-wrap mb-3">
                        <div className="flex items-baseline gap-3 flex-wrap">
                          <SportIcon discipline={gewaehlteDisziplin} size={16} color={farbe} />
                          <span className="text-sm font-mono" style={{ color: farbe }}>{tag}</span>
                          {s.intensity_label && (
                            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded"
                                  style={{ background: `${farbe}12`, border: `1px solid ${farbe}2e`, color: farbe }}>
                              {s.intensity_label}
                            </span>
                          )}
                        </div>
                        <button
                          onClick={() => setOffeneEinheit(s)}
                          className="text-[10px] font-mono text-[var(--text-muted)] hover:text-[#00d4ff]"
                          title="Diagramme, Zonen und Streams"
                        >
                          DETAILS ▸
                        </button>
                      </div>

                      {/* Kennzahlen der Einheit */}
                      <div className="flex gap-5 flex-wrap mb-3">
                        {[
                          ['DAUER', s.duration_min ? fmtTime(s.duration_min) : '—'],
                          ['STRECKE', s.distance_km ? `${s.distance_km.toFixed(1)} km` : '—'],
                          ['TSS', s.tss ? Math.round(s.tss) : '—'],
                          ['Ø PULS', s.avg_hr ? `${s.avg_hr} bpm` : '—'],
                          ...(s.avg_watts ? [['Ø WATT', `${s.avg_watts} W`]] : []),
                        ].map(([label, wert]) => (
                          <div key={label}>
                            <div className="text-[9px] font-mono tracking-widest text-[var(--text-muted)]">{label}</div>
                            <div className="text-sm font-mono tabular-nums text-[#e8eaf0] mt-0.5">{wert}</div>
                          </div>
                        ))}
                      </div>

                      {/* Der Plan/Ist-Abgleich — die eigentliche Erkenntnis. */}
                      {s.deviation_note && (
                        <div className="text-[11px] font-mono text-[var(--text-secondary)] leading-relaxed mb-3 pl-2 border-l"
                             style={{ borderColor: `${farbe}44` }}>
                          {s.deviation_note}
                        </div>
                      )}

                      <div className="text-[9px] font-mono tracking-widest text-[var(--text-muted)] mb-1.5">REFLEXION</div>
                      <ReflectionEditor session={s} rows={2} onSaved={load} />
                    </div>
                  )
                })}
            </div>
          )}
        </div>
      )}

      {/* ── Form über die Zeit ── */}
      <div className={`${CARD} p-5`}>
        <div className={SECTION_TITLE}>PERFORMANCE MANAGEMENT</div>
        <PerformanceChart sessions={sessions} />
      </div>

      {/* ── HRV-Verlauf ── */}
      <div className={`${CARD} p-5`}>
        <div className={SECTION_TITLE}>HRV HISTORY · Grüner Bereich = deine Normalspanne</div>
        <HRVHistoryChart data={hrvHistory} />
      </div>

      {/* ── Begriffe ── */}
      <Glossary />

      {offeneEinheit && (
        <SessionDetail
          session={offeneEinheit}
          onClose={() => { setOffeneEinheit(null); load() }}
        />
      )}

      <style>{`
        @keyframes hrvBreath {
          0%, 100% { opacity: 0.4; transform: scale(0.95); }
          50%       { opacity: 1;   transform: scale(1.05); }
        }
        @keyframes hrvGlow {
          0%, 100% { opacity: 0.6; }
          50%       { opacity: 1; }
        }
      `}</style>
    </div>
  )
}
