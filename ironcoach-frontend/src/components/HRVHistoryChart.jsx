import { useState, useMemo } from 'react'
import {
  ComposedChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Area
} from 'recharts'
import HRVHeatmap from './HRVHeatmap'

const STATUS_COLOR = { green: '#22c55e', yellow: '#eab308', red: '#ef4444' }

const RANGE_OPTIONS = [
  { label: '7d', days: 7 },
  { label: '30d', days: 30 },
  { label: '60d', days: 60 },
]

function computeBaseline(data) {
  return data.map((point, i) => {
    const window = data.slice(Math.max(0, i - 6), i + 1)
    const mean = window.reduce((a, b) => a + b.rmssd, 0) / window.length
    const variance = window.reduce((a, b) => a + (b.rmssd - mean) ** 2, 0) / window.length
    const std = Math.sqrt(variance)
    return {
      ...point,
      upper: parseFloat((mean + std).toFixed(1)),
      lower: parseFloat((mean - std).toFixed(1)),
      mean: parseFloat(mean.toFixed(1)),
    }
  })
}

const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload
  return (
    <div className="border rounded-lg px-3 py-2 text-xs space-y-1" style={{ background: '#111318', borderColor: '#1e2228' }}>
      <div className="font-mono" style={{ color: '#8a909e' }}>{d?.fullDate}</div>
      <div className="font-mono font-bold" style={{ color: '#00d4ff' }}>{d?.rmssd} ms rMSSD</div>
      {d?.readiness_score != null && (
        <div style={{ color: '#8a909e' }}>Body Battery: <span style={{ color: '#e8eaf0' }}>{d.readiness_score}</span></div>
      )}
      <div style={{ color: '#3a3f4a' }} className="font-mono">Baseline: {d?.lower}–{d?.upper} ms</div>
    </div>
  )
}

export default function HRVHistoryChart({ data }) {
  const [range, setRange] = useState(30)

  const allChartData = useMemo(() => {
    if (!data?.length) return []
    const sorted = [...data].sort((a, b) => a.measured_at?.localeCompare(b.measured_at))
    return computeBaseline(sorted).map(d => ({
      ...d,
      date: d.measured_at?.slice(5),
      fullDate: d.measured_at,
    }))
  }, [data])

  const chartData = useMemo(() => allChartData.slice(-range), [allChartData, range])

  if (!data?.length) {
    return (
      <div className="text-center py-8 text-sm font-mono" style={{ color: '#8a909e' }}>
        No HRV data yet. Start logging!
      </div>
    )
  }

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

      <ResponsiveContainer width="100%" height={200}>
        <ComposedChart data={chartData} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e2228" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fill: '#8a909e', fontSize: 11, fontFamily: 'JetBrains Mono, monospace' }}
            axisLine={false} tickLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fill: '#8a909e', fontSize: 11, fontFamily: 'JetBrains Mono, monospace' }}
            axisLine={false} tickLine={false}
            domain={['auto', 'auto']}
          />
          <Tooltip content={<CustomTooltip />} />

          <Area type="monotone" dataKey="upper" stroke="none" fill="#22c55e" fillOpacity={0.08} legendType="none" />
          <Area type="monotone" dataKey="lower" stroke="none" fill="#07080f" fillOpacity={1} legendType="none" />
          <Line type="monotone" dataKey="mean" stroke="#22c55e" strokeWidth={1} strokeDasharray="4 3" dot={false} legendType="none" />
          <Line
            type="monotone" dataKey="rmssd" stroke="#00d4ff" strokeWidth={2}
            dot={(props) => {
              const { cx, cy, payload } = props
              const color = STATUS_COLOR[payload.hrv_status] || '#00d4ff'
              return <circle key={`dot-${payload.fullDate}`} cx={cx} cy={cy} r={3.5} fill={color} stroke="#07080f" strokeWidth={1.5} />
            }}
            activeDot={{ r: 5, fill: '#00d4ff', stroke: '#07080f', strokeWidth: 2 }}
          />
        </ComposedChart>
      </ResponsiveContainer>

      <div className="flex gap-4 px-1 text-xs" style={{ color: '#8a909e' }}>
        <span className="flex items-center gap-1.5"><span className="w-4 h-0.5 inline-block" style={{ background: '#00d4ff' }} /> rMSSD</span>
        <span className="flex items-center gap-1.5"><span className="w-4 h-0.5 inline-block opacity-50" style={{ background: '#22c55e' }} /> Baseline</span>
        <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm inline-block opacity-20" style={{ background: '#22c55e' }} /> Normal range</span>
      </div>

      {/* Heatmap */}
      <div className="pt-2">
        <HRVHeatmap data={data} weeksBack={14} />
      </div>
    </div>
  )
}
