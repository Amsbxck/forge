import { useEffect, useRef, useState } from 'react'
import { getSchedulerStatus, syncNow } from '../services/api'

/**
 * Sofort-Abgleich mit Strava — derselbe Ablauf wie der stündliche Job.
 * Zeigt nach dem Lauf, was tatsächlich passiert ist: eine Meldung "fertig"
 * ohne Zahlen ließe offen, ob überhaupt etwas gefunden wurde.
 */
export default function SyncButton() {
  const [state, setState] = useState('idle')   // idle | running | done | error
  const [result, setResult] = useState(null)
  const [nextRun, setNextRun] = useState(null)
  const resetTimer = useRef(null)

  useEffect(() => {
    getSchedulerStatus()
      .then(r => {
        const job = r.data?.jobs?.find(j => j.id === 'reconcile')
        if (r.data?.running && job?.next_run) setNextRun(new Date(job.next_run))
      })
      .catch(() => {})
    return () => clearTimeout(resetTimer.current)
  }, [])

  const run = async () => {
    if (state === 'running') return
    setState('running')
    setResult(null)
    try {
      const { data } = await syncNow()
      setResult(data)
      setState(data.ok ? 'done' : 'error')
      // Neue Einheiten wirken sich auf jede Seite aus — Daten neu laden,
      // aber nur wenn sich wirklich etwas geändert hat.
      if (data.created > 0 || data.linked > 0) {
        setTimeout(() => window.location.reload(), 1400)
      }
    } catch (e) {
      setResult({ error: e.response?.data?.detail || 'Abgleich fehlgeschlagen' })
      setState('error')
    } finally {
      clearTimeout(resetTimer.current)
      resetTimer.current = setTimeout(() => setState(s => (s === 'running' ? s : 'idle')), 8000)
    }
  }

  const label = {
    idle: 'SYNC',
    running: 'SYNCT…',
    done: result?.created || result?.linked
      ? `+${(result.created || 0) + (result.linked || 0)} NEU`
      : 'AKTUELL',
    error: 'FEHLER',
  }[state]

  const color = state === 'error' ? '#ef4444' : (state === 'done' ? '#22c55e' : '#00d4ff')

  const title = state === 'done' && result
    ? `${result.checked} Aktivitäten geprüft · ${result.created} neu · ${result.linked} verknüpft · ${result.obsidian_written} Notes geschrieben`
    : state === 'error'
      ? (result?.error || 'Abgleich fehlgeschlagen')
      : nextRun
        ? `Jetzt mit Strava abgleichen — automatisch wieder um ${nextRun.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })}`
        : 'Jetzt mit Strava abgleichen (automatischer Abgleich ist aus)'

  return (
    <button
      onClick={run}
      disabled={state === 'running'}
      title={title}
      className="ml-auto flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-mono tracking-wide transition-all flex-shrink-0 disabled:cursor-progress"
      style={{ color, background: `${color}12`, border: `1px solid ${color}33` }}
    >
      <span
        className="inline-block leading-none"
        style={{
          animation: state === 'running' ? 'syncSpin 0.9s linear infinite' : 'none',
          transformOrigin: '50% 50%',
        }}
      >
        ⟳
      </span>
      <span className="hidden sm:inline">{label}</span>

      <style>{`
        @keyframes syncSpin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </button>
  )
}
