import { useEffect, useRef, useState } from 'react'
import Modal from './Modal'
import { DISCIPLINE_COLOR, DISCIPLINE_LABEL } from '../utils/colors'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import HRZoneChart from './HRZoneChart'
import ReflectionEditor from './ReflectionEditor'

const LABEL = 'text-xs font-mono tracking-widest text-[var(--text-secondary)]'

function Stat({ label, value, color }) {
  return (
    <div className="rounded-xl p-3" style={{ background: '#0d0f17', border: '1px solid #1e2228' }}>
      <div className={`${LABEL} mb-1`}>{label}</div>
      <div className="font-bold text-sm font-mono" style={{ color: color || '#e8eaf0' }}>{value}</div>
    </div>
  )
}

const CHART_STYLE = {
  contentStyle: { background: '#111318', border: '1px solid #1e2228', borderRadius: 8, fontSize: 11, fontFamily: 'JetBrains Mono, monospace' },
  tickStyle: { fill: '#79808f', fontSize: 10, fontFamily: 'JetBrains Mono, monospace' },
  gridStroke: '#1e2228',
}

function SectionTitle({ children }) {
  return (
    <div className="text-xs font-mono tracking-widest text-[var(--text-secondary)] mb-3 flex items-center gap-2">
      <div className="w-3 h-px bg-[#3a3f4a]" />
      {children}
    </div>
  )
}

export default function SessionDetail({ session: s, onClose }) {
  const scrollRef = useRef(null)
  const streams = s.streams || {}

  const hrData = (streams.hr || []).map((v, i) => ({ t: i * 10, hr: v }))
  const wattsData = (streams.watts || []).map((v, i) => ({ t: i * 10, watt: v }))
  const paceData = (streams.pace || []).map((v, i) => ({ t: i * 10, pace: v }))
  const speedData = (streams.speed || []).map((v, i) => ({ t: i * 10, speed: v }))
  const swimInfo = streams.swim_info || null

  // Scroll to top on open + lock body scroll
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: 0 })
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = prev }
  }, [])

  const formatTime = (sec) => {
    const m = Math.floor(sec / 60)
    const s2 = sec % 60
    return `${m}:${String(s2).padStart(2, '0')}`
  }

  const DISC = Object.fromEntries(
    Object.entries(DISCIPLINE_LABEL).map(([k, label]) => [
      k, { label: label.toUpperCase(), color: DISCIPLINE_COLOR[k] },
    ])
  )
  const disc = DISC[s.discipline?.toLowerCase()] || { label: s.discipline?.toUpperCase(), color: 'var(--text-secondary)' }

  // Eigener Rahmen ersetzt durch den gemeinsamen Dialog: das alte Overlag lag
  // ohne Portal unter der Seiteneinblendung und deckte nicht die ganze Seite.
  return (
    <Modal open onClose={onClose} width="max-w-5xl" align="top">
      <div ref={scrollRef} className="space-y-5">
        {/* Header */}
        <div className="flex justify-between items-start">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <span
                className="text-2xl font-black tracking-wide"
                style={{ fontFamily: 'Barlow Condensed, sans-serif', color: disc.color }}
              >
                {disc.label}
              </span>
              <span className="text-xs font-mono text-[var(--text-muted)]">{s.session_date}</span>
            </div>
            <div className="flex gap-3 text-xs font-mono text-[var(--text-secondary)]">
              {s.duration_min && <span>{s.duration_min} min</span>}
              {s.distance_km && <span>{s.distance_km} km</span>}
              {s.tss && <span style={{ color: disc.color }}>{s.tss.toFixed ? s.tss.toFixed(0) : s.tss} TSS</span>}
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-[var(--text-muted)] hover:text-[#e8eaf0] transition-colors font-mono text-xl leading-none w-8 h-8 flex items-center justify-center rounded-lg"
            style={{ border: '1px solid #1e2228' }}
          >
            ×
          </button>
        </div>

        {/* Stats grid */}
        <div className="grid grid-cols-3 gap-2">
          {s.avg_hr && <Stat label="AVG HR" value={`${s.avg_hr} bpm`} />}
          {s.max_hr && <Stat label="MAX HR" value={`${s.max_hr} bpm`} color="#ef4444" />}
          {s.avg_watts && <Stat label="AVG POWER" value={`${s.avg_watts}W`} color="#a855f7" />}
          {s.normalized_power && <Stat label="NP" value={`${s.normalized_power}W`} color="#a855f7" />}
          {s.avg_pace_min_km && <Stat label="PACE" value={`${s.avg_pace_min_km.toFixed(2)} /km`} />}
          {s.tss && <Stat label="TSS" value={s.tss.toFixed ? s.tss.toFixed(0) : s.tss} color="#00d4ff" />}
        </div>

        {/* Swim stats */}
        {swimInfo && (
          <div>
            <SectionTitle>SWIM DETAILS</SectionTitle>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {swimInfo.pool_length_m && <Stat label="POOL LENGTH" value={`${swimInfo.pool_length_m}m`} />}
              {swimInfo.num_lengths && <Stat label="LENGTHS" value={swimInfo.num_lengths} />}
              {swimInfo.pure_swim_sec && <Stat label="SWIM TIME" value={`${Math.floor(swimInfo.pure_swim_sec / 60)}:${String(swimInfo.pure_swim_sec % 60).padStart(2, '0')}`} />}
              {swimInfo.pace_per_100m && <Stat label="PACE /100m" value={`${swimInfo.pace_per_100m.toFixed(2)} min`} />}
              {swimInfo.avg_swolf && <Stat label="SWOLF" value={swimInfo.avg_swolf} />}
            </div>
          </div>
        )}

        {/* HR chart */}
        {hrData.length > 0 && (
          <div>
            <SectionTitle>HEART RATE</SectionTitle>
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={hrData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={CHART_STYLE.gridStroke} vertical={false} />
                <XAxis dataKey="t" tickFormatter={formatTime} tick={CHART_STYLE.tickStyle} axisLine={false} tickLine={false} />
                <YAxis domain={['auto', 'auto']} tick={CHART_STYLE.tickStyle} axisLine={false} tickLine={false} unit=" bpm" />
                <Tooltip formatter={(v) => [`${v} bpm`, 'HR']} labelFormatter={formatTime} contentStyle={CHART_STYLE.contentStyle} />
                <Line type="monotone" dataKey="hr" stroke="#ef4444" strokeWidth={1.5} dot={false} activeDot={{ r: 3, fill: '#ef4444' }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Power chart */}
        {wattsData.length > 0 && (
          <div>
            <SectionTitle>POWER</SectionTitle>
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={wattsData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={CHART_STYLE.gridStroke} vertical={false} />
                <XAxis dataKey="t" tickFormatter={formatTime} tick={CHART_STYLE.tickStyle} axisLine={false} tickLine={false} />
                <YAxis domain={['auto', 'auto']} tick={CHART_STYLE.tickStyle} axisLine={false} tickLine={false} unit="W" />
                <Tooltip formatter={(v) => [`${v}W`, 'Power']} labelFormatter={formatTime} contentStyle={CHART_STYLE.contentStyle} />
                <Line type="monotone" dataKey="watt" stroke="#a855f7" strokeWidth={1.5} dot={false} activeDot={{ r: 3, fill: '#a855f7' }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Pace chart */}
        {paceData.length > 0 && (
          <div>
            <SectionTitle>PACE</SectionTitle>
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={paceData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={CHART_STYLE.gridStroke} vertical={false} />
                <XAxis dataKey="t" tickFormatter={formatTime} tick={CHART_STYLE.tickStyle} axisLine={false} tickLine={false} />
                <YAxis reversed domain={['auto', 'auto']} tick={CHART_STYLE.tickStyle} axisLine={false} tickLine={false} unit=" /km" />
                <Tooltip formatter={(v) => [`${v} min/km`, 'Pace']} labelFormatter={formatTime} contentStyle={CHART_STYLE.contentStyle} />
                <Line type="monotone" dataKey="pace" stroke="#22c55e" strokeWidth={1.5} dot={false} activeDot={{ r: 3, fill: '#22c55e' }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Speed chart */}
        {speedData.length > 0 && (
          <div>
            <SectionTitle>SPEED</SectionTitle>
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={speedData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={CHART_STYLE.gridStroke} vertical={false} />
                <XAxis dataKey="t" tickFormatter={formatTime} tick={CHART_STYLE.tickStyle} axisLine={false} tickLine={false} />
                <YAxis domain={['auto', 'auto']} tick={CHART_STYLE.tickStyle} axisLine={false} tickLine={false} unit=" km/h" />
                <Tooltip formatter={(v) => [`${v} km/h`, 'Speed']} labelFormatter={formatTime} contentStyle={CHART_STYLE.contentStyle} />
                <Line type="monotone" dataKey="speed" stroke="#00d4ff" strokeWidth={1.5} dot={false} activeDot={{ r: 3, fill: '#00d4ff' }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        <div>
          <SectionTitle>REFLEXION</SectionTitle>
          <ReflectionEditor session={s} />
        </div>

        {/* HR zones */}
        {s.hr_zones && (
          <div>
            <SectionTitle>HR ZONES</SectionTitle>
            <HRZoneChart zones={s.hr_zones} />
          </div>
        )}

        {!hrData.length && !wattsData.length && !paceData.length && !speedData.length && !s.hr_zones && (
          <p className="text-[var(--text-muted)] text-xs font-mono text-center py-4">
            No time-series data available (FIT uploads only).
          </p>
        )}
      </div>
    </Modal>
  )
}
