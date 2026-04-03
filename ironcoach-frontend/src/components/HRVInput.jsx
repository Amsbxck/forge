import { useState } from 'react'
import { postHrv } from '../services/api'

export default function HRVInput({ onSaved }) {
  const [open, setOpen] = useState(false)
  const [rmssd, setRmssd] = useState('')
  const [readiness, setReadiness] = useState('')
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10))
  const [saving, setSaving] = useState(false)

  const submit = async () => {
    if (!rmssd) return
    setSaving(true)
    try {
      await postHrv({
        measured_at: date,
        rmssd: parseFloat(rmssd),
        readiness_score: readiness ? parseInt(readiness) : null,
      })
      setOpen(false)
      setRmssd('')
      setReadiness('')
      setDate(new Date().toISOString().slice(0, 10))
      onSaved?.()
    } catch (e) {
      console.error(e)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      {!open ? (
        <button
          onClick={() => setOpen(true)}
          className="text-sm px-3 py-1.5 rounded-lg font-mono transition-colors border border-[#1e2228] text-[#8a909e] hover:text-[#e8eaf0] hover:border-[#3a3f4a]"
          style={{ background: '#111318' }}
        >
          Log HRV
        </button>
      ) : (
        <div className="rounded-xl p-4 space-y-3 min-w-[240px] border border-[#1e2228]" style={{ background: '#111318' }}>
          <div>
            <label className="text-xs text-[#8a909e] block mb-1 font-mono">Date</label>
            <input
              type="date"
              value={date}
              onChange={e => setDate(e.target.value)}
              max={new Date().toISOString().slice(0, 10)}
              className="w-full rounded-lg px-3 py-1.5 text-sm border text-[#e8eaf0] font-mono"
              style={{ background: '#0d0f17', borderColor: '#1e2228' }}
            />
          </div>
          <div>
            <label className="text-xs text-[#8a909e] block mb-1 font-mono">rMSSD (ms)</label>
            <input
              type="number"
              value={rmssd}
              onChange={e => setRmssd(e.target.value)}
              placeholder="e.g. 82"
              className="w-full rounded-lg px-3 py-1.5 text-sm border text-[#e8eaf0] font-mono"
              style={{ background: '#0d0f17', borderColor: '#1e2228' }}
              autoFocus
            />
          </div>
          <div>
            <label className="text-xs text-[#8a909e] block mb-1 font-mono">Body Battery (optional)</label>
            <input
              type="number"
              value={readiness}
              onChange={e => setReadiness(e.target.value)}
              placeholder="0–100"
              className="w-full rounded-lg px-3 py-1.5 text-sm border text-[#e8eaf0] font-mono"
              style={{ background: '#0d0f17', borderColor: '#1e2228' }}
            />
          </div>
          <div className="flex gap-2">
            <button
              onClick={submit}
              disabled={saving || !rmssd}
              className="flex-1 text-white text-sm py-1.5 rounded-lg font-mono transition-colors disabled:opacity-50"
              style={{ background: saving || !rmssd ? '#1e2228' : '#00d4ff22', border: '1px solid #00d4ff44', color: '#00d4ff' }}
            >
              {saving ? '...' : 'Save'}
            </button>
            <button onClick={() => setOpen(false)} className="text-[#8a909e] hover:text-[#e8eaf0] text-sm px-2 font-mono">✕</button>
          </div>
        </div>
      )}
    </div>
  )
}
