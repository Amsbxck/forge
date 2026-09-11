import { useState } from 'react'
import SessionDetail from './SessionDetail'
import { DISCIPLINE_COLOR, DISCIPLINE_LABEL, HR_ZONE_COLOR } from '../utils/colors'

// Fläche und Schrift aus derselben Farbe statt aus Tailwind-Klassennamen:
// so bleibt das Abzeichen automatisch stimmig, wenn eine Farbe wechselt.
const DISC_CONFIG = Object.fromEntries(
  Object.entries(DISCIPLINE_LABEL).map(([key, label]) => [
    key,
    {
      label,
      color: DISCIPLINE_COLOR[key],
      style: { background: `${DISCIPLINE_COLOR[key]}26`, color: DISCIPLINE_COLOR[key] },
    },
  ])
)

export default function SessionCard({ session: s }) {
  const [showDetail, setShowDetail] = useState(false)
  const disc = s.discipline?.toLowerCase()
  const cfg = DISC_CONFIG[disc] || {
    label: s.discipline, color: 'var(--text-secondary)',
    style: { background: '#8a909e26', color: 'var(--text-secondary)' },
  }

  return (
    <>
      {showDetail && <SessionDetail session={s} onClose={() => setShowDetail(false)} />}
      <div
        className="rounded-xl p-4 flex flex-wrap gap-4 items-start border-l-2"
        style={{ background: '#111318', borderLeftColor: cfg.color, border: '1px solid #1e2228', borderLeftWidth: '3px' }}
      >
        <div>
          <span className="text-xs px-2 py-0.5 rounded-full font-mono font-medium" style={cfg.style}>
            {cfg.label.toUpperCase()}
          </span>
          <div className="text-xs mt-1 font-mono" style={{ color: 'var(--text-secondary)' }}>
            W{s.week_number} · {s.session_date}
          </div>
        </div>

        <div className="flex flex-wrap gap-4 text-sm flex-1">
          {s.duration_min && <Stat label="Duration" value={`${s.duration_min} min`} />}
          {s.distance_km && <Stat label="Distance" value={`${s.distance_km} km`} />}
          {s.avg_hr && <Stat label="Avg HR" value={`${s.avg_hr} bpm`} />}
          {s.avg_watts && <Stat label="Avg Power" value={`${s.avg_watts}W`} />}
          {s.normalized_power && <Stat label="NP" value={`${s.normalized_power}W`} />}
          {s.tss && <Stat label="TSS" value={s.tss.toFixed(1)} accent={cfg.color} />}
          {s.avg_pace_min_km && (
            <Stat
              label="Pace"
              value={s.discipline === 'swim'
                ? `${s.avg_pace_min_km.toFixed(2)} /100m`
                : `${s.avg_pace_min_km.toFixed(2)} /km`}
            />
          )}
        </div>

        {s.hr_zones && (
          <div className="flex gap-1 items-end h-8">
            {['z1', 'z2', 'z3', 'z4', 'z5'].map((z, i) => {
              const val = s.hr_zones[z] || 0
              const colors = HR_ZONE_COLOR
              return (
                <div key={z} title={`${z.toUpperCase()}: ${val}%`} className="flex flex-col items-center">
                  <div className="w-3 rounded-sm" style={{ height: `${Math.max(2, val * 0.28)}px`, background: colors[i] }} />
                </div>
              )
            })}
          </div>
        )}

        <button
          onClick={() => setShowDetail(true)}
          className="ml-auto text-xs font-mono transition-colors"
          style={{ color: 'var(--text-muted)' }}
          onMouseEnter={e => e.target.style.color = cfg.color}
          onMouseLeave={e => e.target.style.color = '#3a3f4a'}
        >
          View →
        </button>
      </div>
    </>
  )
}

function Stat({ label, value, accent }) {
  return (
    <div>
      <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>{label}</div>
      <div className="font-medium font-mono" style={{ color: accent || '#e8eaf0' }}>{value}</div>
    </div>
  )
}
