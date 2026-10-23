import { isoTag, parseTag } from '../../utils/dates'
import { stunden } from '../../utils/einheiten'
import SportIcon from '../SportIcon'
import SollIstLeiste from './SollIstLeiste'

/** Eine Sportart der laufenden Woche als Zeile — im BREAKDOWN des Dashboards.
 *
 *  Vorher je Sportart ein buntes Kästchen: Anzahl groß, Zeit, km, die
 *  Wochentage als Text („Mo · Mi") und „2/3 reflektiert". Ob das zum Plan
 *  passte, stand nirgends, und eine geplante Sportart ohne Einheit fehlte
 *  ganz. Jetzt eine Zeile wie die übrigen Leisten:
 *
 *  - Stunden groß, darunter Anzahl und Strecke,
 *  - Soll/Ist gegen den Plan, aus der Bilanz (`/planned/am/{montag}/bilanz`,
 *    dieselben Regeln wie auf der Planseite),
 *  - sieben Tagespunkte Mo–So: gemacht, noch offen, verpasst,
 *  - ein Ring, wie viele Einheiten schon reflektiert sind.
 *
 *  Ein Klick klappt im Dashboard die Einheiten mit ihrer Reflexion auf, wie
 *  vorher die Kästchen.
 */

export const SPALTEN = 'sm:grid sm:grid-cols-[8.5rem_6rem_minmax(0,1fr)_auto_2.75rem] sm:items-center sm:gap-x-5'
export const TAGE_KURZ = ['M', 'T', 'W', 'T', 'F', 'S', 'S']

/** Die sieben Tage einer Sportart: `'done' | 'offen' | 'verpasst' | 'leer'`.
 *
 *  `done`, wenn an dem Tag eine Einheit dieser Sportart stattfand — auch eine
 *  ungeplante. Sonst `offen` für einen geplanten Tag ab heute, `verpasst` für
 *  einen geplanten Tag davor. Gestrichenes, Ersetztes und Ruhetage zählen
 *  nicht als geplant: Sie sind keine offene Aufgabe mehr.
 */
export function tagesPunkte(disc, sessions, geplant, montag, heute = isoTag(new Date())) {
  const gemacht = new Set(
    (sessions || [])
      .filter(s => !s.deleted_at && (s.discipline || '').toLowerCase() === disc)
      .map(s => s.session_date?.slice(0, 10)),
  )
  const geplanteTage = new Set(
    (geplant || [])
      .filter(p => (p.discipline || '').toLowerCase() === disc
        && !['skipped', 'replaced'].includes(p.status))
      .map(p => p.planned_date),
  )
  const m = parseTag(montag)
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(m)
    d.setDate(m.getDate() + i)
    const tag = isoTag(d)
    if (gemacht.has(tag)) return 'done'
    if (geplanteTage.has(tag)) return tag >= heute ? 'offen' : 'verpasst'
    return 'leer'
  })
}

function Punkt({ art, farbe, heute }) {
  const stil = {
    done: { background: farbe, boxShadow: `0 0 6px ${farbe}66` },
    offen: { boxShadow: `inset 0 0 0 1.5px ${farbe}` },
    verpasst: { boxShadow: 'inset 0 0 0 1.5px #3a3f4a' },
  }[art]
  return (
    <span className="w-4 h-5 flex items-center justify-center rounded-[3px]"
          style={{ background: heute ? '#ffffff0a' : 'transparent' }}>
      {art === 'leer'
        ? <span className="w-1.5 h-px" style={{ background: '#2a2f38' }} />
        : <span className="w-2 h-2 rounded-full" style={stil} />}
    </span>
  )
}

/** Wie viele Einheiten reflektiert sind, als feiner Ring. */
function Ring({ teil, ganz }) {
  if (!ganz) return <span />
  const fertig = teil >= ganz
  const farbe = fertig ? '#22c55e' : '#a7aebd'
  const r = 7
  const umfang = 2 * Math.PI * r
  return (
    <span className="flex items-center gap-1" title={`${teil} of ${ganz} reflected`}>
      <svg width="18" height="18" viewBox="0 0 18 18" className="-rotate-90">
        <circle cx="9" cy="9" r={r} fill="none" stroke="#1e2228" strokeWidth="2" />
        <circle cx="9" cy="9" r={r} fill="none" stroke={farbe} strokeWidth="2" strokeLinecap="round"
                strokeDasharray={`${(teil / ganz) * umfang} ${umfang}`} />
      </svg>
      <span className="text-[9px] font-mono tabular-nums" style={{ color: farbe }}>
        {fertig ? '✓' : `${teil}/${ganz}`}
      </span>
    </span>
  )
}

export default function SportZeile({
  disc, name, farbe, werte, soll, ist, skala, punkte, heuteIdx, aktiv, onClick,
}) {
  const anzahl = werte?.count || 0
  const klickbar = anzahl > 0
  return (
    <button
      type="button"
      onClick={klickbar ? onClick : undefined}
      disabled={!klickbar}
      title={klickbar ? (aktiv ? 'Close' : `${name}: sessions and reflection`) : `${name}: nothing done yet`}
      className={`w-full text-left rounded-lg px-3 py-2.5 transition-colors ${SPALTEN} ${klickbar ? 'hover:bg-[#ffffff05]' : 'cursor-default'}`}
      style={{
        background: aktiv ? `${farbe}0c` : undefined,
        boxShadow: `inset 2px 0 0 ${aktiv ? farbe : `${farbe}55`}`,
      }}
    >
      {/* Name und, auf dem Telefon, die Stunden daneben */}
      <div className="flex items-center justify-between gap-3 sm:contents">
        <div className="flex items-center gap-2 min-w-0" style={{ color: farbe }}>
          <SportIcon discipline={disc} size={15} />
          <span className="text-xs font-mono font-semibold tracking-wider truncate">{name.toUpperCase()}</span>
          {klickbar && <span className="text-[9px] text-[var(--text-muted)]">{aktiv ? '▴' : '▾'}</span>}
        </div>
        <div className="text-right sm:text-left">
          <div className="text-2xl font-black leading-none tabular-nums"
               style={{ fontFamily: 'Barlow Condensed, sans-serif', color: anzahl ? '#f2f4f8' : 'var(--text-muted)' }}>
            {stunden(werte?.min || 0)}
          </div>
          <div className="text-[9px] font-mono tracking-widest text-[var(--text-muted)] mt-1 whitespace-nowrap">
            {anzahl}×{werte?.km > 0 ? ` · ${werte.km.toFixed(1)} KM` : ''}
          </div>
        </div>
      </div>

      {/* Soll/Ist gegen den Plan */}
      <div className="mt-2.5 sm:mt-0 min-w-0">
        <div className="flex justify-end mb-1 text-[9px] font-mono tabular-nums tracking-wider text-[var(--text-muted)]">
          {soll > 0
            ? <span><span style={{ color: ist >= soll * 0.9 ? '#e8eaf0' : undefined }}>{Math.round(ist)}</span> / {Math.round(soll)} MIN</span>
            : ist > 0 ? 'UNPLANNED' : 'NOT PLANNED'}
        </div>
        <SollIstLeiste kompakt name={name} soll={soll} ist={ist} farbe={farbe} skala={skala} einheit="min" ohneText />
      </div>

      {/* Tagespunkte und Reflexion — auf dem Telefon in einer Zeile */}
      <div className="flex items-center justify-between mt-2 sm:mt-0 sm:contents">
        <div className="flex">
          {punkte.map((art, i) => <Punkt key={i} art={art} farbe={farbe} heute={i === heuteIdx} />)}
        </div>
        <div className="flex sm:justify-end">
          <Ring teil={werte?.reflektiert || 0} ganz={anzahl} />
        </div>
      </div>
    </button>
  )
}
