import { useState } from 'react'

const TYPE_COLOR = {
  rest:  { border: '#1e2228', bg: '#111318',     text: '#8a909e' },
  bike:  { border: '#a855f7', bg: '#a855f720',   text: '#a855f7' },
  run:   { border: '#ef4444', bg: '#ef444420',   text: '#ef4444' },
  swim:  { border: '#eab308', bg: '#eab30820',   text: '#eab308' },
  gym:   { border: '#22c55e', bg: '#22c55e20',   text: '#22c55e' },
  brick: { border: '#f97316', bg: '#f9731620',   text: '#f97316' },
}

function getColors(type) {
  return TYPE_COLOR[type?.toLowerCase()] || TYPE_COLOR.rest
}

function BlocksTable({ blocks }) {
  if (!blocks?.length) return null
  return (
    <div className="mt-1 space-y-1">
      {blocks.map((b, i) => {
        const isRest = b.block === 'Erholung'
        const label = b.block ?? `Block ${i + 1}`
        const { block: _, ...rest } = b
        const values = Object.values(rest).filter(Boolean)
        return (
          <div key={i} className={`rounded-lg px-2 py-1 ${isRest ? 'bg-white/5' : 'bg-white/5'}`}>
            <div className="text-[10px] font-semibold uppercase tracking-wide mb-0.5" style={{ color: isRest ? '#3a3f4a' : '#00d4ff' }}>
              {label}
            </div>
            <div className="flex flex-wrap gap-x-2 gap-y-0.5">
              {values.map((v, j) => (
                <span key={j} className="text-[11px] text-[#8a909e]">{v}</span>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function DetailsSection({ details, sessionType }) {
  if (!details || Object.keys(details).length === 0) return null
  return (
    <div className="mt-2 space-y-1">
      {Object.entries(details).map(([k, v]) => {
        if (Array.isArray(v)) {
          return (
            <div key={k}>
              <div className="text-[10px] uppercase text-[#3a3f4a] font-medium mb-0.5">{k}</div>
              <BlocksTable blocks={v} sessionType={sessionType} />
            </div>
          )
        }
        return (
          <div key={k} className="text-xs text-[#8a909e]">
            <span className="text-[#3a3f4a]">{k}:</span> {String(v)}
          </div>
        )
      })}
    </div>
  )
}

const DAY_ORDER = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']

export default function WeekCalendar({ days: initialDays }) {
  const sorted = [...(initialDays || [])].sort(
    (a, b) => DAY_ORDER.indexOf(a.day) - DAY_ORDER.indexOf(b.day)
  )
  const [days, setDays] = useState(sorted)
  const [dragIndex, setDragIndex] = useState(null)
  const [overIndex, setOverIndex] = useState(null)

  if (!days?.length) return null

  const onDragStart = (i) => setDragIndex(i)
  const onDragOver = (e, i) => { e.preventDefault(); setOverIndex(i) }
  const onDrop = (targetIndex) => {
    if (dragIndex === null || dragIndex === targetIndex) {
      setDragIndex(null); setOverIndex(null); return
    }
    const next = [...days]
    // Swap only the session content, keep day name + date
    const fieldsToSwap = ['session_type', 'duration_min', 'notes', 'details']
    fieldsToSwap.forEach(f => {
      const tmp = next[dragIndex][f]
      next[dragIndex] = { ...next[dragIndex], [f]: next[targetIndex][f] }
      next[targetIndex] = { ...next[targetIndex], [f]: tmp }
    })
    setDays(next)
    setDragIndex(null)
    setOverIndex(null)
  }
  const onDragEnd = () => { setDragIndex(null); setOverIndex(null) }

  return (
    <div className="grid grid-cols-1 md:grid-cols-7 gap-3">
      {days.map((day, i) => {
        const colors = getColors(day.session_type)
        const isDragging = dragIndex === i
        const isOver = overIndex === i && dragIndex !== i

        return (
          <div
            key={i}
            draggable
            onDragStart={() => onDragStart(i)}
            onDragOver={(e) => onDragOver(e, i)}
            onDrop={() => onDrop(i)}
            onDragEnd={onDragEnd}
            className="rounded-xl border p-3 transition-all select-none"
            style={{
              borderColor: isOver ? '#00d4ff' : colors.border,
              background: isOver ? '#00d4ff0d' : colors.bg,
              opacity: isDragging ? 0.4 : 1,
              cursor: 'grab',
              boxShadow: isOver ? '0 0 0 1px #00d4ff44' : 'none',
            }}
          >
            {/* Header */}
            <div className="flex justify-between items-start mb-2">
              <span className="font-bold text-sm text-[#e8eaf0]" style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>
                {day.day?.slice(0, 2).toUpperCase()}
              </span>
              <span className="text-[10px] font-mono text-[#3a3f4a]">{day.date?.slice(5)}</span>
            </div>

            {/* Type badge */}
            <div className="text-[10px] font-mono font-bold uppercase tracking-widest mb-1.5" style={{ color: colors.text }}>
              {day.session_type}
            </div>

            {day.duration_min > 0 && (
              <div className="text-xs font-mono text-[#8a909e] mb-1">{day.duration_min} min</div>
            )}
            {day.notes && (
              <p className="text-xs text-[#8a909e] leading-relaxed">{day.notes}</p>
            )}
            <DetailsSection details={day.details} sessionType={day.session_type} />

            {/* Drag hint */}
            <div className="mt-2 text-[9px] font-mono text-[#3a3f4a] text-center opacity-60">⠿ drag</div>
          </div>
        )
      })}
    </div>
  )
}
