import { useState } from 'react'
import SessionDetail from './SessionDetail'

const DISC_CONFIG = {
  bike:  { label: 'Cycling',  color: '#a855f7', bg: 'bg-purple-900/30 text-purple-300' },
  run:   { label: 'Running',  color: '#ef4444', bg: 'bg-red-900/30 text-red-300'    },
  swim:  { label: 'Swimming', color: '#eab308', bg: 'bg-yellow-900/30 text-yellow-300' },
  gym:   { label: 'Gym',      color: '#22c55e', bg: 'bg-green-900/30 text-green-300'  },
  brick: { label: 'Brick',    color: '#f97316', bg: 'bg-orange-900/30 text-orange-300' },
}

export default function SessionCard({ session: s }) {
  const [showDetail, setShowDetail] = useState(false)
  const disc = s.discipline?.toLowerCase()
  const cfg = DISC_CONFIG[disc] || { label: s.discipline, color: '#8a909e', bg: 'bg-gray-800 text-gray-300' }

  return (
    <>
      {showDetail && <SessionDetail session={s} onClose={() => setShowDetail(false)} />}
      <div
        className="rounded-xl p-4 flex flex-wrap gap-4 items-start border-l-2"
        style={{ background: '#111318', borderLeftColor: cfg.color, border: '1px solid #1e2228', borderLeftWidth: '3px' }}
      >
        <div>
          <span className={`text-xs px-2 py-0.5 rounded-full font-mono font-medium ${cfg.bg}`}>
            {cfg.label.toUpperCase()}
          </span>
          <div className="text-xs mt-1 font-mono" style={{ color: '#8a909e' }}>
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
              const colors = ['#3b82f6', '#22c55e', '#eab308', '#f97316', '#ef4444']
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
          style={{ color: '#3a3f4a' }}
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
      <div className="text-xs" style={{ color: '#8a909e' }}>{label}</div>
      <div className="font-medium font-mono" style={{ color: accent || '#e8eaf0' }}>{value}</div>
    </div>
  )
}
