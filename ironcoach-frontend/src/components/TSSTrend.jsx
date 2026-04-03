import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'

export default function TSSTrend({ data }) {
  if (!data?.length) return <div className="text-gray-500 text-sm py-4">Noch keine Daten.</div>

  const chartData = data.map(d => ({
    week: `KW${d.week_number}`,
    TSS: d.total_tss,
    Einheiten: d.sessions_count,
  }))

  return (
    <ResponsiveContainer width="100%" height={180}>
      <LineChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
        <XAxis dataKey="week" tick={{ fill: '#9ca3af', fontSize: 12 }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fill: '#6b7280', fontSize: 11 }} axisLine={false} tickLine={false} />
        <Tooltip
          contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
          labelStyle={{ color: '#d1d5db' }}
        />
        <Line type="monotone" dataKey="TSS" stroke="#0ea5e9" strokeWidth={2} dot={{ fill: '#0ea5e9', r: 4 }} />
      </LineChart>
    </ResponsiveContainer>
  )
}
