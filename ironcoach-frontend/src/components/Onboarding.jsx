import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getOnboardingStatus } from '../services/api'

const DISPLAY = { fontFamily: 'Barlow Condensed, sans-serif' }

/**
 * Führt neue Athleten bis zum ersten Wochenplan.
 * Verschwindet von selbst, sobald alle Schritte erledigt sind — eine
 * dauerhafte Checkliste wäre für Bestandsnutzer nur im Weg.
 */
export default function Onboarding({ warten = false }) {
  const [state, setState] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    // Solange das Willkommensfenster offen ist, wird nicht geladen: Der
    // Athlet kann die Liste ohnehin nicht bedienen, und sie erschiene
    // hinter dem Dialog abrupt, sobald die Antwort da ist.
    if (warten) return
    getOnboardingStatus().then(({ data }) => setState(data)).catch(() => setState(null))
  }, [warten])

  if (warten || !state || state.complete) return null

  const doneCount = state.steps.filter(s => s.done).length
  const progress = Math.round((doneCount / state.steps.length) * 100)

  return (
    <div
      className="rounded-xl p-5 relative overflow-hidden"
      style={{ background: '#111318', border: '1px solid #1e2228', borderLeft: '3px solid #00d4ff' }}
    >
      <div className="absolute pointer-events-none" style={{
        top: '-70px', left: '-50px', width: '280px', height: '240px',
        background: 'linear-gradient(135deg, #00d4ff12 0%, transparent 60%)', transform: 'rotate(-10deg)',
      }} />

      <div className="relative z-10">
        <div className="flex items-baseline justify-between gap-3 flex-wrap">
          <h2 className="text-xl font-black tracking-tight text-[#e8eaf0]" style={DISPLAY}>
            ERSTE SCHRITTE
          </h2>
          <span className="text-xs font-mono text-[var(--text-secondary)] tabular-nums">
            {doneCount} / {state.steps.length}
          </span>
        </div>

        {/* Fortschritt als dünner Balken — kein Prozentwert im Vordergrund */}
        <div className="h-1 rounded-full mt-2 mb-4" style={{ background: '#0d0f17' }}>
          <div className="h-full rounded-full transition-all"
               style={{ width: `${progress}%`, background: '#00d4ff' }} />
        </div>

        <ol className="space-y-2">
          {state.steps.map(step => {
            const isNext = step.key === state.next
            return (
              <li
                key={step.key}
                className="flex items-start gap-3 rounded-lg px-2.5 py-2"
                style={{
                  background: isNext ? '#00d4ff0d' : 'transparent',
                  border: isNext ? '1px solid #00d4ff26' : '1px solid transparent',
                }}
              >
                <span
                  className="flex-shrink-0 w-4 text-center text-xs font-mono leading-5"
                  style={{ color: step.done ? '#22c55e' : (isNext ? '#00d4ff' : '#3a3f4a') }}
                >
                  {step.done ? '✓' : '·'}
                </span>

                <div className="min-w-0 flex-1">
                  <div className="text-sm" style={{ color: step.done ? 'var(--text-secondary)' : 'var(--text-primary)' }}>
                    {step.label}
                    {step.detail && (
                      <span className="text-xs font-mono text-[var(--text-muted)] ml-2">{step.detail}</span>
                    )}
                  </div>
                  {isNext && step.hint && (
                    <div className="text-[11px] font-mono text-[var(--text-secondary)] mt-0.5 leading-relaxed">
                      {step.hint}
                    </div>
                  )}
                </div>

                {isNext && step.action && (
                  <button
                    onClick={() => navigate(step.action)}
                    className="flex-shrink-0 px-2.5 py-1 rounded-lg text-[11px] font-mono tracking-wide"
                    style={{ background: '#00d4ff20', border: '1px solid #00d4ff44', color: '#00d4ff' }}
                  >
                    WEITER
                  </button>
                )}
              </li>
            )
          })}
        </ol>
      </div>
    </div>
  )
}
