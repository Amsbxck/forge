import { useMemo, useState } from 'react'
import { FAMILIE_LABEL, phaseFamilie } from '../utils/phasen'
import { PHASE_COLOR } from '../utils/colors'
import {
  AUTOMATISCH,
  GRUPPEN,
  OPTIONEN,
  istMoeglich,
} from '../utils/trainingsoptionen'

/** Das aufklappbare Glossar der wünschbaren Trainingsformen.
 *
 *  Zwei Dinge unterscheiden diese Liste von einem Nachschlagewerk:
 *
 *  1. **Sie weiß, welche Phase gerade läuft.** Was jetzt nicht geht, steht
 *     ausgegraut da — mit dem Grund, nicht ohne. Eine Liste, die alles gleich
 *     anzeigt, erzeugt Wünsche, die der Coach ablehnen muss.
 *  2. **Ein Klick übernimmt den Wunsch.** Hat die Form einen Knopf in der
 *     Reihe über dem Eingabefeld, wird dieser gesetzt — nicht Text angehängt.
 *     Sonst zeigten Panel und Knopfreihe verschiedene Zustände für dieselbe
 *     Entscheidung, und das Abwählen wirkte nur an einer von beiden Stellen.
 *
 *  Die Liste selbst liegt in `utils/trainingsoptionen.js`, weil die Knopfreihe
 *  dieselbe braucht — siehe dort.
 */

const ACCENT = '#00d4ff'

function Etikett({ text, farbe, gedimmt }) {
  return (
    <span
      className="text-[9px] font-mono tracking-wider px-1.5 py-0.5 rounded"
      style={{
        color: gedimmt ? 'var(--text-muted)' : farbe,
        background: gedimmt ? '#16181f' : `${farbe}14`,
        border: `1px solid ${gedimmt ? '#1e2228' : `${farbe}33`}`,
      }}
    >
      {text}
    </span>
  )
}

function Option({ o, familie, onWunsch }) {
  const [offen, setOffen] = useState(false)
  const moeglich = istMoeglich(o, familie)
  const farbe = o.art === AUTOMATISCH ? '#40916c' : ACCENT

  return (
    <div
      className="rounded-lg overflow-hidden transition-colors"
      style={{
        background: '#111318',
        border: '1px solid #1e2228',
        // Die Schiene links sagt auf einen Blick, ob es jetzt geht. Ohne sie
        // liest sich die Liste wie ein Katalog, in dem alles gleich weit weg
        // ist. Nach `border`, damit sie es überschreibt und nicht umgekehrt.
        borderLeft: `2px solid ${moeglich ? farbe : '#1e2228'}`,
        opacity: moeglich ? 1 : 0.55,
      }}
    >
      <button
        onClick={() => setOffen(v => !v)}
        className="w-full text-left px-3 py-2.5 hover:bg-[#15171e] transition-colors"
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div
              className="text-[13px] font-bold leading-tight"
              style={{
                fontFamily: 'Barlow Condensed, sans-serif',
                color: moeglich ? '#e8eaf0' : 'var(--text-secondary)',
              }}
            >
              {o.name.toUpperCase()}
            </div>
            <div className="text-[11px] text-[var(--text-secondary)] mt-0.5 leading-snug">
              {o.kurz}
            </div>
          </div>
          <span className="text-[var(--text-muted)] font-mono text-[10px] shrink-0 mt-0.5">
            {offen ? '▲' : '▼'}
          </span>
        </div>

        <div className="flex flex-wrap gap-1 mt-2">
          <Etikett
            text={o.art === AUTOMATISCH ? 'KOMMT VON SELBST' : 'AUF WUNSCH'}
            farbe={farbe}
            gedimmt={!moeglich}
          />
          {(o.phasen || []).map(p => (
            <Etikett
              key={p}
              text={(FAMILIE_LABEL[p] || p).toUpperCase()}
              farbe={PHASE_COLOR[p] || ACCENT}
              gedimmt={!moeglich}
            />
          ))}
          {o.phasen === null && (
            <Etikett text="JEDE PHASE" farbe={PHASE_COLOR.base} gedimmt={false} />
          )}
        </div>
      </button>

      {offen && (
        <div className="px-3 pb-3 pt-1 space-y-2 border-t border-[#1e2228]">
          <div>
            <div className="text-[9px] font-mono tracking-widest text-[var(--text-muted)] mb-0.5">
              BEDINGUNGEN
            </div>
            <div className="text-[11px] text-[#c8ccd6] leading-snug">{o.bedingung}</div>
          </div>
          <div>
            <div className="text-[9px] font-mono tracking-widest text-[var(--text-muted)] mb-0.5">
              BELEG
            </div>
            <div className="text-[11px] text-[var(--text-secondary)] leading-snug">
              {o.beleg}
            </div>
          </div>
          {o.hinweis && (
            <div
              className="text-[11px] leading-snug px-2 py-1.5 rounded"
              style={{ background: `${ACCENT}0d`, color: '#c8ccd6' }}
            >
              {o.hinweis}
            </div>
          )}

          {!moeglich && (
            <div className="text-[11px] text-[var(--text-muted)] leading-snug">
              Jetzt nicht: diese Form gehört in{' '}
              {(o.phasen || []).map(p => FAMILIE_LABEL[p] || p).join(' oder ')}
              {familie ? `, die laufende Phase ist ${FAMILIE_LABEL[familie] || familie}.` : '.'}
            </div>
          )}

          {moeglich && o.wunsch && (
            <button
              // Die ganze Option, nicht nur ihr Satz: Hat sie einen Knopf in
              // der Reihe über dem Eingabefeld, wird dieser gesetzt statt Text
              // angehängt — sonst liefen Panel und Knopfreihe auseinander.
              onClick={() => onWunsch(o)}
              className="text-[10px] font-mono tracking-wider px-2.5 py-1.5 rounded transition-colors"
              style={{
                color: ACCENT,
                background: `${ACCENT}14`,
                border: `1px solid ${ACCENT}44`,
              }}
              onMouseEnter={e => { e.currentTarget.style.background = `${ACCENT}26` }}
              onMouseLeave={e => { e.currentTarget.style.background = `${ACCENT}14` }}
            >
              IN DIE WÜNSCHE ÜBERNEHMEN →
            </button>
          )}
          {moeglich && !o.wunsch && (
            <div className="text-[11px] text-[var(--text-muted)] leading-snug">
              Kein Wunsch nötig — das macht die App von selbst.
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function PlanOptionen({ phase, onWunsch }) {
  const [open, setOpen] = useState(false)
  const familie = useMemo(() => phaseFamilie(phase), [phase])

  const moeglichJetzt = OPTIONEN.filter(o => istMoeglich(o, familie)).length

  return (
    <div className="bg-[#0d0f17] border border-[#1e2228] rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-[#111318] transition-colors"
      >
        <div className="flex items-center gap-3 flex-wrap">
          <span
            className="font-bold tracking-widest text-[var(--text-secondary)]"
            style={{ fontFamily: 'Barlow Condensed, sans-serif', fontSize: '0.85rem' }}
          >
            WAS DU DIR WÜNSCHEN KANNST
          </span>
          <span className="text-xs font-mono text-[var(--text-muted)]">
            {moeglichJetzt} von {OPTIONEN.length} jetzt möglich
            {familie ? ` · Phase ${FAMILIE_LABEL[familie]}` : ''}
          </span>
        </div>
        <span className="text-[var(--text-secondary)] font-mono text-sm">
          {open ? '▲' : '▼'}
        </span>
      </button>

      {open && (
        <div className="border-t border-[#1e2228] p-5 space-y-5">
          <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed">
            Diese Trainingsformen stehen in den Studiendokumenten, und der Coach
            plant sie — aber die meisten schlägt er nicht von selbst vor. Was
            jetzt nicht geht, steht ausgegraut mit dem Grund dabei. Wo ein Beleg
            dünn ist, ist es vermerkt; das entscheidet, wie fest du darauf bauen
            solltest.
          </p>

          {GRUPPEN.map(gruppe => {
            const eintraege = OPTIONEN.filter(o => o.gruppe === gruppe)
            if (!eintraege.length) return null
            return (
              <div key={gruppe}>
                <div className="text-[10px] font-mono tracking-widest text-[var(--text-secondary)] mb-2">
                  {gruppe.toUpperCase()}
                </div>
                <div className="grid gap-2 md:grid-cols-2">
                  {eintraege.map(o => (
                    <Option
                      key={o.id}
                      o={o}
                      familie={familie}
                      onWunsch={onWunsch}
                    />
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
