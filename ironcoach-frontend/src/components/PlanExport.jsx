import { useState } from 'react'
import { downloadPlanPdfByMonday } from '../services/api'
import { fehlerText } from '../utils/fehler'

/** PDF des angezeigten Wochenplans — angesprochen über den Montag.
 *
 *  Vorher über die Wochennummer: Woche 0 ließ sich gar nicht exportieren
 *  (`!plan.week_number` war wahr), und nach einem Zielwechsel kam das PDF
 *  einer anderen Kalenderwoche mit derselben Nummer.
 */
export default function PlanExport({ plan }) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const exportPdf = async () => {
    if (!plan?.week_start) return
    setLoading(true)
    setError(null)
    try {
      const res = await downloadPlanPdfByMonday(plan.week_start)
      const blob = new Blob([res.data], { type: 'application/pdf' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `FORGE_${plan.week_start}.pdf`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(fehlerText(err, 'Export fehlgeschlagen'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={exportPdf}
        disabled={loading}
        className="text-[10px] font-mono font-semibold tracking-widest px-3 py-1.5 rounded-lg transition-colors hover:brightness-125 disabled:opacity-50"
        style={{ background: 'transparent', border: '1px solid #1e2228', color: '#a7aebd' }}
      >
        {loading ? 'EXPORTING…' : 'PDF EXPORT'}
      </button>
      {error && <span className="text-xs" style={{ color: '#ef4444' }}>{error}</span>}
    </div>
  )
}
