import { downloadPlanPDF } from '../services/api'

export default function PlanExport({ plan }) {
  const exportPdf = async () => {
    if (!plan?.week_number) return
    try {
      const res = await downloadPlanPDF(plan.week_number)
      const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }))
      const a = document.createElement('a')
      a.href = url
      a.download = `IronCoach_Woche_${plan.week_number}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error('PDF-Export fehlgeschlagen', err)
    }
  }

  return (
    <button
      onClick={exportPdf}
      className="text-sm bg-purple-700 hover:bg-purple-600 px-3 py-1.5 rounded-lg text-white transition-colors font-medium"
    >
      PDF Export
    </button>
  )
}
