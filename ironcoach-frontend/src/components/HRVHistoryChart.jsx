import { useEffect, useMemo, useState } from 'react'
import {
  ComposedChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, ReferenceArea, ReferenceLine
} from 'recharts'
import HRVHeatmap from './HRVHeatmap'
import { getHrvRange } from '../services/api'

import { STATUS_COLOR } from '../utils/colors'

const RANGE_OPTIONS = [
  { label: '7d', days: 7 },
  { label: '30d', days: 30 },
  { label: '60d', days: 60 },
]

/** Gleitender Mittelwert als Trendlinie.
 *
 *  Das frühere Band aus Mittelwert ± 1σ über sieben Messungen wurde ersetzt:
 *  Es lief der Kurve hinterher. Wer zwei Wochen überlastet ist, zieht das Band
 *  mit nach unten, und alles sah weiter „normal" aus. Vor allem widersprach es
 *  der Ampel, die gegen eine feste Spanne bewertet — dasselbe Wort für zwei
 *  verschiedene Dinge auf einer Seite.
 *
 *  Der Trend bleibt: er zeigt die Richtung, ohne eine Bewertung zu behaupten.
 */
function computeBaseline(data) {
  return data.map((point, i) => {
    const window = data.slice(Math.max(0, i - 6), i + 1)
    const mean = window.reduce((a, b) => a + b.rmssd, 0) / window.length
    return {
      ...point,
      mean: parseFloat(mean.toFixed(1)),
    }
  })
}

const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload
  return (
    <div className="border rounded-lg px-3 py-2 text-xs space-y-1" style={{ background: '#111318', borderColor: '#1e2228' }}>
      <div className="font-mono" style={{ color: 'var(--text-secondary)' }}>{d?.fullDate}</div>
      <div className="font-mono font-bold" style={{ color: '#00d4ff' }}>{d?.rmssd} ms rMSSD</div>
      {d?.readiness_score != null && (
        <div style={{ color: 'var(--text-secondary)' }}>Body Battery: <span style={{ color: '#e8eaf0' }}>{d.readiness_score}</span></div>
      )}
      <div style={{ color: 'var(--text-muted)' }} className="font-mono">Trend: {d?.mean} ms</div>
    </div>
  )
}

export default function HRVHistoryChart({ data }) {
  const [grenzen, setGrenzen] = useState(null)
  useEffect(() => {
    getHrvRange().then(({ data: d }) => setGrenzen(d.grenzen)).catch(() => {})
  }, [])
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
      <div className="text-center py-8 text-sm font-mono" style={{ color: 'var(--text-secondary)' }}>
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
        <ComposedChart key={range} data={chartData} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e2228" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fill: '#a7aebd', fontSize: 11, fontFamily: 'JetBrains Mono, monospace' }}
            axisLine={false} tickLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fill: '#a7aebd', fontSize: 11, fontFamily: 'JetBrains Mono, monospace' }}
            axisLine={false} tickLine={false}
            domain={['auto', 'auto']}
          />
          <Tooltip content={<CustomTooltip />} />

          {/* Die Grenzen, nach denen die Ampel tatsächlich urteilt — nicht
              eine zweite, davon abweichende Rechnung. */}
          {grenzen && (
            <ReferenceArea y1={grenzen.gruen_ab} y2={grenzen.gruen_bis || 'dataMax'}
                           fill="#22c55e" fillOpacity={0.08} stroke="none" />
          )}
          {grenzen && (
            <ReferenceLine y={grenzen.gruen_ab} stroke="#22c55e" strokeOpacity={0.5} strokeDasharray="4 4" />
          )}
          {grenzen && (
            <ReferenceLine y={grenzen.rot_unter} stroke="#ef4444" strokeOpacity={0.5} strokeDasharray="4 4" />
          )}
          {/* Ohne Einblendung: die Animation schneidet den Pfad beim ersten
              Zeichnen ab, solange die Breite des Containers noch nicht steht —
              sichtbar als Kurve, die mitten im Diagramm endet. */}
          <Line type="monotone" dataKey="mean" stroke="#22c55e" strokeWidth={1} strokeDasharray="4 3"
                dot={false} legendType="none" isAnimationActive={false} />
          <Line
            type="monotone" dataKey="rmssd" stroke="#00d4ff" strokeWidth={2}
            isAnimationActive={false}
            dot={(props) => {
              const { cx, cy, payload, index } = props
              const color = STATUS_COLOR[payload.hrv_status] || '#00d4ff'
              // Schlüssel mit Index: an vier Tagen liegen zwei Messungen vor,
              // und ein Schlüssel nur aus dem Datum war dann doppelt. React
              // konnte die Punkte beim Umschalten des Zeitraums nicht ersetzen
              // — sichtbar als lose Punkte, die sich aufsummierten.
              return (
                <circle key={`dot-${payload.fullDate}-${index}`}
                        cx={cx} cy={cy} r={3.5} fill={color}
                        stroke="#07080f" strokeWidth={1.5} />
              )
            }}
            activeDot={{ r: 5, fill: '#00d4ff', stroke: '#07080f', strokeWidth: 2 }}
          />
        </ComposedChart>
      </ResponsiveContainer>

      <div className="flex gap-4 px-1 text-xs" style={{ color: 'var(--text-secondary)' }}>
        <span className="flex items-center gap-1.5"><span className="w-4 h-0.5 inline-block" style={{ background: '#00d4ff' }} /> rMSSD</span>
        <span className="flex items-center gap-1.5"><span className="w-4 h-0.5 inline-block opacity-50" style={{ background: '#22c55e' }} /> Trend</span>
        <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm inline-block opacity-20" style={{ background: '#22c55e' }} /> Grüner Bereich</span>
        <span className="flex items-center gap-1.5"><span className="w-4 h-0.5 inline-block opacity-60" style={{ background: '#ef4444' }} /> Rote Grenze</span>
      </div>

      {/* Heatmap */}
      <div className="pt-2">
        <HRVHeatmap data={data} weeksBack={14} />
      </div>
    </div>
  )
}
