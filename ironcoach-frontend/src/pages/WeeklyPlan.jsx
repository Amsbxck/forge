import { useEffect, useState } from 'react'
import { getCurrentPlan, generatePlan } from '../services/api'
import WeekCalendar from '../components/WeekCalendar'
import PlanExport from '../components/PlanExport'

const CARD = 'bg-[#111318] border border-[#1e2228] rounded-xl'
const LABEL = 'text-xs font-mono tracking-widest text-[#8a909e]'

export default function WeeklyPlan() {
  const [plan, setPlan] = useState(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [requests, setRequests] = useState('')
  const [error, setError] = useState(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const resp = await getCurrentPlan()
      setPlan(resp.data)
    } catch (e) {
      if (e.response?.status !== 404) setError('Failed to load plan')
    } finally {
      setLoading(false)
    }
  }

  const generate = async () => {
    setGenerating(true)
    setError(null)
    try {
      const resp = await generatePlan(requests)
      setPlan(resp.data)
    } catch (e) {
      setError(e.response?.data?.detail || 'Generation failed')
    } finally {
      setGenerating(false)
    }
  }

  useEffect(() => { load() }, [])

  return (
    <div className="space-y-6 page-enter">

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-baseline gap-3">
          <h1
            className="text-3xl font-black tracking-tight text-[#e8eaf0]"
            style={{ fontFamily: 'Barlow Condensed, sans-serif' }}
          >
            WEEKLY PLAN
          </h1>
          {plan && (
            <span className="text-lg font-mono text-[#3a3f4a]">WK {plan.week_number}</span>
          )}
        </div>

        <div className="flex gap-2 items-center flex-wrap">
          <input
            value={requests}
            onChange={e => setRequests(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !generating && generate()}
            placeholder="Special requests (optional)"
            className="rounded-lg px-3 py-2 text-sm font-mono text-[#e8eaf0] placeholder-[#3a3f4a] outline-none transition-colors w-64"
            style={{
              background: '#111318',
              border: '1px solid #1e2228',
            }}
            onFocus={e => { e.target.style.borderColor = '#00d4ff44' }}
            onBlur={e => { e.target.style.borderColor = '#1e2228' }}
          />
          <button
            onClick={generate}
            disabled={generating}
            className="relative px-4 py-2 rounded-lg text-sm font-mono font-bold tracking-wide transition-all disabled:opacity-40"
            style={{
              background: generating ? '#00d4ff15' : '#00d4ff20',
              border: '1px solid #00d4ff44',
              color: '#00d4ff',
            }}
            onMouseEnter={e => { if (!generating) e.currentTarget.style.background = '#00d4ff30' }}
            onMouseLeave={e => { e.currentTarget.style.background = generating ? '#00d4ff15' : '#00d4ff20' }}
          >
            {generating ? (
              <span className="flex items-center gap-2">
                <span className="inline-flex gap-0.5">
                  {[0, 1, 2].map(i => (
                    <span
                      key={i}
                      className="w-1 h-1 rounded-full bg-[#00d4ff]"
                      style={{ animation: `pulse 1.2s ease-in-out ${i * 0.2}s infinite` }}
                    />
                  ))}
                </span>
                GENERATING
              </span>
            ) : 'GENERATE PLAN'}
          </button>
          {plan && <PlanExport plan={plan} />}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-xl p-4 font-mono text-sm" style={{ background: '#ef444415', border: '1px solid #ef444430', color: '#ef4444' }}>
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="text-[#8a909e] font-mono text-sm py-8 text-center tracking-widest">
          LOADING...
        </div>
      )}

      {/* Empty state */}
      {!loading && !plan && !error && (
        <div className={`${CARD} p-10 text-center`}>
          <div
            className="text-2xl font-black text-[#3a3f4a] mb-2"
            style={{ fontFamily: 'Barlow Condensed, sans-serif' }}
          >
            NO PLAN YET
          </div>
          <p className="text-sm font-mono text-[#3a3f4a]">
            Click Generate Plan to create your weekly training schedule.
          </p>
        </div>
      )}

      {/* Plan */}
      {plan && (
        <div className="space-y-5">

          {/* Coaching brief card */}
          <div
            className="rounded-xl p-5 relative overflow-hidden"
            style={{ background: '#111318', border: '1px solid #1e2228', borderLeft: '3px solid #00d4ff' }}
          >
            {/* Single diagonal light beam */}
            <div
              className="absolute pointer-events-none"
              style={{
                top: '-60px', left: '-60px',
                width: '220px', height: '220px',
                background: 'linear-gradient(135deg, #00d4ff0e 0%, transparent 55%)',
                transform: 'rotate(-10deg)',
              }}
            />
            <div className="relative z-10">
              <div className="flex flex-wrap gap-4 mb-3">
                <div>
                  <div className={`${LABEL} mb-0.5`}>PHASE</div>
                  <div
                    className="text-sm font-bold text-[#e8eaf0]"
                    style={{ fontFamily: 'Barlow Condensed, sans-serif' }}
                  >
                    {plan.plan_phase?.toUpperCase()}
                  </div>
                </div>
                <div>
                  <div className={`${LABEL} mb-0.5`}>PERIOD</div>
                  <div className="text-sm font-mono text-[#8a909e]">
                    {plan.week_start} – {plan.week_end}
                  </div>
                </div>
              </div>

              {plan.plan_content?.coaching_comment && (
                <p className="text-sm text-[#e8eaf0] leading-relaxed">
                  {plan.plan_content.coaching_comment}
                </p>
              )}

              {plan.adjustments_applied?.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {plan.adjustments_applied.map((adj, i) => (
                    <span
                      key={i}
                      className="text-xs font-mono px-2 py-0.5 rounded-full"
                      style={{ background: '#00d4ff15', color: '#00d4ff', border: '1px solid #00d4ff25' }}
                    >
                      {adj}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Calendar */}
          <WeekCalendar days={plan.plan_content?.days || []} />
        </div>
      )}

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 0.3; transform: scale(0.8); }
          50% { opacity: 1; transform: scale(1); }
        }
      `}</style>
    </div>
  )
}
