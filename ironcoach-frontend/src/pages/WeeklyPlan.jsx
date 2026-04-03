import { useEffect, useState } from 'react'
import { getCurrentPlan, generatePlan } from '../services/api'
import WeekCalendar from '../components/WeekCalendar'
import PlanExport from '../components/PlanExport'

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
      if (e.response?.status !== 404) setError('Fehler beim Laden des Plans')
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
      setError(e.response?.data?.detail || 'Generierung fehlgeschlagen')
    } finally {
      setGenerating(false)
    }
  }

  useEffect(() => { load() }, [])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-bold">
          Wochenplan {plan ? `Woche ${plan.week_number}` : ''}
        </h1>
        <div className="flex gap-2 items-center flex-wrap">
          <input
            value={requests}
            onChange={e => setRequests(e.target.value)}
            placeholder="Besondere Wünsche (optional)"
            className="bg-gray-800 rounded-lg px-3 py-2 text-sm border border-gray-700 w-64"
          />
          <button
            onClick={generate}
            disabled={generating}
            className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white font-medium px-4 py-2 rounded-lg text-sm transition-colors"
          >
            {generating ? 'Claude denkt...' : 'Neuen Plan generieren'}
          </button>
          {plan && <PlanExport plan={plan} />}
        </div>
      </div>

      {error && <div className="bg-red-900/40 border border-red-700 rounded-xl p-4 text-red-400">{error}</div>}

      {loading && <div className="text-gray-400 py-8 text-center">Lade Plan...</div>}

      {!loading && !plan && !error && (
        <div className="bg-gray-900 rounded-xl p-8 text-center text-gray-400">
          Noch kein Plan vorhanden. Klicke "Neuen Plan generieren".
        </div>
      )}

      {plan && (
        <div className="space-y-4">
          <div className="bg-gray-900 rounded-xl p-5">
            <div className="flex gap-4 text-sm text-gray-400 mb-2">
              <span>Phase: <span className="text-gray-200">{plan.plan_phase}</span></span>
              <span>{plan.week_start} – {plan.week_end}</span>
            </div>
            {plan.plan_content?.coaching_comment && (
              <p className="text-gray-200 leading-relaxed">{plan.plan_content.coaching_comment}</p>
            )}
            {plan.adjustments_applied?.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {plan.adjustments_applied.map((adj, i) => (
                  <span key={i} className="bg-blue-900/40 text-blue-300 text-xs px-2 py-1 rounded-full">{adj}</span>
                ))}
              </div>
            )}
          </div>
          <WeekCalendar days={plan.plan_content?.days || []} />
        </div>
      )}
    </div>
  )
}
