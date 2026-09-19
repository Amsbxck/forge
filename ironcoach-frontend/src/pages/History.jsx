import { useEffect, useState, useMemo } from 'react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid
} from 'recharts'
import {
  getSessions, getHistoryPlans,
  softDeleteSession, hardDeleteSession, restoreSession
} from '../services/api'
import SessionDetail from '../components/SessionDetail'

import { ACCENT, DISCIPLINE_COLOR, DISCIPLINE_LABEL, phaseColor } from '../utils/colors'
import SportIcon from '../components/SportIcon'
import { disciplineLabel } from '../utils/colors'

// ─── Constants ────────────────────────────────────────────────────────────────

const DISC_CONFIG = Object.fromEntries(
  ['bike', 'run', 'swim', 'gym', 'brick', 'hike', 'other'].map(k => [
    k,
    {
      key: k, label: DISCIPLINE_LABEL[k],
      color: DISCIPLINE_COLOR[k], borderColor: DISCIPLINE_COLOR[k],
    },
  ])
)

// Gleiche Stufen und Farben wie im Wochenplan — dieselbe Information darf
// nicht an zwei Stellen unterschiedlich aussehen.
const INTENSITY_META = {
  base:       { short: 'BASE',      zone: 'Z1–Z2', color: '#40916c' },
  sweet_spot: { short: 'SWEETSPOT', zone: 'Z3',    color: '#f4a261' },
  threshold:  { short: 'THRESHOLD', zone: 'Z4',    color: '#e76f51' },
  vo2max:     { short: 'VO₂MAX',    zone: 'Z5',    color: '#e63946' },
}

const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function formatMonth(ym) {
  const [y, m] = ym.split('-')
  return `${MONTH_NAMES[parseInt(m) - 1]} ${y}`
}

function formatDuration(min) {
  if (!min) return null
  const h = Math.floor(min / 60)
  const m = min % 60
  return h > 0 ? `${h}h ${m > 0 ? `${m}m` : ''}`.trim() : `${m}m`
}

function formatPace(val, disc) {
  if (!val) return null
  return disc === 'swim' ? `${val.toFixed(2)}/100m` : `${val.toFixed(2)}/km`
}

// ─── Progress Tab ─────────────────────────────────────────────────────────────

const STEP_DISCS = [
  { key: 'all', label: 'Total', color: ACCENT },
  ...['bike', 'run', 'swim', 'gym'].map(k => ({
    key: k, label: DISCIPLINE_LABEL[k], color: DISCIPLINE_COLOR[k],
  })),
]

function buildMonthStepData(sessions, ym) {
  const monthSessions = sessions.filter(s => !s.deleted_at && s.session_date?.startsWith(ym))
  const sorted = [...monthSessions].sort((a, b) => a.session_date?.localeCompare(b.session_date))
  const c = { all: 0, bike: 0, run: 0, swim: 0, gym: 0 }
  const h = { all: 0, bike: 0, run: 0, swim: 0, gym: 0 }
  return sorted.map(s => {
    const disc = s.discipline?.toLowerCase()
    const hrs = parseFloat(((s.duration_min || 0) / 60).toFixed(2))
    c.all++; h.all = parseFloat((h.all + hrs).toFixed(2))
    if (c[disc] !== undefined) { c[disc]++; h[disc] = parseFloat((h[disc] + hrs).toFixed(2)) }
    return {
      date: s.session_date?.slice(8),
      all_count: c.all, bike_count: c.bike, run_count: c.run, swim_count: c.swim, gym_count: c.gym,
      all_hours: h.all, bike_hours: h.bike, run_hours: h.run, swim_hours: h.swim, gym_hours: h.gym,
    }
  })
}

const StepTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload
  return (
    <div className="bg-[#111318] border border-[#1e2228] rounded-lg px-3 py-2 text-xs space-y-1">
      <div className="text-[var(--text-secondary)] font-mono">Day {d?.date}</div>
      {payload.map(p => (
        <div key={p.dataKey} style={{ color: p.stroke }} className="font-mono">
          {p.name}: {p.value}
        </div>
      ))}
    </div>
  )
}

function fmtHours(min) {
  const h = Math.floor(min / 60)
  const m = min % 60
  if (h === 0) return `${m}m`
  return m > 0 ? `${h}h ${m}m` : `${h}h`
}

function ProgressTab({ sessions }) {
  const active = useMemo(() => sessions.filter(s => !s.deleted_at), [sessions])

  // Available months for selector
  const months = useMemo(() => {
    const set = new Set(active.map(s => s.session_date?.slice(0, 7)).filter(Boolean))
    return [...set].sort((a, b) => b.localeCompare(a))
  }, [active])

  const [selectedMonth, setSelectedMonth] = useState(null)
  const [yMode, setYMode] = useState('count')
  const [activeDiscs, setActiveDiscs] = useState(new Set(['all', 'bike', 'run', 'swim', 'gym']))

  const toggleDisc = (key) => setActiveDiscs(prev => {
    const next = new Set(prev)
    next.has(key) ? next.delete(key) : next.add(key)
    return next
  })

  const currentMonth = selectedMonth ?? months[0] ?? ''
  const stepData = useMemo(() => buildMonthStepData(sessions, currentMonth), [sessions, currentMonth])
  const suffix = yMode === 'hours' ? '_hours' : '_count'

  const stats = useMemo(() => {
    const totals = { count: 0, km: 0, min: 0 }
    const byDisc = {}
    for (const [disc] of Object.entries(DISC_CONFIG)) {
      byDisc[disc] = { count: 0, km: 0, min: 0 }
    }
    active.forEach(s => {
      const disc = s.discipline?.toLowerCase()
      totals.count++
      totals.km += s.distance_km || 0
      totals.min += s.duration_min || 0
      if (byDisc[disc]) {
        byDisc[disc].count++
        byDisc[disc].km += s.distance_km || 0
        byDisc[disc].min += s.duration_min || 0
      }
    })
    return { totals, byDisc }
  }, [active])

  if (!active.length) {
    return <div className="text-center py-8 text-[var(--text-secondary)] text-sm">No sessions yet.</div>
  }

  const disciplines = Object.entries(DISC_CONFIG).filter(([disc]) => stats.byDisc[disc].count > 0)

  return (
    <div className="space-y-5">

      {/* Monthly step chart */}
      <div className="bg-[#111318] border border-[#1e2228] rounded-xl p-5">
        {/* Controls */}
        <div className="flex flex-wrap gap-2 items-center justify-between mb-4">
          <div className="flex gap-1.5 flex-wrap">
            {STEP_DISCS.map(({ key, label, color }) => (
              <button key={key} onClick={() => toggleDisc(key)}
                className="px-2.5 py-1 rounded-lg text-xs font-mono transition-all border"
                style={{
                  borderColor: activeDiscs.has(key) ? color : '#1e2228',
                  color: activeDiscs.has(key) ? color : 'var(--text-muted)',
                  background: activeDiscs.has(key) ? `${color}15` : '#0d0f17',
                }}
              >{label}</button>
            ))}
          </div>
          <div className="flex gap-2 flex-wrap items-center">
            <select
              value={currentMonth}
              onChange={e => setSelectedMonth(e.target.value)}
              className="text-xs font-mono px-2 py-1 rounded-lg border bg-[#0d0f17] text-[var(--text-secondary)]"
              style={{ borderColor: '#1e2228' }}
            >
              {months.map(m => <option key={m} value={m}>{formatMonth(m)}</option>)}
            </select>
            <div className="flex gap-1 border border-[#1e2228] rounded-lg p-0.5 bg-[#0d0f17]">
              {[{ v: 'count', label: 'Sessions' }, { v: 'hours', label: 'Hours' }].map(opt => (
                <button key={opt.v} onClick={() => setYMode(opt.v)}
                  className="px-2.5 py-1 rounded-md text-xs font-mono transition-all"
                  style={{
                    background: yMode === opt.v ? '#00d4ff20' : 'transparent',
                    color: yMode === opt.v ? '#00d4ff' : 'var(--text-muted)',
                    border: yMode === opt.v ? '1px solid #00d4ff33' : '1px solid transparent',
                  }}
                >{opt.label}</button>
              ))}
            </div>
          </div>
        </div>
        {stepData.length === 0 ? (
          <div className="text-center py-6 text-[var(--text-muted)] text-xs font-mono">No sessions this month</div>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={stepData} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2228" vertical={false} />
              <XAxis dataKey="date" tick={{ fill: '#a7aebd', fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }} axisLine={false} tickLine={false} interval={Math.max(0, Math.floor(stepData.length / 6) - 1)} />
              <YAxis tick={{ fill: '#a7aebd', fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }} axisLine={false} tickLine={false} allowDecimals={yMode === 'hours'} />
              <Tooltip content={<StepTooltip />} />
              {STEP_DISCS.map(({ key, label, color }) => activeDiscs.has(key) && (
                <Line key={key} type="stepAfter" dataKey={`${key}${suffix}`} name={label}
                  stroke={color} strokeWidth={key === 'all' ? 2.5 : 1.5}
                  dot={false} activeDot={{ r: 3, fill: color }} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Total summary strip */}
      <div className="bg-[#111318] border border-[#1e2228] rounded-xl px-5 py-4 grid grid-cols-3 gap-4">
        {[
          { label: 'TOTAL SESSIONS', value: stats.totals.count, unit: null },
          { label: 'TOTAL DISTANCE', value: stats.totals.km.toFixed(1), unit: 'km' },
          { label: 'TOTAL TIME', value: fmtHours(stats.totals.min), unit: null },
        ].map(({ label, value, unit }) => (
          <div key={label} className="text-center">
            <div className="text-xs text-[var(--text-secondary)] font-mono tracking-widest mb-1">{label}</div>
            <div className="text-3xl font-black font-mono text-[#e8eaf0]" style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>
              {value}{unit && <span className="text-base text-[var(--text-secondary)] font-normal ml-1">{unit}</span>}
            </div>
          </div>
        ))}
      </div>

      {/* Per-discipline cards */}
      <div className={`grid gap-3 ${{1:'grid-cols-1',2:'grid-cols-2',3:'grid-cols-3',4:'grid-cols-4'}[Math.min(disciplines.length,4)]}`}>
        {disciplines.map(([disc, cfg]) => {
          const s = stats.byDisc[disc]
          const pct = Math.round((s.count / stats.totals.count) * 100)
          return (
            <div
              key={disc}
              className="bg-[#111318] border border-[#1e2228] rounded-xl overflow-hidden"
              style={{ borderLeftColor: cfg.color, borderLeftWidth: 3 }}
            >
              {/* Header */}
              <div className="flex items-center gap-2 px-4 pt-4 pb-2">
                <SportIcon discipline={cfg.key} size={20} color={cfg.color} />
                <span
                  className="text-base font-bold tracking-wide"
                  style={{ color: cfg.color, fontFamily: 'Barlow Condensed, sans-serif' }}
                >
                  {cfg.label.toUpperCase()}
                </span>
                <span className="ml-auto text-xs font-mono text-[var(--text-muted)]">{pct}% of total</span>
              </div>

              {/* Stats row */}
              <div className="grid grid-cols-3 divide-x divide-[#1e2228] border-t border-[#1e2228]">
                <div className="px-4 py-3 text-center">
                  <div className="text-2xl font-black font-mono" style={{ color: cfg.color, fontFamily: 'Barlow Condensed, sans-serif' }}>{s.count}</div>
                  <div className="text-xs text-[var(--text-secondary)] font-mono mt-0.5">sessions</div>
                </div>
                <div className="px-4 py-3 text-center">
                  <div className="text-2xl font-black font-mono text-[#e8eaf0]" style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>
                    {s.km > 0 ? s.km.toFixed(1) : '—'}
                  </div>
                  <div className="text-xs text-[var(--text-secondary)] font-mono mt-0.5">km</div>
                </div>
                <div className="px-4 py-3 text-center">
                  <div className="text-2xl font-black font-mono text-[#e8eaf0]" style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>{fmtHours(s.min)}</div>
                  <div className="text-xs text-[var(--text-secondary)] font-mono mt-0.5">time</div>
                </div>
              </div>

              {/* Progress bar */}
              <div className="h-1" style={{ background: '#1e2228' }}>
                <div className="h-full transition-all" style={{ width: `${pct}%`, background: cfg.color, opacity: 0.6 }} />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─── Sessions Timeline ─────────────────────────────────────────────────────────

function SessionRow({ session: s, onDelete, onHardDelete, onRestore, onClick }) {
  const disc = s.discipline?.toLowerCase()
  const cfg = DISC_CONFIG[disc] || { key: disc, color: 'var(--text-secondary)' }
  const intensity = INTENSITY_META[s.intensity]
  // "Ungeplantes Training" ist keine Abweichung im engeren Sinn — das wäre
  // bei ungeplanten Wochen sonst ein Warndreieck in jeder zweiten Zeile.
  const deviation = s.deviation_note && !s.deviation_note.startsWith('Keine geplante')
    ? s.deviation_note
    : null
  const unplanned = Boolean(s.deviation_note?.startsWith('Keine geplante'))

  return (
    <div
      className={`flex items-center gap-3 px-4 py-3 border-l-2 hover:bg-[#111318] transition-colors cursor-pointer group ${s.deleted_at ? 'opacity-40' : ''}`}
      style={{ borderLeftColor: cfg.color }}
      onClick={onClick}
    >
      <div className="flex-shrink-0 w-6 flex justify-center">
        <SportIcon discipline={cfg.key} size={16} color={cfg.color} />
      </div>
      <div className="w-14 flex-shrink-0 font-mono text-xs text-[var(--text-secondary)]">{s.session_date?.slice(5)}</div>
      <div className="w-18 flex-shrink-0 text-xs text-[#e8eaf0] hidden sm:block">{cfg.label}</div>

      {/* Klassifizierung: Intensitätsstufe und erkannter Trainingstyp */}
      <div className="flex items-center gap-1.5 flex-shrink-0">
        {intensity && (
          <span
            className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded leading-none whitespace-nowrap"
            style={{ color: intensity.color, background: `${intensity.color}1e`, border: `1px solid ${intensity.color}44` }}
            title={`Intensität ${intensity.short} (${intensity.zone})`}
          >
            {intensity.short}
          </span>
        )}
        {s.actual_type && (
          <span className="text-[10px] font-mono text-[var(--text-secondary)] hidden lg:inline whitespace-nowrap">
            {s.actual_type.replace(/_/g, ' ')}
          </span>
        )}
      </div>

      <div className="flex gap-3 flex-1 min-w-0 flex-wrap">
        {s.duration_min && <span className="text-xs font-mono text-[var(--text-secondary)]">{formatDuration(s.duration_min)}</span>}
        {s.distance_km && <span className="text-xs font-mono text-[var(--text-secondary)]">{s.distance_km} km</span>}
        {s.avg_watts && <span className="text-xs font-mono text-[var(--text-secondary)]">{s.avg_watts}W</span>}
        {s.avg_pace_min_km && <span className="text-xs font-mono text-[var(--text-secondary)]">{formatPace(s.avg_pace_min_km, disc)}</span>}
        {s.tss && <span className="text-xs font-mono font-semibold" style={{ color: cfg.color }}>{s.tss.toFixed(0)} TSS</span>}
        {s.avg_hr && <span className="text-xs font-mono text-[var(--text-secondary)]">{s.avg_hr} bpm</span>}
      </div>

      {/* Soll/Ist — nur wenn es wirklich abwich. Volltext im Tooltip. */}
      {(deviation || unplanned) && (
        <span
          className="text-[10px] font-mono flex-shrink-0 cursor-help leading-none"
          style={{ color: deviation ? '#f4a261' : 'var(--text-muted)' }}
          title={deviation || 'Ungeplantes Training — keine Einheit im Plan zugeordnet'}
        >
          {deviation ? '⚠' : '○'}
        </span>
      )}

      {s.hr_zones && (
        <div className="flex gap-0.5 items-end h-5 flex-shrink-0 hidden md:flex">
          {['z1','z2','z3','z4','z5'].map((z, i) => {
            const val = s.hr_zones[z] || 0
            const zoneColors = ['#3b82f6','#22c55e','#eab308','#f97316','#ef4444']
            return <div key={z} className="w-1.5 rounded-sm" style={{ height: `${Math.max(2, val * 0.18)}px`, background: zoneColors[i], opacity: val > 0 ? 0.8 : 0.2 }} />
          })}
        </div>
      )}

      <div
        className="flex gap-2 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
        onClick={e => e.stopPropagation()}
      >
        {s.deleted_at ? (
          <>
            <button onClick={onRestore} className="text-xs text-green-500 hover:text-green-400 font-mono">↩</button>
            <button onClick={onHardDelete} className="text-xs text-red-500 hover:text-red-400 font-mono">✕</button>
          </>
        ) : (
          <button onClick={onDelete} className="text-xs text-[var(--text-muted)] hover:text-red-500 font-mono transition-colors">✕</button>
        )}
      </div>
    </div>
  )
}

function SessionsTab({ sessions, showDeleted, onToggleDeleted, onRefresh }) {
  const [filter, setFilter] = useState('all')
  const [openMonths, setOpenMonths] = useState(null)
  const [selectedSession, setSelectedSession] = useState(null)

  const filtered = useMemo(() => sessions.filter(s => {
    if (!showDeleted && s.deleted_at) return false
    if (filter !== 'all' && s.discipline?.toLowerCase() !== filter) return false
    return true
  }), [sessions, filter, showDeleted])

  const grouped = useMemo(() => {
    const map = {}
    filtered.forEach(s => {
      const key = s.session_date?.slice(0, 7) || 'unknown'
      if (!map[key]) map[key] = []
      map[key].push(s)
    })
    return Object.entries(map).sort(([a], [b]) => b.localeCompare(a))
  }, [filtered])

  const effectiveOpenMonths = useMemo(() => {
    if (openMonths !== null) return openMonths
    if (!grouped.length) return new Set()
    return new Set([grouped[0][0]])
  }, [openMonths, grouped])

  const toggleMonth = (ym) => {
    setOpenMonths(prev => {
      const base = prev ?? effectiveOpenMonths
      const next = new Set(base)
      next.has(ym) ? next.delete(ym) : next.add(ym)
      return next
    })
  }

  const handleSoftDelete = async (id) => { await softDeleteSession(id); onRefresh() }
  const handleHardDelete = async (id) => {
    if (!confirm('Permanently delete? This cannot be undone.')) return
    await hardDeleteSession(id); onRefresh()
  }
  const handleRestore = async (id) => { await restoreSession(id); onRefresh() }

  return (
    <div className="space-y-4">
      {selectedSession && <SessionDetail session={selectedSession} onClose={() => setSelectedSession(null)} />}

      {/* Filter bar */}
      <div className="flex gap-2 flex-wrap items-center justify-between">
        <div className="flex gap-2 flex-wrap">
          {['all', 'bike', 'run', 'swim', 'gym', 'hike'].map(d => {
            const cfg = DISC_CONFIG[d]
            const isActive = filter === d
            return (
              <button
                key={d}
                onClick={() => setFilter(d)}
                className="px-3 py-1.5 rounded-lg text-xs font-mono transition-all border"
                style={{
                  borderColor: isActive ? (cfg?.color || '#00d4ff') : '#1e2228',
                  color: isActive ? (cfg?.color || '#00d4ff') : '#8a909e',
                  background: isActive ? `${cfg?.color || '#00d4ff'}15` : '#111318',
                }}
              >
                {d === 'all' ? 'All' : cfg?.label || d}
              </button>
            )
          })}
        </div>
        <button
          onClick={onToggleDeleted}
          className={`text-xs px-3 py-1.5 rounded-lg border font-mono transition-colors ${showDeleted ? 'border-red-500/40 text-red-400 bg-red-500/10' : 'border-[#1e2228] text-[var(--text-muted)] hover:text-[var(--text-secondary)]'}`}
        >
          {showDeleted ? 'Hide deleted' : 'Show deleted'}
        </button>
      </div>

      {grouped.length === 0 && <div className="text-center py-8 text-[var(--text-secondary)] text-sm">No sessions found.</div>}

      {grouped.map(([ym, monthSessions]) => {
        const isOpen = effectiveOpenMonths.has(ym)
        const sorted = [...monthSessions].sort((a, b) => b.session_date?.localeCompare(a.session_date))

        // Month summary stats
        const totalHours = monthSessions.reduce((acc, s) => acc + (s.duration_min || 0) / 60, 0)
        const totalTSS = monthSessions.reduce((acc, s) => acc + (s.tss || 0), 0)

        return (
          <div key={ym} className="bg-[#111318] border border-[#1e2228] rounded-xl overflow-hidden">
            <button
              onClick={() => toggleMonth(ym)}
              className="w-full flex items-center justify-between px-4 py-3 hover:bg-[#0d0f17] transition-colors"
            >
              <div className="flex items-center gap-3 flex-wrap">
                <span
                  className="text-base font-bold text-[#e8eaf0] tracking-wide"
                  style={{ fontFamily: 'Barlow Condensed, sans-serif' }}
                >
                  {formatMonth(ym).toUpperCase()}
                </span>
                <span className="text-xs font-mono text-[var(--text-secondary)] bg-[#1e2228] px-2 py-0.5 rounded-full">
                  {monthSessions.length} sessions
                </span>
                <span className="text-xs font-mono text-[var(--text-muted)]">{totalHours.toFixed(1)}h</span>
                {totalTSS > 0 && <span className="text-xs font-mono text-[var(--text-muted)]">{Math.round(totalTSS)} TSS</span>}
                <div className="flex gap-1 hidden sm:flex">
                  {['bike','run','swim','gym'].map(d => {
                    const cnt = monthSessions.filter(s => s.discipline?.toLowerCase() === d).length
                    if (!cnt) return null
                    return (
                      <span key={d}
                            className="text-xs font-mono px-1.5 py-0.5 rounded inline-flex items-center gap-1"
                            style={{ color: DISC_CONFIG[d].color, background: `${DISC_CONFIG[d].color}20` }}>
                        <SportIcon discipline={d} size={13} />
                        {cnt}
                      </span>
                    )
                  })}
                </div>
              </div>
              <span className="text-[var(--text-secondary)] text-sm font-mono flex-shrink-0">{isOpen ? '▼' : '▶'}</span>
            </button>

            {isOpen && (
              <div className="border-t border-[#1e2228] divide-y divide-[#1e2228]/40 bg-[#0d0f17]">
                {sorted.map(s => (
                  <SessionRow
                    key={s.id}
                    session={s}
                    onClick={() => setSelectedSession(s)}
                    onDelete={() => handleSoftDelete(s.id)}
                    onHardDelete={() => handleHardDelete(s.id)}
                    onRestore={() => handleRestore(s.id)}
                  />
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ─── Plans Tab ─────────────────────────────────────────────────────────────────

function PlansTab({ plans }) {
  if (!plans.length) return <p className="text-[var(--text-secondary)] text-sm py-4">No training plans generated yet.</p>
  return (
    <div className="space-y-4">
      {plans.map(p => (
        <div key={p.id} className="bg-[#111318] border border-[#1e2228] rounded-xl p-5">
          <div className="flex justify-between items-start mb-2">
            <span className="font-bold text-[#e8eaf0] tracking-wide" style={{ fontFamily: 'Barlow Condensed, sans-serif', fontSize: '1.05rem' }}>
              WEEK {p.week_number} — <span style={{ color: phaseColor(p.plan_phase) }}>{p.plan_phase}</span>
            </span>
            <span className="text-xs font-mono text-[var(--text-secondary)]">{p.week_start} – {p.week_end}</span>
          </div>
          {p.plan_content?.coaching_comment && (
            <p className="text-[var(--text-secondary)] text-sm">{p.plan_content.coaching_comment}</p>
          )}
          <div className="mt-3 flex flex-wrap gap-1">
            {(p.plan_content?.days || []).map((d, i) => (
              <span key={i} className={`text-xs px-2 py-0.5 rounded-full font-mono ${d.session_type === 'rest' ? 'bg-[#1e2228] text-[var(--text-muted)]' : 'bg-[#1e2228] text-[var(--text-secondary)]'}`}>
                {d.day.slice(0, 2)}: {d.session_type}
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

// ─── Main ──────────────────────────────────────────────────────────────────────

const TABS = [
  { key: 'sessions',  label: 'Sessions' },
  { key: 'progress',  label: 'Progress' },
  { key: 'plans',     label: 'Training Plans' },
]

export default function History() {
  const [sessions, setSessions] = useState([])
  const [plans, setPlans] = useState([])
  const [tab, setTab] = useState('sessions')
  const [showDeleted, setShowDeleted] = useState(false)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      const [s, p] = await Promise.all([
        getSessions({ include_deleted: showDeleted }),
        getHistoryPlans(),
      ])
      setSessions(s.data)
      setPlans(p.data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [showDeleted])

  return (
    <div className="space-y-5 page-enter">
      <h1 className="text-3xl font-bold tracking-tight text-[#e8eaf0]" style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>
        HISTORY
      </h1>

      <div className="flex gap-1.5 border-b border-[#1e2228]">
        {TABS.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-mono transition-all border-b-2 -mb-px ${tab === t.key ? 'border-[#00d4ff] text-[#00d4ff]' : 'border-transparent text-[var(--text-secondary)] hover:text-[#e8eaf0]'}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="text-[var(--text-secondary)] font-mono text-sm py-6 text-center tracking-widest">LOADING...</div>
      ) : (
        <>
          {tab === 'sessions' && <SessionsTab sessions={sessions} showDeleted={showDeleted} onToggleDeleted={() => setShowDeleted(v => !v)} onRefresh={load} />}
          {tab === 'progress' && <ProgressTab sessions={sessions} />}
          {tab === 'plans' && <PlansTab plans={plans} />}
        </>
      )}
    </div>
  )
}
