import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import HRZoneChart from './HRZoneChart'

export default function SessionDetail({ session: s, onClose }) {
  const streams = s.streams || {}

  const hrData = (streams.hr || []).map((v, i) => ({ t: i * 10, hr: v }))
  const wattsData = (streams.watts || []).map((v, i) => ({ t: i * 10, watt: v }))
  const paceData = (streams.pace || []).map((v, i) => ({ t: i * 10, pace: v }))
  const speedData = (streams.speed || []).map((v, i) => ({ t: i * 10, speed: v }))
  const swimInfo = streams.swim_info || null

  const formatTime = (sec) => {
    const m = Math.floor(sec / 60)
    const s2 = sec % 60
    return `${m}:${String(s2).padStart(2, '0')}`
  }

  return (
    <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-gray-900 rounded-2xl w-full max-w-3xl max-h-[90vh] overflow-y-auto p-6 space-y-6"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex justify-between items-start">
          <div>
            <h2 className="text-xl font-bold capitalize">{s.discipline} — {s.session_date}</h2>
            <div className="flex gap-4 text-sm text-gray-400 mt-1">
              {s.duration_min && <span>{s.duration_min} min</span>}
              {s.distance_km && <span>{s.distance_km} km</span>}
              {s.tss && <span>TSS {s.tss}</span>}
            </div>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-200 text-2xl leading-none">×</button>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-3">
          {s.avg_hr && <Stat label="Ø HR" value={`${s.avg_hr} bpm`} />}
          {s.max_hr && <Stat label="Max HR" value={`${s.max_hr} bpm`} />}
          {s.avg_watts && <Stat label="Ø Watt" value={`${s.avg_watts}W`} />}
          {s.normalized_power && <Stat label="NP" value={`${s.normalized_power}W`} />}
          {s.avg_pace_min_km && <Stat label="Pace" value={`${s.avg_pace_min_km.toFixed(2)} min/km`} />}
        </div>

        {/* Swim Stats */}
        {swimInfo && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {swimInfo.pool_length_m && <Stat label="Bahnlänge" value={`${swimInfo.pool_length_m}m`} />}
            {swimInfo.num_lengths && <Stat label="Bahnen" value={swimInfo.num_lengths} />}
            {swimInfo.pure_swim_sec && <Stat label="Reine Schwimmzeit" value={`${Math.floor(swimInfo.pure_swim_sec / 60)}:${String(swimInfo.pure_swim_sec % 60).padStart(2, '0')} min`} />}
            {swimInfo.pace_per_100m && <Stat label="Pace (ohne Pausen)" value={`${swimInfo.pace_per_100m.toFixed(2)} min/100m`} />}
            {swimInfo.avg_swolf && <Stat label="SWOLF" value={swimInfo.avg_swolf} />}
          </div>
        )}

        {/* HR Verlauf */}
        {hrData.length > 0 && (
          <div>
            <h3 className="font-semibold mb-3 text-sm text-gray-300">Herzfrequenz Verlauf</h3>
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={hrData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis dataKey="t" tickFormatter={formatTime} tick={{ fill: '#6b7280', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis domain={['auto', 'auto']} tick={{ fill: '#6b7280', fontSize: 11 }} axisLine={false} tickLine={false} unit=" bpm" />
                <Tooltip formatter={(v) => [`${v} bpm`, 'HR']} labelFormatter={(v) => formatTime(v)} contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8 }} />
                <Line type="monotone" dataKey="hr" stroke="#ef4444" strokeWidth={1.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Watt Verlauf */}
        {wattsData.length > 0 && (
          <div>
            <h3 className="font-semibold mb-3 text-sm text-gray-300">Leistung Verlauf</h3>
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={wattsData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis dataKey="t" tickFormatter={formatTime} tick={{ fill: '#6b7280', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis domain={['auto', 'auto']} tick={{ fill: '#6b7280', fontSize: 11 }} axisLine={false} tickLine={false} unit="W" />
                <Tooltip formatter={(v) => [`${v}W`, 'Leistung']} labelFormatter={(v) => formatTime(v)} contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8 }} />
                <Line type="monotone" dataKey="watt" stroke="#0ea5e9" strokeWidth={1.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Pace Verlauf */}
        {paceData.length > 0 && (
          <div>
            <h3 className="font-semibold mb-3 text-sm text-gray-300">Pace Verlauf</h3>
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={paceData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis dataKey="t" tickFormatter={formatTime} tick={{ fill: '#6b7280', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis reversed domain={['auto', 'auto']} tick={{ fill: '#6b7280', fontSize: 11 }} axisLine={false} tickLine={false} unit=" min/km" />
                <Tooltip formatter={(v) => [`${v} min/km`, 'Pace']} labelFormatter={(v) => formatTime(v)} contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8 }} />
                <Line type="monotone" dataKey="pace" stroke="#22c55e" strokeWidth={1.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* HR Zonen groß */}
        {s.hr_zones && (
          <div>
            <h3 className="font-semibold mb-3 text-sm text-gray-300">HR-Zonen</h3>
            <HRZoneChart zones={s.hr_zones} />
          </div>
        )}

        {/* Speed Verlauf (Bike) */}
        {speedData.length > 0 && (
          <div>
            <h3 className="font-semibold mb-3 text-sm text-gray-300">Geschwindigkeit Verlauf</h3>
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={speedData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis dataKey="t" tickFormatter={formatTime} tick={{ fill: '#6b7280', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis domain={['auto', 'auto']} tick={{ fill: '#6b7280', fontSize: 11 }} axisLine={false} tickLine={false} unit=" km/h" />
                <Tooltip formatter={(v) => [`${v} km/h`, 'Speed']} labelFormatter={(v) => formatTime(v)} contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8, color: '#d1d5db' }} itemStyle={{ color: '#d1d5db' }} />
                <Line type="monotone" dataKey="speed" stroke="#a78bfa" strokeWidth={1.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {!hrData.length && !wattsData.length && !paceData.length && !speedData.length && !s.hr_zones && (
          <p className="text-gray-500 text-sm text-center py-4">Keine Zeitreihendaten vorhanden (nur für FIT-Uploads verfügbar).</p>
        )}
      </div>
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div className="bg-gray-800 rounded-xl p-3">
      <div className="text-xs text-gray-500 mb-0.5">{label}</div>
      <div className="font-semibold">{value}</div>
    </div>
  )
}
