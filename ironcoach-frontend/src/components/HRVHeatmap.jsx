import { useState, useMemo, useRef, useLayoutEffect } from 'react'

import { STATUS_COLOR } from '../utils/colors'
import { parseTag } from '../utils/dates'
const STATUS_LABEL = { green: 'Good', yellow: 'Caution', red: 'Rest' }
const DAY_LABELS = ['Mon', '', 'Wed', '', 'Fri', '', 'Sun']

function isoDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function buildGrid(data, weeksBack, weeksForward) {
  const byDate = new Map()
  for (const d of data) byDate.set(d.measured_at?.slice(0, 10), d)

  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const todayIso = isoDate(today)
  const dayOfWeek = today.getDay() === 0 ? 6 : today.getDay() - 1

  const startMonday = new Date(today)
  startMonday.setDate(today.getDate() - dayOfWeek - (weeksBack - 1) * 7)

  const totalWeeks = weeksBack + weeksForward
  const columns = []
  for (let w = 0; w < totalWeeks; w++) {
    const colMonday = new Date(startMonday)
    colMonday.setDate(startMonday.getDate() + w * 7)
    const days = []
    for (let i = 0; i < 7; i++) {
      const d = new Date(colMonday)
      d.setDate(colMonday.getDate() + i)
      const iso = isoDate(d)
      const entry = byDate.get(iso)
      const isFuture = d > today
      days.push({
        date: iso,
        future: isFuture,
        today: iso === todayIso,
        ...(entry || {}),
      })
    }
    columns.push({
      days,
      // Ob die laufende Woche getroffen ist — daran richtet sich beim
      // Öffnen die Scrollposition aus.
      istDieseWoche: days.some(d => d.today),
      monthLabel: colMonday.getDate() <= 7 ? colMonday.toLocaleString('en', { month: 'short' }) : '',
    })
  }
  return columns
}

function Cell({ day, onHover, isActive }) {
  if (!day) return <div className="w-[18px] h-[18px]" />
  const hasData = day.rmssd != null
  const isFuture = day.future
  const isToday = day.today

  let color = '#1a1d24'
  if (hasData) color = STATUS_COLOR[day.hrv_status] || '#3a3f4a'
  else if (isFuture) color = '#0e1015'

  return (
    <div
      className="w-[18px] h-[18px] rounded-sm transition-all cursor-pointer"
      style={{
        background: color,
        opacity: isActive ? 1 : hasData ? 0.92 : isFuture ? 0.7 : 0.6,
        transform: isActive ? 'scale(1.4)' : 'scale(1)',
        boxShadow: isActive ? `0 0 8px ${color}` : 'none',
        border: isToday ? '1px solid #00d4ff' : '1px solid transparent',
      }}
      onMouseEnter={() => onHover(day)}
      onMouseLeave={() => onHover(null)}
    />
  )
}

export default function HRVHeatmap({ data, weeksBack = 14, weeksForward, endDate }) {
  const [hover, setHover] = useState(null)
  const computedForward = useMemo(() => {
    if (weeksForward != null) return weeksForward
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    // Ohne Zieldatum zwölf Wochen nach vorn. Zwei waren zu wenig — das
    // Raster endete sichtbar mitten im laufenden Monat und sah aus, als
    // hörten die Daten dort auf.
    //
    // Zwölf und nicht acht, weil daran die Ausrichtung hängt: Die laufende
    // Woche soll bei drei Vierteln der sichtbaren Breite stehen, und dafür
    // muss rechts davon ein Viertel Zukunft liegen. Bei acht Wochen reichte
    // das auf einem schmalen Fenster nicht, die Scrollposition schlug am
    // Ende an und heute klebte am rechten Rand. Nachgemessen: bei 676 px
    // sichtbarer Breite ist die Position mit zwölf Wochen frei (168 von
    // 232), mit acht sitzt sie am Anschlag.
    if (!endDate) return 12
    const end = parseTag(endDate)
    if (end < today) return 0
    const dayOfWeek = today.getDay() === 0 ? 6 : today.getDay() - 1
    const thisWeekMonday = new Date(today)
    thisWeekMonday.setDate(today.getDate() - dayOfWeek)
    const diffDays = Math.ceil((end - thisWeekMonday) / 86400000)
    return Math.max(0, Math.ceil(diffDays / 7))
  }, [weeksForward, endDate])

  // So weit zurück, wie Messungen vorliegen — mindestens aber `weeksBack`.
  // Vorher war das Raster bei 14 Wochen abgeschnitten, und alles davor war
  // nicht erreichbar, obwohl die Daten da sind.
  const computedBack = useMemo(() => {
    if (!data?.length) return weeksBack
    const aeltestes = data.reduce(
      (min, d) => (d.measured_at && d.measured_at < min ? d.measured_at : min),
      data[0]?.measured_at || ''
    )
    const start = parseTag(aeltestes?.slice(0, 10))
    if (!start) return weeksBack
    const heute = new Date()
    heute.setHours(0, 0, 0, 0)
    const wochen = Math.ceil((heute - start) / (7 * 86400000)) + 1
    return Math.max(weeksBack, wochen)
  }, [data, weeksBack])

  const columns = useMemo(
    () => buildGrid(data || [], computedBack, computedForward),
    [data, computedBack, computedForward]
  )

  // Beim Öffnen so scrollen, dass die laufende Woche bei drei Vierteln der
  // sichtbaren Breite steht: rechts bleibt ein Stück Zukunft sichtbar, und
  // nach links lässt sich die Vergangenheit heranziehen. Ganz rechts
  // angeschlagen wäre die Zukunft weg, ganz links die Gegenwart.
  const scrollBox = useRef(null)
  const heuteSpalte = useRef(null)
  useLayoutEffect(() => {
    const box = scrollBox.current
    const ziel = heuteSpalte.current
    if (!box || !ziel) return
    const mitte = ziel.offsetLeft + ziel.offsetWidth / 2
    const gewuenscht = mitte - box.clientWidth * 0.75
    box.scrollLeft = Math.max(0, Math.min(gewuenscht, box.scrollWidth - box.clientWidth))
  }, [columns])

  if (!data?.length) {
    return (
      <div className="text-center py-6 text-sm font-mono" style={{ color: 'var(--text-secondary)' }}>
        No HRV data yet.
      </div>
    )
  }

  const totalDays = data.length
  const greenDays = data.filter(d => d.hrv_status === 'green').length
  const greenPct = Math.round((greenDays / totalDays) * 100)

  return (
    <div className="space-y-3">
      <div className="flex gap-2 items-start">
        {/* Wochentage bleiben stehen — sie gehören zu jeder Spalte gleichermassen
            und wären beim Scrollen als erstes aus dem Bild gewandert. */}
        <div className="flex flex-col gap-1 pt-5 font-mono shrink-0" style={{ color: 'var(--text-muted)' }}>
          {DAY_LABELS.map((d, i) => (
            <div key={i} className="h-3.5 flex items-center" style={{ fontSize: '9px', lineHeight: 1 }}>
              {d}
            </div>
          ))}
        </div>

        {/* Nur das Raster scrollt. `overscroll-x-contain` verhindert, dass ein
            Wisch über das Ende hinaus die ganze Seite mitzieht oder im
            Browser eine Zurück-Navigation auslöst. */}
        <div
          ref={scrollBox}
          className="overflow-x-auto overscroll-x-contain pb-1 min-w-0 flex-1"
          style={{ scrollbarWidth: 'thin' }}
          role="group"
          aria-label="HRV-Verlauf, waagerecht scrollbar"
          tabIndex={0}
        >
          <div className="inline-block">
            {/* Month labels */}
            <div className="flex gap-1 mb-1 font-mono" style={{ color: 'var(--text-muted)' }}>
              {columns.map((c, i) => (
                <div key={i} className="w-[18px] text-center" style={{ fontSize: '9px' }}>
                  {c.monthLabel}
                </div>
              ))}
            </div>

            {/* Cells */}
            <div className="flex gap-1">
              {columns.map((col, ci) => (
                <div
                  key={ci}
                  ref={col.istDieseWoche ? heuteSpalte : null}
                  className="flex flex-col gap-1"
                >
                  {col.days.map((day, di) => (
                    <Cell
                      key={di}
                      day={day}
                      onHover={setHover}
                      isActive={hover && day && hover.date === day.date}
                    />
                  ))}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Hover details — fixed height to prevent layout shift */}
      <div className="text-xs font-mono h-5 px-1 flex items-center" style={{ color: 'var(--text-secondary)' }}>
        {hover ? (
          hover.rmssd != null ? (
            <span className="flex items-center gap-2">
              <span style={{ color: '#e8eaf0' }}>{hover.date}</span>
              <span style={{ color: 'var(--text-muted)' }}>·</span>
              <span style={{ color: '#00d4ff' }} className="font-semibold">{hover.rmssd} ms</span>
              {hover.readiness_score != null && (
                <>
                  <span style={{ color: 'var(--text-muted)' }}>·</span>
                  <span>Body Battery <span style={{ color: '#e8eaf0' }}>{hover.readiness_score}</span></span>
                </>
              )}
              <span style={{ color: 'var(--text-muted)' }}>·</span>
              <span style={{ color: STATUS_COLOR[hover.hrv_status] }} className="uppercase tracking-wider">
                {STATUS_LABEL[hover.hrv_status]}
              </span>
            </span>
          ) : (
            <span>
              <span style={{ color: '#e8eaf0' }}>{hover.date}</span>
              <span className="mx-2" style={{ color: 'var(--text-muted)' }}>·</span>
              <span style={{ color: 'var(--text-muted)' }}>
                {hover.future ? 'Upcoming' : hover.today ? 'Today — no entry yet' : 'No measurement'}
              </span>
            </span>
          )
        ) : (
          <span style={{ color: 'var(--text-muted)' }}>
            {totalDays} measurements · {greenPct}% green days
          </span>
        )}
      </div>

      {/* Legend */}
      <div className="flex gap-2 items-center text-xs font-mono pt-1" style={{ color: 'var(--text-muted)' }}>
        <span style={{ fontSize: '10px' }}>STATUS</span>
        <span className="w-3 h-3 rounded-sm ml-1" style={{ background: '#1a1d24' }} title="No data" />
        <span className="w-3 h-3 rounded-sm" style={{ background: '#ef4444' }} title="Rest" />
        <span className="w-3 h-3 rounded-sm" style={{ background: '#eab308' }} title="Caution" />
        <span className="w-3 h-3 rounded-sm" style={{ background: '#22c55e' }} title="Good" />
      </div>
    </div>
  )
}
