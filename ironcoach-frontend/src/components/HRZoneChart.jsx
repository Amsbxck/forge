import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'

import { HR_ZONE_COLOR as COLORS } from '../utils/colors'
const LABELS = { z1: 'Z1', z2: 'Z2', z3: 'Z3', z4: 'Z4', z5: 'Z5' }

export default function HRZoneChart({ zones }) {
  const data = Object.entries(zones).map(([key, value], i) => ({
    name: LABELS[key] || key,
    value,
    color: COLORS[i] || '#6b7280',
  }))

  return (
    <ResponsiveContainer width="100%" height={160}>
      <BarChart data={data} barSize={32}>
        <XAxis dataKey="name" tick={{ fill: '#9ca3af', fontSize: 12 }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fill: '#6b7280', fontSize: 11 }} axisLine={false} tickLine={false} unit="%" domain={[0, 100]} />
        <Tooltip
          formatter={(v) => [`${v}%`, 'Zeit']}
          contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8, color: '#d1d5db' }}
          labelStyle={{ color: '#d1d5db' }}
          itemStyle={{ color: '#d1d5db' }}
          cursor={{ fill: 'rgba(255,255,255,0.05)' }}
        />
        <Bar dataKey="value" radius={[4, 4, 0, 0]}>
          {data.map((entry, i) => <Cell key={i} fill={entry.color} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
