import { useMemo, useState } from 'react'
import {
  ComposedChart, Area, Bar, Cell, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, ReferenceLine
} from 'recharts'

const K_ATL = 1 - Math.exp(-1 / 7)
const K_CTL = 1 - Math.exp(-1 / 42)

function calculatePMC(sessions) {
  if (!sessions?.length) return []
  const dailyTSS = {}
  sessions.forEach(s => {
    if (s.tss != null && s.session_date) {
      const d = s.session_date.slice(0, 10)
      dailyTSS[d] = (dailyTSS[d] || 0) + s.tss
    }
  })
  const dates = Object.keys(dailyTSS).sort()
  if (!dates.length) return []

  const start = new Date(dates[0] + 'T00:00:00Z')
  const end = new Date()
  const todayUTC = end.toISOString().slice(0, 10)
  const endUTC = new Date(todayUTC + 'T00:00:00Z')
  const allDays = []
  for (let d = new Date(start); d <= endUTC; d.setUTCDate(d.getUTCDate() + 1)) {
    allDays.push(d.toISOString().slice(0, 10))
  }

  let atl = 0, ctl = 0
  return allDays.map(date => {
    const tss = dailyTSS[date] || 0
    atl = atl + (tss - atl) * K_ATL
    ctl = ctl + (tss - ctl) * K_CTL
    const tsb = ctl - atl
    return {
      date,
      label: date.slice(5),
      tss: tss || null,
      atl: parseFloat(atl.toFixed(1)),
      ctl: parseFloat(ctl.toFixed(1)),
      tsb: parseFloat(tsb.toFixed(1)),
    }
  })
}

function filterByDays(data, days) {
  const today = new Date().toISOString().slice(0, 10)
  const cutoff = new Date(today + 'T00:00:00Z')
  cutoff.setUTCDate(cutoff.getUTCDate() - days)
  const cutoffStr = cutoff.toISOString().slice(0, 10)
  return data.filter(d => d.date >= cutoffStr)
}

const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload
  if (!d) return null
  const tsbColor = d.tsb >= 0 ? '#22c55e' : '#ef4444'
  return (
    <div className="border rounded-lg px-3 py-2.5 text-xs space-y-1.5 min-w-[160px]" style={{ background: '#111318', borderColor: '#1e2228' }}>
      <div className="font-mono" style={{ color: '#8a909e' }}>{d.date}</div>
      {d.tss != null && <div style={{ color: '#e8eaf0' }}>TSS: <span className="font-mono font-bold" style={{ color: '#00d4ff' }}>{d.tss}</span></div>}
      <div style={{ color: '#e8eaf0' }}>CTL (Fitness): <span className="font-mono font-bold" style={{ color: '#00d4ff' }}>{d.ctl}</span></div>
      <div style={{ color: '#e8eaf0' }}>ATL (Fatigue): <span className="font-mono font-bold" style={{ color: '#f97316' }}>{d.atl}</span></div>
      <div className="border-t pt-1" style={{ borderColor: '#1e2228' }}>
        Form (TSB): <span className="font-mono font-bold" style={{ color: tsbColor }}>{d.tsb > 0 ? '+' : ''}{d.tsb}</span>
      </div>
    </div>
  )
}

const RANGE_OPTIONS = [
  { label: '30d', days: 30 },
  { label: '60d', days: 60 },
  { label: '90d', days: 90 },
]

export default function PerformanceChart({ sessions }) {
  const [range, setRange] = useState(60)

  const allPMC = useMemo(() => calculatePMC(sessions), [sessions])
  const pmcData = useMemo(() => filterByDays(allPMC, range), [allPMC, range])

  if (!sessions?.length || !pmcData.length) {
    return (
      <div className="text-center py-8 text-sm font-mono" style={{ color: '#8a909e' }}>
        No training data available for PMC yet.
      </div>
    )
  }

  const latest = pmcData[pmcData.length - 1]
  const tsbColor = latest?.tsb >= 0 ? '#22c55e' : '#ef4444'
  const tsbLabel = latest?.tsb >= 5 ? 'Fresh' : latest?.tsb >= -10 ? 'Optimal' : latest?.tsb >= -20 ? 'Fatigued' : 'Overloaded'

  return (
    <div className="space-y-4">
      {/* Range toggle */}
      <div className="flex gap-1.5">
        {RANGE_OPTIONS.map(opt => (
          <button
            key={opt.days}
            onClick={() => setRange(opt.days)}
            className="px-3 py-1 rounded-lg text-xs font-mono transition-colors border"
            style={{
              borderColor: range === opt.days ? '#00d4ff44' : '#1e2228',
              color: range === opt.days ? '#00d4ff' : '#8a909e',
              background: range === opt.days ? '#00d4ff22' : '#111318',
            }}
          >
            {opt.label}
          </button>
        ))}
      </div>

      <ResponsiveContainer width="100%" height={240}>
        <ComposedChart data={pmcData} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e2228" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fill: '#8a909e', fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }}
            axisLine={false} tickLine={false}
            interval={Math.floor(pmcData.length / 6)}
          />
          <YAxis yAxisId="fitness" tick={{ fill: '#8a909e', fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }} axisLine={false} tickLine={false} />
          <YAxis yAxisId="form" orientation="right" tick={{ fill: '#8a909e', fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }} axisLine={false} tickLine={false} />
          <Tooltip content={<CustomTooltip />} />
          <ReferenceLine yAxisId="form" y={0} stroke="#3a3f4a" strokeWidth={1} />

          <Area yAxisId="fitness" type="monotone" dataKey="ctl" stroke="#00d4ff" strokeWidth={2} fill="#00d4ff" fillOpacity={0.06} dot={false} activeDot={{ r: 4, fill: '#00d4ff' }} />
          <Area yAxisId="fitness" type="monotone" dataKey="atl" stroke="#f97316" strokeWidth={1.5} fill="#f97316" fillOpacity={0.04} dot={false} activeDot={{ r: 4, fill: '#f97316' }} />
          <Bar yAxisId="form" dataKey="tsb" barSize={3} radius={[2, 2, 0, 0]}>
            {pmcData.map((entry, index) => (
              <Cell key={`tsb-${index}`} fill={entry.tsb >= 0 ? '#22c55e' : '#ef4444'} fillOpacity={0.7} />
            ))}
          </Bar>
        </ComposedChart>
      </ResponsiveContainer>

      <div className="flex gap-5 text-xs px-1" style={{ color: '#8a909e' }}>
        <span className="flex items-center gap-1.5"><span className="w-4 h-0.5 inline-block" style={{ background: '#00d4ff' }} /> CTL Fitness</span>
        <span className="flex items-center gap-1.5"><span className="w-4 h-0.5 inline-block" style={{ background: '#f97316' }} /> ATL Fatigue</span>
        <span className="flex items-center gap-2">
          <span className="flex gap-0.5">
            <span className="w-1.5 h-3 rounded-sm inline-block opacity-70" style={{ background: '#22c55e' }} />
            <span className="w-1.5 h-3 rounded-sm inline-block opacity-70" style={{ background: '#ef4444' }} />
          </span>
          TSB Form
        </span>
      </div>

      {/* Summary badges */}
      <div className="flex gap-3 flex-wrap">
        {[
          { label: 'CTL Fitness', value: latest?.ctl, color: '#00d4ff' },
          { label: 'ATL Fatigue', value: latest?.atl, color: '#f97316' },
          { label: `TSB Form · ${tsbLabel}`, value: `${latest?.tsb > 0 ? '+' : ''}${latest?.tsb}`, color: tsbColor },
        ].map(({ label, value, color }) => (
          <div key={label} className="border rounded-lg px-3 py-2 flex-1 min-w-[100px]" style={{ background: '#0d0f17', borderColor: '#1e2228' }}>
            <div className="text-xs mb-0.5" style={{ color: '#8a909e' }}>{label}</div>
            <div className="font-mono font-bold text-lg" style={{ color }}>{value}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
