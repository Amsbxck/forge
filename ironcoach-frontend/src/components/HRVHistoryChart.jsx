import { useEffect, useMemo, useState } from 'react'
import {
  ComposedChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Area, ReferenceArea, ReferenceLine
} from 'recharts'
import HRVHeatmap from './HRVHeatmap'
import { getHrvRange } from '../services/api'

import { ACCENT, STATUS_COLOR } from '../utils/colors'
import { isoTag, parseTag } from '../utils/dates'

const TAG_MS = 86400000
const MONO = { fill: '#a7aebd', fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }
const tagKurz = ms => {
  const d = new Date(ms)
  return `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}.`
}

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
/** Gleitender Trend und die mitlaufende Normalspanne.
 *
 *  Zwei verschiedene Fenster, mit Absicht:
 *
 *  Der **Trend** mittelt sieben Messungen — kurz genug, um eine Woche
 *  Erschöpfung zu zeigen.
 *
 *  Die **Normalspanne** rechnet mit denselben Regeln wie `compute_baseline` im
 *  Backend: bis zu 30 Messungen, Mittelwert ± 0,5 σ, und unter 14 Messungen
 *  gar nichts. Nur dann zeigt das Diagramm die Rechnung, die auch urteilt —
 *  mit einem eigenen Fenster wäre es eine zweite, davon abweichende Rechnung,
 *  und man sähe die Bewegung einer Spanne, die es nirgends gibt.
 */
function computeBaseline(data, regeln) {
  const { minMessungen = 14, maxMessungen = 30, sigma = 0.5, fensterTage = 180 } = regeln || {}
  return data.map((point, i) => {
    const trendFenster = data.slice(Math.max(0, i - 6), i + 1)
    const mean = trendFenster.reduce((a, b) => a + b.rmssd, 0) / trendFenster.length

    // Alles bis zu diesem Punkt, höchstens die jüngsten `maxMessungen` —
    // genau das, was das Backend an diesem Tag gesehen hätte.
    // Dazu das Zeitfenster des Backends (180 Tage): Ohne es zählten hier
    // Messungen mit, die das Backend längst nicht mehr sah.
    const grenze = new Date(point.measured_at)
    grenze.setDate(grenze.getDate() - fensterTage)
    const bandFenster = data
      .slice(0, i + 1)
      .filter(d => new Date(d.measured_at) >= grenze)
      .slice(-maxMessungen)
    let band = null
    let bandMitte = null
    if (bandFenster.length >= minMessungen) {
      const werte = bandFenster.map(d => d.rmssd)
      const m = werte.reduce((a, b) => a + b, 0) / werte.length
      const varianz = werte.reduce((a, b) => a + (b - m) ** 2, 0) / werte.length
      const sd = Math.sqrt(varianz)
      band = [
        parseFloat((m - sigma * sd).toFixed(1)),
        parseFloat((m + sigma * sd).toFixed(1)),
      ]
      bandMitte = parseFloat(m.toFixed(1))
    }
    return {
      ...point,
      mean: parseFloat(mean.toFixed(1)),
      band,
      bandMitte,
    }
  })
}

const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload
  const tag = parseTag(d?.fullDate)
  return (
    <div className="border rounded-lg px-3 py-2 text-xs space-y-1" style={{ background: '#111318', borderColor: '#1e2228' }}>
      <div className="font-mono" style={{ color: 'var(--text-secondary)' }}>
        {tag ? tag.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' }) : d?.fullDate}
      </div>
      <div className="font-mono font-bold" style={{ color: '#00d4ff' }}>{d?.rmssd} ms rMSSD</div>
      {d?.readiness_score != null && (
        <div style={{ color: 'var(--text-secondary)' }}>Readiness: <span style={{ color: '#e8eaf0' }}>{d.readiness_score}</span></div>
      )}
      <div style={{ color: 'var(--text-muted)' }} className="font-mono">Trend: {d?.mean} ms</div>
      {/* Die Spanne dieses Tages — hier wird die Bewegung der Rechnung
          ablesbar, statt nur als Fläche sichtbar zu sein. */}
      {d?.band && (
        <div style={{ color: '#22c55e' }} className="font-mono">
          Normal range: {d.band[0]}–{d.band[1]} ms
          {d.bandMitte != null && (
            <span style={{ color: 'var(--text-muted)' }}> (mean {d.bandMitte})</span>
          )}
        </div>
      )}
    </div>
  )
}

export default function HRVHistoryChart({ data }) {
  const [grenzen, setGrenzen] = useState(null)
  // Die berechnete Grundlinie getrennt von den geltenden Grenzen. Mit Garmin
  // urteilt sie nicht — Garmins Spanne hat Vorrang. Sie steht trotzdem da, um
  // die Rechnung sichtbar zu machen: was die eigenen Messungen ergeben.
  const [grundlinie, setGrundlinie] = useState(null)
  // Die Regeln der Rechnung, nicht nur ihr Ergebnis — damit die gezeichnete
  // Spanne genau die ist, die das Backend rechnet. Ohne Garmin urteilt sie
  // auch; mit Garmin zeigt sie, was die eigenen Messungen ergeben.
  const [regeln, setRegeln] = useState(null)
  useEffect(() => {
    getHrvRange().then(({ data: d }) => {
      setGrenzen(d.grenzen)
      setGrundlinie(d.baseline)
      setRegeln({
        minMessungen: d.min_messungen,
        maxMessungen: d.max_messungen,
        sigma: d.band_sigma,
        fensterTage: d.fenster_tage,
      })
    }).catch(() => {})
  }, [])
  const [range, setRange] = useState(30)
  // Erklärsatz zur Fläche nur auf Klick: Ständig sichtbar war er Amir zu viel.
  const [hilfe, setHilfe] = useState(false)

  const allChartData = useMemo(() => {
    if (!data?.length) return []
    const sorted = [...data].sort((a, b) => a.measured_at?.localeCompare(b.measured_at))
    return computeBaseline(sorted, regeln).map(d => ({
      ...d,
      // Die x-Achse ist eine **Zeit**achse. Vorher stand jede Messung als
      // gleich breite Kategorie da: Wo bis Anfang Oktober nur jeden zweiten
      // Tag gemessen wurde, lagen zwei Tage so weit auseinander wie ab dem
      // 11.10. ein einziger — die täglichen Werte rückten zusammen, die
      // Beschriftung drängte sich, und eine Lücke war nicht zu sehen.
      t: parseTag(d.measured_at).getTime(),
      fullDate: d.measured_at,
    }))
  }, [data, regeln])

  // Nach Tagen, nicht nach Anzahl: `slice(-30)` waren die letzten 30
  // **Messungen** — bei Messung jeden zweiten Tag also zwei Monate unter „30d".
  const { chartData, start, ende, ticks, vorher } = useMemo(() => {
    const heute = parseTag(isoTag(new Date())).getTime()
    const anfang = heute - (range - 1) * TAG_MS
    const imFenster = allChartData.filter(d => d.t >= anfang && d.t <= heute)
    const davor = allChartData.filter(d => d.t >= anfang - range * TAG_MS && d.t < anfang)
    // Bei 7 Tagen jeder Tag, sonst die Montage: Wochen sind die Einheit,
    // in der geplant wird, und die Beschriftung bleibt dünn genug.
    const marken = []
    for (let t = anfang; t <= heute; t += TAG_MS) {
      if (range <= 7 || new Date(t).getDay() === 1) marken.push(t)
    }
    return { chartData: imFenster, start: anfang, ende: heute, ticks: marken, vorher: davor }
  }, [allChartData, range])

  // Kopfzahlen: Schnitt des Zeitraums und Richtung gegenüber dem Zeitraum
  // davor. Der zählt erst ab fünf Messungen — mit zweien wäre die Richtung
  // Zufall.
  const schnitt = werte => werte.length ? werte.reduce((a, b) => a + b, 0) / werte.length : null
  const schnittJetzt = schnitt(chartData.map(d => d.rmssd))
  const schnittVorher = vorher.length >= 5 ? schnitt(vorher.map(d => d.rmssd)) : null
  const richtung = schnittJetzt != null && schnittVorher != null ? schnittJetzt - schnittVorher : null

  if (!data?.length) {
    return (
      <div className="text-center py-8 text-sm font-mono" style={{ color: 'var(--text-secondary)' }}>
        No HRV measurements yet. Add your first one.
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Kennzahlen und Zeitraum in einer Zeile. Gleich gebaute Felder
          — Name oben, Zahl in derselben Größe auf einer Grundlinie, Einheit
          klein dahinter —, getrennt durch feine Linien. Vorher hatte jede
          Zahl ihre eigene Größe, und die Namen standen auf drei Höhen. */}
      <div className="flex items-end justify-between gap-x-4 gap-y-3 flex-wrap">
        <div className="flex">
          {[
            { name: `Ø ${range} DAYS`, wert: schnittJetzt != null ? Math.round(schnittJetzt) : '–', einheit: 'ms', farbe: '#e8eaf0' },
            richtung != null && {
              name: 'VS. PREVIOUS',
              wert: `${richtung > 0 ? '+' : richtung < 0 ? '−' : '±'}${Math.abs(richtung).toFixed(1).replace('.', ',')}`,
              einheit: 'ms',
              // Grün nur nach oben, Gelb ab drei ms nach unten — kleiner ist
              // Messrauschen und bleibt neutral.
              farbe: richtung > 0.5 ? STATUS_COLOR.green : richtung < -3 ? STATUS_COLOR.yellow : '#a7aebd',
            },
          ].filter(Boolean).map((f, i) => (
            <div key={f.name} className={i === 0 ? 'pr-5' : 'px-5 border-l border-[#1e2228]'}>
              <div className="text-[9px] font-mono tracking-[0.2em] text-[var(--text-muted)] whitespace-nowrap">{f.name}</div>
              <div className="flex items-baseline gap-1 mt-1.5">
                <span className="text-3xl font-black leading-none tabular-nums"
                      style={{ color: f.farbe, fontFamily: 'Barlow Condensed, sans-serif' }}>
                  {f.wert}
                </span>
                <span className="text-[10px] font-mono text-[var(--text-muted)] whitespace-nowrap">{f.einheit}</span>
              </div>
            </div>
          ))}
        </div>

        {/* Zeitraum als ein Schalter statt drei loser Knöpfe */}
        <div className="flex rounded-lg p-0.5" style={{ background: '#0d0f14', border: '1px solid #1e2228' }}>
          {RANGE_OPTIONS.map(opt => (
            <button
              key={opt.days}
              onClick={() => setRange(opt.days)}
              className="px-3 py-1 rounded-md text-[10px] font-mono tracking-widest transition-colors"
              style={{
                color: range === opt.days ? ACCENT : '#8a909e',
                background: range === opt.days ? `${ACCENT}1f` : 'transparent',
                boxShadow: range === opt.days ? `inset 0 0 0 1px ${ACCENT}44` : 'none',
              }}
            >
              {opt.label.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      <ResponsiveContainer width="100%" height={200}>
        <ComposedChart key={range} data={chartData} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
          {/* Senkrecht die Wochen (an den Montagen der Achse), waagrecht nur
              ein Hauch — das Gitter soll gliedern, nicht mitreden. */}
          <CartesianGrid stroke="#1e2228" strokeOpacity={0.7} horizontal={false} />
          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={[start, ende]}
            ticks={ticks}
            tickFormatter={tagKurz}
            tick={MONO}
            axisLine={false} tickLine={false}
            padding={{ left: 6, right: 6 }}
          />
          <YAxis
            tick={MONO}
            axisLine={false} tickLine={false}
            domain={['auto', 'auto']}
            tickCount={4}
          />
          <Tooltip content={<CustomTooltip />} />

          {/* Die **berechnete** Normalspanne, mitlaufend als Fläche: je Tag die
              Spanne, die das Backend an diesem Tag ergeben hätte. Wird die
              Streuung grösser, öffnet sie sich; verschiebt sich das Mittel,
              wandert sie mit. Sie bleibt auch mit Garmin stehen, und eine
              Garmin-Linie gibt es hier nicht mehr — Vorgeschichte in einem
              Satz: Die Garmin-Spanne war erst eine Fläche, die die Rechnung
              verdeckte, dann gestrichelte Linien neben ihr, und keiner sah,
              welches Grün urteilt. Garmins Spanne steht jetzt im Profil und
              urteilt hier nur über die Farbe der Punkte; das sagt der Satz
              unter dem Diagramm. */}
          <Area dataKey="band" fill="#22c55e" fillOpacity={0.10} stroke="none"
                isAnimationActive={false} connectNulls legendType="none"
                activeDot={false} />
          {/* Die Ränder zusätzlich als feine Linien: Sie machen die Bewegung
              auch dort erkennbar, wo die Fläche flach verläuft, und sie geben
              der Spanne eine Kante statt eines Farbverlaufs. */}
          <Line type="monotone" dataKey={d => d.band?.[1]} stroke="#22c55e" strokeWidth={1}
                strokeOpacity={0.45} strokeDasharray="2 3" dot={false} legendType="none"
                isAnimationActive={false} connectNulls activeDot={false} name="Spanne oben" />
          <Line type="monotone" dataKey={d => d.band?.[0]} stroke="#22c55e" strokeWidth={1}
                strokeOpacity={0.45} strokeDasharray="2 3" dot={false} legendType="none"
                isAnimationActive={false} connectNulls activeDot={false} name="Spanne unten" />

          {/* Die rote Grenze als Bezug. Gestrichelt und ohne Fläche: Sie
              entscheidet über Rot, soll aber die Bewegung der Rechnung nicht
              überdecken. */}
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

      <div className="flex gap-x-4 gap-y-1 flex-wrap px-1 text-[10px] font-mono" style={{ color: 'var(--text-secondary)' }}>
        <span className="flex items-center gap-1.5"><span className="w-4 h-0.5 inline-block" style={{ background: '#00d4ff' }} /> rMSSD</span>
        <span className="flex items-center gap-1.5"><span className="w-4 h-0.5 inline-block opacity-50" style={{ background: '#22c55e' }} /> Trend</span>
        <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm inline-block opacity-25" style={{ background: '#22c55e' }} /> Normal range (calculated)</span>
        <span className="flex items-center gap-1.5"><span className="w-4 h-0.5 inline-block opacity-60" style={{ background: '#ef4444' }} /> Red limit</span>
        <button type="button" onClick={() => setHilfe(h => !h)} aria-expanded={hilfe}
                aria-label="Was die grüne Fläche bedeutet" title="Was die grüne Fläche bedeutet"
                className="ml-auto w-4 h-4 rounded-full border flex items-center justify-center text-[9px] leading-none transition-colors hover:text-[#e8eaf0]"
                style={{ borderColor: hilfe ? '#e8eaf0' : 'var(--text-muted)', color: hilfe ? '#e8eaf0' : 'var(--text-muted)' }}>
          ?
        </button>
      </div>

      {/* Was die Fläche ist und wonach geurteilt wird. Mit Garmin kann ein
          Punkt in der grünen Fläche liegen und trotzdem rot sein (bewusst so,
          siehe CLAUDE.md) — ohne den Satz wirkte das wie ein Fehler. Seit
          Amirs Wunsch aufklappbar über das „?" in der Legende. */}
      {hilfe && <p className="px-1 text-[11px] font-mono leading-relaxed" style={{ color: 'var(--text-muted)' }}>
        The <span style={{ color: '#22c55e' }}>area</span> is your calculated
        normal range: mean ± 0.5 σ of your last{' '}
        {regeln?.maxMessungen ?? 30} measurements, recalculated every day. It
        widens when your variation grows and moves with your mean. Differences
        inside it are measurement noise.
        {grenzen?.quelle === 'garmin' || grenzen?.quelle === 'manual' ? (
          <> The colour of the dots follows your Garmin range (see Profile).</>
        ) : grenzen ? (
          <> It is also what you are judged by: currently{' '}
            <span style={{ color: '#22c55e' }}>{grenzen.gruen_ab}–{grenzen.gruen_bis} ms</span>,
            red below {grenzen.rot_unter} ms.</>
        ) : (
          <> Not enough measurements for a verdict yet. The range is drawn from{' '}
            {regeln?.minMessungen ?? 14} on.</>
        )}
      </p>}

      {/* Heatmap */}
      <div className="pt-2">
        <HRVHeatmap data={data} weeksBack={14} />
      </div>
    </div>
  )
}
