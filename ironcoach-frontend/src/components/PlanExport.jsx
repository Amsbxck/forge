import { useState } from 'react'
import { downloadPlanPDF } from '../services/api'

export default function PlanExport({ plan }) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const exportPdf = async () => {
    if (!plan?.week_number) return
    setLoading(true)
    setError(null)
    try {
      const res = await downloadPlanPDF(plan.week_number)
      const blob = new Blob([res.data], { type: 'application/pdf' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `IronCoach_Woche_${plan.week_number}.pdf`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error('PDF-Export fehlgeschlagen', err)
      setError('Export fehlgeschlagen')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={exportPdf}
        disabled={loading}
        className="text-sm bg-purple-700 hover:bg-purple-600 disabled:opacity-50 px-3 py-1.5 rounded-lg text-white transition-colors font-medium"
      >
        {loading ? 'Exportiere...' : 'PDF Export'}
      </button>
      {error && <span className="text-xs text-red-400">{error}</span>}
    </div>
  )
}
