import { useEffect, useState } from 'react'
import { getWeekMetrics, getLatestHrv, getHrv, getSessions, getProfile } from '../services/api'
import HRVInput from '../components/HRVInput'
import HRVHistoryChart from '../components/HRVHistoryChart'
import PerformanceChart from '../components/PerformanceChart'
import HRZoneChart from '../components/HRZoneChart'

const HRV_COLOR = { green: '#22c55e', yellow: '#eab308', red: '#ef4444' }
const HRV_TEXT = {
  green: 'Normal session as planned',
  yellow: 'Possible — reduce intensity',
  red: 'Reduce intensity or rest',
}

// ─── Glossary ─────────────────────────────────────────────────────────────────

const GLOSSARY = [
  {
    term: 'TSS',
    full: 'Training Stress Score',
    color: '#00d4ff',
    desc: 'A single number expressing how stressful a workout was, combining duration and intensity.',
    formula: 'TSS = (duration_sec × NP × IF) / (FTP × 3600) × 100',
    notes: [
      'Easy 1h ride → ~40 TSS',
      'Hard 2h race → ~150 TSS',
      'For runs without power: rTSS = (duration_h × HR_IF²) × 100',
    ],
  },
  {
    term: 'CTL',
    full: 'Chronic Training Load — Fitness',
    color: '#00d4ff',
    desc: '42-day exponentially weighted average of daily TSS. Reflects your long-term fitness level. Builds slowly, fades slowly.',
    formula: 'CTL = CTL_prev + (TSS_today − CTL_prev) × (1 − e^(−1/42))   [k ≈ 0.023]',
    notes: [
      'Needs ~42 days to reach steady state',
      'Increases with consistent training weeks',
      'Drops ~2–3% per rest day',
    ],
  },
  {
    term: 'ATL',
    full: 'Acute Training Load — Fatigue',
    color: '#f97316',
    desc: '7-day exponentially weighted average of daily TSS. Reflects how tired you are right now. Reacts fast to training spikes.',
    formula: 'ATL = ATL_prev + (TSS_today − ATL_prev) × (1 − e^(−1/7))   [k ≈ 0.133]',
    notes: [
      'Responds within days to training changes',
      'Hard training week → ATL spikes quickly',
      'One rest day drops ATL ~13%',
    ],
  },
  {
    term: 'TSB',
    full: 'Training Stress Balance — Form',
    color: '#22c55e',
    desc: 'The difference between fitness and fatigue. Positive = fresh, negative = tired. Aim for +5 to +15 on race day.',
    formula: 'TSB = CTL − ATL',
    notes: [
      '> +5  →  Fresh, possibly under-trained',
      '−10 to +5  →  Optimal race window',
      '−10 to −25  →  Productive training block',
      '< −25  →  Overreaching, injury risk',
    ],
  },
  {
    term: 'rMSSD',
    full: 'Root Mean Square of Successive Differences',
    color: '#22c55e',
    desc: 'The primary HRV metric. Measures variability between consecutive heartbeats. Higher = better recovered.',
    formula: 'rMSSD = √( (1/N−1) × Σ(RR_{i+1} − RR_i)² )',
    notes: [
      'Measure first thing in the morning, lying down',
      'Normal range varies per athlete (typically 30–90ms)',
      'Green band = your personal 7-day baseline ± 1σ',
    ],
  },
]

function GlossarySection() {
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)

  return (
    <div className="border border-[#1e2228] rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-[#111318] transition-colors"
      >
        <div className="flex items-center gap-3">
          <span
            className="font-bold tracking-widest text-[#8a909e]"
            style={{ fontFamily: 'Barlow Condensed, sans-serif', fontSize: '0.85rem' }}
          >
            METRICS GLOSSARY
          </span>
          <span className="text-xs font-mono text-[#3a3f4a]">TSS · CTL · ATL · TSB · rMSSD</span>
        </div>
        <span className="text-[#8a909e] font-mono text-sm">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="border-t border-[#1e2228]">
          {/* Tab bar */}
          <div className="flex border-b border-[#1e2228] bg-[#0d0f17]">
            {GLOSSARY.map((g, i) => (
              <button
                key={g.term}
                onClick={() => setActive(i)}
                className="px-4 py-2.5 text-xs font-mono transition-all border-b-2 -mb-px"
                style={{
                  borderBottomColor: active === i ? g.color : 'transparent',
                  color: active === i ? g.color : '#3a3f4a',
                }}
              >
                {g.term}
              </button>
            ))}
          </div>

          {/* Content */}
          <div className="p-5 space-y-4 bg-[#0d0f17]">
            {(() => {
              const g = GLOSSARY[active]
              return (
                <>
                  <div>
                    <div
                      className="text-xl font-bold tracking-wide"
                      style={{ fontFamily: 'Barlow Condensed, sans-serif', color: g.color }}
                    >
                      {g.term}
                    </div>
                    <div className="text-xs text-[#8a909e] font-mono mt-0.5">{g.full}</div>
                  </div>

                  <p className="text-sm text-[#e8eaf0] leading-relaxed">{g.desc}</p>

                  <div className="bg-[#07080f] border border-[#1e2228] rounded-lg px-4 py-3">
                    <div className="text-xs text-[#3a3f4a] font-mono mb-1 uppercase tracking-wider">Formula</div>
                    <code className="text-xs font-mono" style={{ color: g.color }}>{g.formula}</code>
                  </div>

                  <ul className="space-y-1">
                    {g.notes.map((n, i) => (
                      <li key={i} className="flex items-start gap-2 text-xs text-[#8a909e]">
                        <span style={{ color: g.color }} className="mt-0.5 flex-shrink-0">›</span>
                        <span className="font-mono">{n}</span>
                      </li>
                    ))}
                  </ul>
                </>
              )
            })()}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Main Dashboard ───────────────────────────────────────────────────────────

export default function Dashboard() {
  const [metrics, setMetrics] = useState(null)
  const [hrv, setHrv] = useState(null)
  const [hrvHistory, setHrvHistory] = useState([])
  const [sessions, setSessions] = useState([])
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)

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
    <div className="flex items-center justify-center py-20 text-[#8a909e]">
      <div className="text-sm font-mono tracking-widest">LOADING...</div>
    </div>
  )

  const status = hrv?.hrv_status || 'green'
  const statusColor = HRV_COLOR[status]

  const fmtTime = (min) => { const h = Math.floor(min/60), m = min%60; return h > 0 ? `${h}h${m>0?` ${m}m`:''}` : `${m}m` }

  const DISC = {
    bike: { label: 'Cycling',  icon: '🚴', color: '#a855f7' },
    run:  { label: 'Running',  icon: '🏃', color: '#ef4444' },
    swim: { label: 'Swimming', icon: '🏊', color: '#eab308' },
    gym:  { label: 'Gym',      icon: '💪', color: '#22c55e' },
  }

  const weekSessions = sessions.filter(s => !s.deleted_at && s.week_number === metrics?.week_number)
  const totals = { count: 0, km: 0, min: 0 }
  const byDisc = {}
  weekSessions.forEach(s => {
    const d = s.discipline?.toLowerCase()
    totals.count++; totals.km += s.distance_km || 0; totals.min += s.duration_min || 0
    if (!byDisc[d]) byDisc[d] = { count: 0, km: 0, min: 0 }
    byDisc[d].count++; byDisc[d].km += s.distance_km || 0; byDisc[d].min += s.duration_min || 0
  })
  const discEntries = Object.entries(DISC).filter(([d]) => byDisc[d]?.count > 0)

  const CARD = 'bg-[#111318] border border-[#1e2228] rounded-xl'
  const LABEL = 'text-xs font-mono tracking-widest text-[#8a909e]'
  const SECTION_TITLE = 'text-xs font-mono tracking-widest text-[#8a909e] mb-4'

  return (
    <div className="space-y-4 page-enter">

      {/* Page header */}
      <div className="flex items-baseline gap-3">
        <h1 className="text-3xl font-black tracking-tight text-[#e8eaf0]" style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>
          DASHBOARD
        </h1>
        <span className="text-lg font-mono text-[#3a3f4a]">WK {metrics?.week_number}</span>
      </div>

      {/* ── Row 1: This week breakdown ── */}
      {discEntries.length > 0 && (
        <div className={`${CARD} p-5`}>
          <div className={SECTION_TITLE}>THIS WEEK</div>

          {/* Totals strip */}
          <div className="grid grid-cols-3 gap-3 mb-5 pb-5 border-b border-[#1e2228]">
            {[
              { label: 'SESSIONS', value: totals.count, unit: null },
              { label: 'DISTANCE', value: totals.km.toFixed(1), unit: 'km' },
              { label: 'TIME',     value: fmtTime(totals.min), unit: null },
            ].map(({ label, value, unit }) => (
              <div key={label} className="text-center">
                <div className={`${LABEL} mb-1.5`}>{label}</div>
                <div className="text-4xl font-black leading-none font-mono text-[#e8eaf0]" style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>{value}</div>
                {unit && <div className="text-xs text-[#8a909e] font-mono mt-1">{unit}</div>}
              </div>
            ))}
          </div>

          {/* Discipline cards */}
          <div className={`grid gap-3 ${{1:'grid-cols-1',2:'grid-cols-2',3:'grid-cols-3',4:'grid-cols-4'}[Math.min(discEntries.length,4)]}`}>
            {discEntries.map(([disc, cfg]) => {
              const s = byDisc[disc]
              return (
                <div key={disc} className="rounded-xl p-4" style={{ background: `${cfg.color}0a`, border: `1px solid ${cfg.color}25`, borderLeft: `3px solid ${cfg.color}` }}>
                  <div className="text-xs font-mono font-semibold mb-2.5" style={{ color: cfg.color }}>{cfg.icon} {cfg.label}</div>
                  <div className="text-3xl font-black leading-none mb-2 font-mono" style={{ color: cfg.color, fontFamily: 'Barlow Condensed, sans-serif' }}>{s.count}</div>
                  <div className="space-y-0.5">
                    <div className="text-sm font-mono text-[#e8eaf0]">{fmtTime(s.min)}</div>
                    {s.km > 0 && <div className="text-xs font-mono text-[#8a909e]">{s.km.toFixed(1)} km</div>}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* ── Row 2: HRV + quick stats ── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">

        {/* HRV card — spans 2 cols */}
        <div
          className={`${CARD} p-5 md:col-span-2 flex items-center gap-5 relative overflow-hidden`}
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
            <svg width="72" height="72" viewBox="0 0 72 72">
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
              <div className="text-xs font-mono text-[#8a909e]">
                {hrv.measured_at} · {hrv.rmssd} ms rMSSD
                {hrv.readiness_score != null && ` · ${hrv.readiness_score} Body Battery`}
              </div>
            )}
          </div>

          <div className="flex-shrink-0">
            <HRVInput onSaved={load} />
          </div>
        </div>

        {/* TSS + Avg HR — 1 col, stacked */}
        <div className="flex flex-col gap-4">
          <div className={`${CARD} p-5 flex-1`}>
            <div className={LABEL}>TSS THIS WEEK</div>
            <div className="text-4xl font-black font-mono mt-2 leading-none text-[#e8eaf0]" style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>
              {metrics?.total_tss ?? 0}
            </div>
          </div>
          {(() => {
            const HR_ZONE_COLORS = ['#3b82f6', '#22c55e', '#eab308', '#f97316', '#ef4444']
            const HR_ZONE_LABELS = ['Z1', 'Z2', 'Z3', 'Z4', 'Z5']
            const hr = metrics?.avg_hr
            const z = profile
            const zoneIndex = !hr ? 0
              : z && hr <= z.z1_hr_max ? 0
              : z && hr <= z.z2_hr_max ? 1
              : z && hr <= z.z3_hr_max ? 2
              : z && hr <= z.z4_hr_max ? 3
              : 4
            const hrColor = hr ? HR_ZONE_COLORS[zoneIndex] : '#e8eaf0'
            const hrZoneLabel = hr ? HR_ZONE_LABELS[zoneIndex] : null
            return (
              <div className={`${CARD} p-5 flex-1`}>
                <div className={LABEL}>AVG HEART RATE</div>
                <div className="text-4xl font-black font-mono mt-2 leading-none" style={{ color: hrColor, fontFamily: 'Barlow Condensed, sans-serif' }}>
                  {metrics?.avg_hr ?? '–'}
                  {metrics?.avg_hr && <span className="text-lg font-normal ml-1" style={{ color: hrColor, opacity: 0.8 }}>bpm</span>}
                </div>
                {hrZoneLabel && <div className="text-xs font-mono mt-1" style={{ color: hrColor, opacity: 0.7 }}>{hrZoneLabel}</div>}
              </div>
            )
          })()}
        </div>
      </div>

      {/* ── Row 3: PMC ── */}
      <div className={`${CARD} p-5`}>
        <div className={SECTION_TITLE}>PERFORMANCE MANAGEMENT</div>
        <PerformanceChart sessions={sessions} />
      </div>

      {/* ── Row 4: HRV History ── */}
      <div className={`${CARD} p-5`}>
        <div className={SECTION_TITLE}>HRV HISTORY · Green band = personal baseline ± 1σ</div>
        <HRVHistoryChart data={hrvHistory} />
      </div>

      {/* ── Row 5: HR Zones ── */}
      {metrics?.hr_zones_avg && (
        <div className={`${CARD} p-5`}>
          <div className={SECTION_TITLE}>HR ZONES THIS WEEK</div>
          <HRZoneChart zones={metrics.hr_zones_avg} />
        </div>
      )}

      {/* ── Row 6: Glossary ── */}
      <GlossarySection />

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
