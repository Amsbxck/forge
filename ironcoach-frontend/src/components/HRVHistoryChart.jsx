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
  // Die berechnete Grundlinie getrennt von den geltenden Grenzen. Sie urteilt
  // nicht — die eingetragene Spanne aus der Uhr hat Vorrang. Sie steht da, um
  // die Rechnung sichtbar zu machen: Wer seine Garmin-Spanne pflegt, soll sehen,
  // was die eigenen Messungen daneben ergeben würden.
  const [grundlinie, setGrundlinie] = useState(null)
  useEffect(() => {
    getHrvRange().then(({ data: d }) => {
      setGrenzen(d.grenzen)
      setGrundlinie(d.baseline)
    }).catch(() => {})
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
          {/* Beschriftet, weil die Fläche jetzt oben begrenzt ist: Seit die
              Normalspanne beide Grenzen hat (Mittelwert ± 0,5 σ), liegt ein
              auffällig guter Wert **über** dem grünen Band — ohne Beschriftung
              liest sich das wie "ausserhalb des guten Bereichs". Über der
              Spanne ist nicht schlechter als darin, nur nachweislich anders. */}
          {grenzen && (
            <ReferenceArea y1={grenzen.gruen_ab} y2={grenzen.gruen_bis || 'dataMax'}
                           fill="#22c55e" fillOpacity={0.08} stroke="none"
                           label={{ value: 'NORMALSPANNE', position: 'insideTopLeft',
                                    fill: '#22c55e', fillOpacity: 0.7, fontSize: 9,
                                    fontFamily: 'monospace', letterSpacing: '0.1em' }} />
          )}
          {grenzen && (
            <ReferenceLine y={grenzen.gruen_ab} stroke="#22c55e" strokeOpacity={0.5} strokeDasharray="4 4" />
          )}
          {grenzen && (
            <ReferenceLine y={grenzen.rot_unter} stroke="#ef4444" strokeOpacity={0.5} strokeDasharray="4 4" />
          )}
          {/* Die berechnete Normalspanne — nur zum Vergleich, nicht als Urteil.
              Zurückgenommen gezeichnet (grau, feine Punkte), damit sie nicht mit
              der geltenden Spanne verwechselt wird. Sie erscheint nur, wenn eine
              eingetragene gilt: Sind beide dasselbe, wären es doppelte Linien. */}
          {grundlinie?.status === 'ok' && grenzen?.quelle === 'manual' && (
            <>
              <ReferenceLine y={grundlinie.band_unten} stroke="#7b8496"
                             strokeOpacity={0.45} strokeDasharray="1 3" />
              <ReferenceLine y={grundlinie.band_oben} stroke="#7b8496"
                             strokeOpacity={0.45} strokeDasharray="1 3" />
            </>
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
        {grundlinie?.status === 'ok' && grenzen?.quelle === 'manual' && (
          <span className="flex items-center gap-1.5">
            <span className="w-4 h-0.5 inline-block opacity-45" style={{ background: '#7b8496' }} /> gemessen
          </span>
        )}
      </div>

      {/* Welche Spanne gilt und welche nur daneben steht. Ohne diesen Satz wären
          vier Linien im Diagramm und keine Auskunft darüber, welche urteilt. */}
      {grenzen && (
        <p className="px-1 text-[11px] font-mono leading-relaxed" style={{ color: 'var(--text-muted)' }}>
          {grenzen.quelle === 'manual' ? (
            <>
              Es gilt deine eingetragene Spanne{' '}
              <span style={{ color: '#22c55e' }}>
                {grenzen.gruen_ab}{grenzen.gruen_bis ? `–${grenzen.gruen_bis}` : '+'} ms
              </span>
              , rot unter {grenzen.rot_unter} ms.
              {grundlinie?.status === 'ok' && (
                <> Deine {grundlinie.messungen} Messungen hier ergäben{' '}
                  <span style={{ color: '#7b8496' }}>
                    {grundlinie.band_unten}–{grundlinie.band_oben} ms
                  </span>{' '}
                  (Mittel {grundlinie.mean} ± 0,5 σ) — nur zum Vergleich, geurteilt
                  wird nach deiner Spanne.</>
              )}
            </>
          ) : (
            <>
              Normalspanne aus deinen {grundlinie?.messungen} Messungen:{' '}
              <span style={{ color: '#22c55e' }}>{grenzen.gruen_ab}–{grenzen.gruen_bis} ms</span>
              {' '}(Mittel {grundlinie?.mean} ± 0,5 σ). Innerhalb davon ist ein
              Unterschied Messrauschen. Trägst du deine Garmin-Spanne ein, gilt sie.
            </>
          )}
        </p>
      )}

      {/* Heatmap */}
      <div className="pt-2">
        <HRVHeatmap data={data} weeksBack={14} />
      </div>
    </div>
  )
}
