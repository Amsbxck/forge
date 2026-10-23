import { ACCENT, PHASE_COLOR, phaseColor } from '../../utils/colors'
import { daysUntil, parseTag } from '../../utils/dates'
import { phaseFamilie } from '../../utils/phasen'

/** Die Saison als Strahl: Phasen und ihre Blöcke, Entlastungswochen, Rennen, heute.
 *
 *  Vorher stand an drei Stellen (Dashboard, Plan, Rennen) „Woche x/y · Phase
 *  · noch n Tage" als Text. Wie lange der Aufbau noch läuft, wo das B-Rennen
 *  liegt, ließ sich daraus nicht ablesen.
 *
 *  **Eine Quelle:** `GET /metrics/saison` liefert Phasen und Unterphasen aus
 *  `core.race_types` (`phase_boundaries`, `phase_for_week`) — denselben
 *  Funktionen, nach denen der Planer plant. Hier wird nichts nachgerechnet,
 *  nur gezeichnet.
 *
 *  **Gezeichnet werden die Blöcke** (Base 1, Base 2, …), nicht nur die
 *  Phasen. Mit „Base 12W" neben einer dreiwöchigen Vorbereitung sah der
 *  Strahl ungleichmäßig aus, obwohl in gleich langen Blöcken zu vier Wochen
 *  geplant wird. Innerhalb einer Phase wird jeder Block kräftiger — die
 *  Steigerung soll man sehen, ohne zu lesen.
 *
 *  Nach **Datum**, nicht nach Wochennummer: Vorbereitung, Rennen und „heute"
 *  sind Tage, und die Wochennummer verschiebt sich mit jedem Zielwechsel
 *  (siehe CLAUDE.md, „Wochen werden über den Montag gewählt").
 *
 *  **Kopfzeile:** wo man steht und was als Nächstes kommt. Vor dem Planstart
 *  „PLAN STARTS IN 3 WEEKS", danach der nächste Block mit Datum. Früher stand
 *  hier „Deload ab 30.11." — Amir fragte zu Recht, was er damit soll: Den
 *  Deload plant der Coach, wissen muss man ihn vorher nicht. Er bleibt als
 *  Kerbe im Strahl.
 *
 *  Auf Englisch wie alle Anzeige-Leisten (Amirs Wunsch); die Phasennamen
 *  kommen ohnehin englisch aus dem Backend.
 *
 *  `kompakt` für die Planseite: dünner, ohne Beschriftung darunter.
 *  `fokus` (`{von, bis}`) rahmt eine Woche ein — auf der Planseite die
 *  angezeigte, die beim Blättern nicht die heutige ist. `ohneKopf` lässt die
 *  Kopfzeile weg, wenn die Karte Phase und Zeitraum schon selbst nennt.
 */

const TAG_MS = 86400000
const WOCHE_MS = 7 * TAG_MS

const OFFSEASON_EN = { formerhalt: 'MAINTENANCE', 'übergang': 'TRANSITION' }

/** „Base 2" → „BASE 2", „Race Week" → „RACE WEEK", die Vorbereitung heißt PREP. */
export function blockName(name) {
  if (phaseFamilie(name) === 'grundlage') return 'PREP'
  return (name || '').toUpperCase()
}

const kurzDatum = tag =>
  parseTag(tag).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }).toUpperCase()

export default function SaisonStrahl({ saison, kompakt = false, fokus = null, ohneKopf = false, ohneTage = false }) {
  if (!saison) return null

  if (saison.lage === 'off_season') {
    const seit = saison.race_date ? -daysUntil(saison.race_date) : null
    const phase = (saison.offseason_phase || 'Formerhalt').toLowerCase()
    const wochen = seit > 0 ? Math.round(seit / 7) : null
    return (
      <div className="flex items-center gap-2 text-[10px] font-mono tracking-widest text-[var(--text-muted)]">
        <span className="w-1.5 h-1.5 rounded-full" style={{ background: PHASE_COLOR.off }} />
        OFF SEASON · {OFFSEASON_EN[phase] || phase.toUpperCase()}
        {wochen > 0 && (
          <span className="opacity-70">· RACE {wochen} {wochen === 1 ? 'WEEK' : 'WEEKS'} AGO</span>
        )}
      </div>
    )
  }

  const phasen = saison.phasen || []
  if (!phasen.length) return null

  // Blöcke nach Datum. Die Vorbereitung steht als eigener Block vor Woche 1.
  // Ein Backend ohne `teile` (älterer Stand) zeichnet jede Phase als einen
  // Block — dann gröber, aber nicht leer.
  const bloecke = [
    ...(saison.grundlage
      ? [{ name: 'Grundlage', von: saison.grundlage.von, bis: saison.grundlage.bis, stufe: 1, phase: 'grundlage' }]
      : []),
    ...phasen.flatMap(p => {
      const teile = p.teile?.length ? p.teile : [p]
      return teile.map((t, i) => ({ ...t, stufe: teile.length > 1 ? i / (teile.length - 1) : 1, phase: p.name }))
    }),
  ]
  const start = parseTag(bloecke[0].von).getTime()
  const ende = parseTag(bloecke[bloecke.length - 1].bis).getTime() + TAG_MS
  const posMs = ms => Math.min(100, Math.max(0, ((ms - start) / (ende - start)) * 100))
  const pos = tag => posMs(parseTag(tag).getTime())
  // Das Ende eines Blocks ist der Tag **nach** seinem letzten Tag. Über
  // Millisekunden, nicht über `toISOString`: Das rechnet in UTC und lieferte
  // in Berlin für Mitternacht den Vortag.
  const posEnde = tag => posMs(parseTag(tag).getTime() + TAG_MS)
  const heute = pos(saison.heute)

  const imPlan = bloecke.filter(b => b.von_woche != null)
  const aktuell = imPlan.find(b => saison.aktuelle_woche >= b.von_woche && saison.aktuelle_woche <= b.bis_woche)
  const naechster = aktuell ? imPlan[imPlan.indexOf(aktuell) + 1] : null
  const tage = saison.race_date ? daysUntil(saison.race_date) : null

  // Wochen bis zum Planstart über die Montage: An einem Freitag der Woche
  // vom 19.10. mit Planstart am 09.11. sind es drei Wochen, nicht „2,4".
  let planInWochen = null
  if (saison.grundlage && saison.plan_start) {
    const heuteTag = parseTag(saison.heute)
    const montag = new Date(heuteTag)
    montag.setDate(heuteTag.getDate() - ((heuteTag.getDay() + 6) % 7))
    planInWochen = Math.round((parseTag(saison.plan_start).getTime() - montag.getTime()) / WOCHE_MS)
  }

  const kopfName = saison.grundlage ? 'PREP' : blockName(aktuell?.name)
  const kopfFarbe = phaseColor(saison.grundlage ? 'grundlage' : aktuell?.name)

  return (
    <div>
      {!ohneKopf && (
      <div className="flex items-end justify-between gap-3 mb-2.5">
        <div className="flex items-baseline gap-x-2.5 gap-y-1 flex-wrap min-w-0">
          <span
            className={`${kompakt ? 'text-sm' : 'text-base'} font-bold tracking-wide`}
            style={{ fontFamily: 'Barlow Condensed, sans-serif', color: kopfFarbe }}
          >
            {kopfName}
          </span>
          {saison.aktuelle_woche && (
            <span className="text-[10px] font-mono tracking-widest tabular-nums text-[var(--text-secondary)]">
              WEEK {saison.aktuelle_woche}/{saison.total_weeks}
            </span>
          )}
          {planInWochen != null && (
            <span className="text-[10px] font-mono tracking-widest text-[var(--text-secondary)]">
              PLAN STARTS {planInWochen <= 0 ? 'THIS WEEK' : planInWochen === 1 ? 'NEXT WEEK' : `IN ${planInWochen} WEEKS`}
              <span className="text-[var(--text-muted)]"> · {kurzDatum(saison.plan_start)}</span>
            </span>
          )}
          {!kompakt && naechster && (
            <span className="text-[10px] font-mono tracking-widest text-[var(--text-muted)]">
              · <span style={{ color: phaseColor(naechster.name) }}>{blockName(naechster.name)}</span> FROM {kurzDatum(naechster.von)}
            </span>
          )}
        </div>
        {/* `ohneTage` auf der Rennseite: Dort steht der Countdown schon groß in
            der Zielkachel, zweimal „247" untereinander war einmal zu viel. */}
        {tage != null && !ohneTage && (
          // Die Tage bis zum Rennen sind die Zahl, nach der man auf dem
          // Dashboard sucht — als Fließtext in 10 px ging sie unter.
          <span className="shrink-0 flex items-baseline gap-1.5 text-[10px] font-mono tracking-widest text-[var(--text-secondary)]">
            {tage > 0 ? (
              <>
                <span
                  className={`${kompakt ? 'text-xl' : 'text-3xl'} font-black leading-none tabular-nums tracking-normal`}
                  style={{ color: ACCENT, fontFamily: 'Barlow Condensed, sans-serif', textShadow: `0 0 16px ${ACCENT}40` }}
                >
                  {tage}
                </span>
                {tage === 1 ? 'DAY TO GO' : 'DAYS TO GO'}
              </>
            ) : 'RACE WEEK'}
          </span>
        )}
      </div>
      )}

      <div className={`relative ${kompakt ? 'h-1.5' : 'h-2.5'}`}>
        {/* Die Blöcke, in der Farbe ihrer Phase. Vergangenes kräftig,
            Kommendes gedämpft — so liest man „wie weit" ohne Zahl. Zwischen
            zwei Phasen eine breitere Fuge als zwischen zwei Blöcken. */}
        {bloecke.map((b, i) => {
          const farbe = phaseColor(b.name)
          const l = pos(b.von)
          const r = posEnde(b.bis)
          const neuePhase = i === 0 || bloecke[i - 1].phase !== b.phase
          const fuge = neuePhase ? 2 : 1
          return (
            <div
              key={`${b.name}-${b.von}`}
              className="absolute inset-y-0 rounded-[2px] overflow-hidden"
              style={{
                left: `calc(${l}% + ${fuge}px)`,
                width: `calc(${r - l}% - ${fuge + 1}px)`,
                background: `${farbe}${b.stufe < 0.5 ? '1c' : b.stufe < 1 ? '26' : '33'}`,
              }}
              title={`${blockName(b.name)} · ${kurzDatum(b.von)} – ${kurzDatum(b.bis)}${b.von_woche ? ` · weeks ${b.von_woche}–${b.bis_woche}` : ''}`}
            >
              <div
                className="absolute inset-y-0 left-0"
                style={{
                  width: `${Math.min(100, Math.max(0, ((heute - l) / (r - l)) * 100))}%`,
                  background: farbe,
                  opacity: 0.6 + 0.3 * b.stufe,
                }}
              />
            </div>
          )
        })}

        {/* Entlastungswochen als feine Kerben */}
        {(saison.deload || []).map(d => (
          <div
            key={d.woche}
            className="absolute inset-y-0 w-px"
            style={{ left: `${pos(d.montag)}%`, background: '#0a0c0f', opacity: 0.9 }}
            title={`Deload · week ${d.woche} · ${kurzDatum(d.montag)}`}
          />
        ))}

        {/* B- und C-Rennen als Rauten, das Saisonziel am Ende */}
        {(saison.rennen || []).map(r => (
          <div
            key={`${r.datum}-${r.name}`}
            className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 w-2 h-2 rotate-45"
            style={{ left: `${pos(r.datum)}%`, background: '#0a0c0f', border: `1px solid ${ACCENT}` }}
            title={`${r.prioritaet} race · ${r.name || ''} · ${kurzDatum(r.datum)}`}
          />
        ))}
        {saison.race_date && (
          <div
            className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 w-2.5 h-2.5 rotate-45"
            style={{ left: `${pos(saison.race_date)}%`, background: ACCENT, boxShadow: `0 0 8px ${ACCENT}` }}
            title={`${saison.race_name || 'Season goal'} · ${kurzDatum(saison.race_date)}`}
          />
        )}

        {/* Die angezeigte Woche, eingerahmt */}
        {fokus && (
          <div
            className="absolute rounded-[3px] pointer-events-none"
            style={{
              left: `${pos(fokus.von)}%`,
              width: `${Math.max(0.8, posEnde(fokus.bis) - pos(fokus.von))}%`,
              top: -3, bottom: -3,
              boxShadow: `0 0 0 1px ${ACCENT}, 0 0 10px ${ACCENT}66`,
            }}
            title={`Shown week · ${kurzDatum(fokus.von)} – ${kurzDatum(fokus.bis)}`}
          />
        )}

        {/* Heute */}
        <div
          className="absolute -translate-x-1/2"
          style={{ left: `${heute}%`, top: -4, bottom: -4, width: 2, background: '#e8eaf0', boxShadow: '0 0 6px #e8eaf0aa' }}
          title={`Today · ${kurzDatum(saison.heute)}`}
        />
      </div>

      {!kompakt && (
        <div className="relative h-4 mt-1.5">
          {bloecke.map(b => {
            const l = pos(b.von)
            const r = posEnde(b.bis)
            const istAktuell = b === aktuell || (saison.grundlage && b.phase === 'grundlage')
            return (
              <div
                key={`${b.name}-${b.von}-l`}
                className="absolute text-[9px] font-mono truncate pl-0.5"
                style={{ left: `${l}%`, width: `${r - l}%`, color: istAktuell ? '#e8eaf0' : 'var(--text-muted)' }}
              >
                {blockName(b.name)}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
