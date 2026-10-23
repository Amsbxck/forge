import { DONE_COLOR, INTENSITY_META, disciplineColor, disciplineLabel } from '../../utils/colors'
import { isoTag, parseTag } from '../../utils/dates'

/** Die harten Einheiten der Woche — im BREAKDOWN unter der 80/20-Leiste.
 *
 *  Die Leiste darüber zeigt nur den Anteil harter Minuten nach Puls. Ob die
 *  Einheiten, um die die Woche gebaut ist (Sweet Spot, Schwelle, VO₂max),
 *  wirklich stattfanden, sah man nicht: 20 % hart kann auch heißen, dass die
 *  Schwelle ausfiel und ein lockerer Lauf zu flott war. Deshalb hier die
 *  geplanten Schlüsseleinheiten mit ihrem Stand.
 *
 *  Die Intensität kommt vom Backend (`intensity_for_type`, aus Trainingstyp
 *  oder Zielzone), nicht aus einer eigenen Regel. Grundlage zählt nicht, Kraft
 *  hat keine Stufe. Der Platz dafür wurde frei, als FORM aus der rechten
 *  Spalte in die Performance-Kachel wanderte.
 */

export const HART = ['sweet_spot', 'threshold', 'vo2max']
const NAME = { sweet_spot: 'Sweet Spot', threshold: 'Threshold', vo2max: 'VO₂max' }
const STAND = {
  done: { text: 'DONE' },
  heute: { text: 'TODAY' },
  offen: { text: 'OPEN' },
  verpasst: { text: 'MISSED' },
  skipped: { text: 'SKIPPED' },
  replaced: { text: 'REPLACED' },
}

/** Die Schlüsseleinheiten mit Stand, nach Datum.
 *
 *  `done`, wenn sie abgehakt oder verknüpft ist — oder wenn am selben Tag eine
 *  Einheit derselben Sportart stattfand, wie bei den Tagespunkten der
 *  Sportzeilen. Sonst zählt das Datum: heute, noch offen, verpasst.
 */
export function keySessions(geplant, sessions, heute = isoTag(new Date())) {
  const gemacht = new Set((sessions || []).filter(s => !s.deleted_at)
    .map(s => `${s.session_date?.slice(0, 10)}|${(s.discipline || '').toLowerCase()}`))
  return (geplant || [])
    .filter(p => HART.includes(p.intensity))
    .map(p => {
      let stand
      if (p.status === 'skipped' || p.status === 'replaced') stand = p.status
      else if (p.status === 'completed' || p.matched_session_id
        || gemacht.has(`${p.planned_date}|${(p.discipline || '').toLowerCase()}`)) stand = 'done'
      else if (p.planned_date === heute) stand = 'heute'
      else stand = p.planned_date > heute ? 'offen' : 'verpasst'
      return { ...p, stand }
    })
    .sort((a, b) => a.planned_date.localeCompare(b.planned_date))
}

function Marke({ stand, farbe }) {
  if (stand === 'done') {
    return (
      <span className="w-3.5 h-3.5 rounded-full flex items-center justify-center"
            style={{ background: DONE_COLOR }}>
        <svg width="8" height="8" viewBox="0 0 8 8"><path d="M1.5 4.2 L3.3 6 L6.5 2.2" stroke="#0a0c0f" strokeWidth="1.4" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
      </span>
    )
  }
  const umriss = stand === 'offen' || stand === 'heute' ? farbe : '#3a3f4a'
  return <span className="w-3.5 h-3.5 rounded-full" style={{ boxShadow: `inset 0 0 0 1.5px ${umriss}` }} />
}

export default function KeySessions({ geplant, sessions }) {
  if (!geplant?.length) return null
  const liste = keySessions(geplant, sessions)
  const erledigt = liste.filter(k => k.stand === 'done').length

  return (
    <div>
      <div className="flex items-baseline justify-between mb-2">
        <span className="text-[9px] font-mono tracking-[0.2em] text-[var(--text-muted)]">KEY SESSIONS</span>
        {liste.length > 0 && (
          <span className="text-[10px] font-mono tabular-nums tracking-wider text-[var(--text-muted)]">
            <span style={{ color: erledigt === liste.length ? DONE_COLOR : '#e8eaf0' }}>{erledigt}</span> / {liste.length}
          </span>
        )}
      </div>

      {liste.length === 0 ? (
        <div className="text-[10px] font-mono tracking-widest text-[var(--text-muted)]">
          NONE PLANNED · AN EASY WEEK
        </div>
      ) : (
        <div className="space-y-1.5">
          {liste.map(k => {
            const farbe = disciplineColor(k.discipline)
            const stufe = INTENSITY_META[k.intensity]
            const tag = parseTag(k.planned_date).toLocaleDateString('en-GB', { weekday: 'short' }).toUpperCase()
            const vorbei = ['verpasst', 'skipped', 'replaced'].includes(k.stand)
            return (
              <div key={k.id}
                   className="grid grid-cols-[0.875rem_4.5rem_minmax(0,1fr)_2.25rem_3.75rem] items-center gap-x-2.5 text-[10px] font-mono"
                   style={{ opacity: vorbei ? 0.55 : 1 }}>
                <Marke stand={k.stand} farbe={farbe} />
                <span className="font-semibold tracking-wider truncate" style={{ color: farbe }}>
                  {disciplineLabel(k.discipline).toUpperCase()}
                </span>
                <span className="truncate" style={{ color: stufe?.color }}>
                  {NAME[k.intensity]}{k.duration_min ? <span className="text-[var(--text-muted)]"> · {k.duration_min}′</span> : null}
                </span>
                <span className="tracking-widest text-[var(--text-muted)]">{tag}</span>
                <span className="text-right tracking-widest"
                      style={{ color: k.stand === 'done' ? DONE_COLOR : k.stand === 'heute' ? '#e8eaf0' : 'var(--text-muted)' }}>
                  {STAND[k.stand].text}
                </span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
