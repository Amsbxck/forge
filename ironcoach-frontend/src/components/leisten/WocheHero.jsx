import { useEffect, useMemo, useRef, useState } from 'react'
import { ACCENT, DISCIPLINE_COLOR, DISCIPLINE_LABEL, STATUS_COLOR } from '../../utils/colors'
import { isoTag, parseTag } from '../../utils/dates'
import { SPORTEN, sportVon, stunden, tagesSummen, wochenSummen } from '../../utils/einheiten'

/** Die laufende Woche als große Kachel ganz oben im Dashboard.
 *
 *  Vorher drei Zahlen (Einheiten, Zeit, Strecke) ohne Bezug: nicht zum Plan,
 *  nicht zur Vorwoche, und wie sich die Woche über die Tage verteilt, stand
 *  nirgends. Amir wollte sie „majestätischer" — groß, ruhig, mit allem, was
 *  zur Woche gehört, auf einen Blick:
 *
 *  - die drei Zahlen groß, beim Laden einmal hochzählend, darunter der
 *    Vergleich zur Vorwoche **bis zum selben Wochentag**,
 *  - rechts die Stunden der letzten acht Wochen,
 *  - das Wochenband Mo–So: absolviert gefüllt in Sportfarben, geplant als
 *    Umriss dahinter,
 *  - Ist gegen Plan als Leiste mit Erfüllungsgrad.
 *
 *  Geplant kommt aus `/planned/am/{montag}` (Tage) und der Bilanz (Summen)
 *  — denselben Quellen wie die Soll/Ist-Leisten der Planseite. Die Regeln
 *  der Bilanz gelten auch hier: Ruhetage zählen nicht, ein ersetzter Tag
 *  („war wandern") zählt mit seinen Minuten unter der Ersatz-Sportart als
 *  absolviert.
 */

const TAGE = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']
const DISPLAY = { fontFamily: 'Barlow Condensed, sans-serif' }
const KOPF = 'text-[9px] font-mono tracking-[0.2em] text-[var(--text-muted)]'
const SCHRAFFUR = 'repeating-linear-gradient(135deg, transparent 0 2px, #0a0c0f 2px 4px)'
const BAND_HOEHE = 120

// ─── Reine Rechnungen (exportiert für die Probe) ───────────────────────────

/** Geplante Minuten je Tag und Sportart: `{tag: {min, jeSport}}`. */
export function tagesPlan(geplant) {
  const ergebnis = {}
  for (const p of geplant || []) {
    const sport = (p.discipline || '').toLowerCase()
    if (!p.planned_date || sport === 'rest' || !p.duration_min) continue
    const t = (ergebnis[p.planned_date] ||= { min: 0, jeSport: {} })
    t.min += p.duration_min
    const k = SPORTEN.includes(sport) ? sport : 'other'
    t.jeSport[k] = (t.jeSport[k] || 0) + p.duration_min
  }
  return ergebnis
}

/** Absolvierte Minuten je Tag: die Einheiten, dazu ersetzte Tage mit ihren
 *  Ersatzminuten (die stehen nur am Plan, nicht als Einheit). */
export function tagesIst(sessions, geplant) {
  const ergebnis = tagesSummen(sessions)
  for (const p of geplant || []) {
    if (p.status !== 'replaced' || !p.replacement_min || !p.planned_date) continue
    const t = (ergebnis[p.planned_date] ||= { min: 0, tss: 0, km: 0, n: 0, jeSport: {} })
    const k = SPORTEN.includes((p.replacement_discipline || '').toLowerCase())
      ? p.replacement_discipline.toLowerCase() : 'other'
    t.min += p.replacement_min
    t.n += 1
    t.jeSport[k] = (t.jeSport[k] || 0) + p.replacement_min
  }
  return ergebnis
}

/** Summen der Vorwoche bis zum selben Wochentag wie heute.
 *
 *  Gegen die ganze Vorwoche stünde jeder Mittwoch im Minus — drei Tage
 *  gegen sieben. Verglichen wird, was bis zu diesem Punkt der Woche
 *  passiert war.
 */
export function vorwocheBisHeute(verlauf, montag, heute = new Date()) {
  const m = parseTag(montag)
  const vorMontag = new Date(m)
  vorMontag.setDate(m.getDate() - 7)
  const tagImWoche = Math.min(6, Math.max(0, Math.round((parseTag(isoTag(heute)) - m) / 86400000)))
  const bis = new Date(vorMontag)
  bis.setDate(vorMontag.getDate() + tagImWoche)
  const [a, b] = [isoTag(vorMontag), isoTag(bis)]
  const summe = { min: 0, km: 0, n: 0, tss: 0 }
  for (const s of verlauf || []) {
    const t = s.session_date?.slice(0, 10)
    if (s.deleted_at || !t || t < a || t > b) continue
    summe.min += s.duration_min || 0
    summe.km += s.distance_km || 0
    summe.tss += s.tss || 0
    summe.n += 1
  }
  return summe
}

// ─── Hochzählen ─────────────────────────────────────────────────────────────

/** Zählt einmal von 0 auf `ziel` (ease-out, ~900 ms). Ändert sich der Wert
 *  danach (neue Einheit), springt er ohne Animation — sonst zählte die
 *  Kachel bei jedem Neuladen wieder von vorn. */
function useHochzaehlen(ziel, dauer = 900) {
  const ruhig = typeof window !== 'undefined'
    && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  const [wert, setWert] = useState(ruhig ? ziel : 0)
  const fertig = useRef(ruhig)
  useEffect(() => {
    if (fertig.current) { setWert(ziel); return }
    let start = null
    let rahmen
    const schritt = t => {
      if (start == null) start = t
      const p = Math.min(1, (t - start) / dauer)
      setWert(ziel * (1 - Math.pow(1 - p, 3)))
      if (p < 1) rahmen = requestAnimationFrame(schritt)
      else fertig.current = true
    }
    rahmen = requestAnimationFrame(schritt)
    return () => cancelAnimationFrame(rahmen)
  }, [ziel, dauer])
  return wert
}

const zeitText = min => {
  const h = Math.floor(min / 60)
  const m = Math.round(min % 60)
  return h > 0 ? `${h}h ${String(m).padStart(2, '0')}` : `${m}m`
}

function Delta({ jetzt, davor, absolut = false }) {
  if (davor == null) return <div className="h-4" />
  if (!davor && !jetzt) return <div className="h-4" />
  const prozent = davor ? ((jetzt - davor) / davor) * 100 : null
  const farbe = (absolut ? jetzt - davor : prozent ?? 1) > 0.5 ? STATUS_COLOR.green
    : prozent != null && prozent < -15 ? STATUS_COLOR.yellow : '#a7aebd'
  const text = absolut
    ? `${jetzt - davor > 0 ? '+' : jetzt - davor < 0 ? '−' : '±'}${Math.abs(jetzt - davor)}`
    : prozent == null ? 'NEW' : `${prozent > 0 ? '+' : prozent < 0 ? '−' : '±'}${Math.abs(Math.round(prozent))} %`
  return (
    <div className="h-4 mt-1.5 text-[10px] font-mono tracking-widest tabular-nums whitespace-nowrap">
      <span style={{ color: farbe }}>{text}</span>
      <span className="text-[var(--text-muted)]"> VS LAST WEEK</span>
    </div>
  )
}

// ─── Kachel ────────────────────────────────────────────────────────────────

export default function WocheHero({ sessions, geplant, bilanz, verlauf, montag }) {
  const [hover, setHover] = useState(null)
  const [da, setDa] = useState(false)
  useEffect(() => {
    const t = requestAnimationFrame(() => setDa(true))
    return () => cancelAnimationFrame(t)
  }, [])

  const heute = isoTag(new Date())
  const aktiv = useMemo(() => (sessions || []).filter(s => !s.deleted_at), [sessions])
  const summe = useMemo(() => aktiv.reduce((a, s) => ({
    n: a.n + 1, min: a.min + (s.duration_min || 0), km: a.km + (s.distance_km || 0),
  }), { n: 0, min: 0, km: 0 }), [aktiv])
  const davor = useMemo(() => (verlauf ? vorwocheBisHeute(verlauf, montag) : null), [verlauf, montag])

  const n = useHochzaehlen(summe.n)
  const min = useHochzaehlen(summe.min)
  const km = useHochzaehlen(summe.km)

  // Die Tage der Woche
  const plan = useMemo(() => tagesPlan(geplant), [geplant])
  const ist = useMemo(() => tagesIst(aktiv, geplant), [aktiv, geplant])
  const tage = TAGE.map((kurz, i) => {
    const d = parseTag(montag)
    d.setDate(d.getDate() + i)
    const tag = isoTag(d)
    return { kurz, tag, plan: plan[tag], ist: ist[tag], zukunft: tag > heute, heute: tag === heute }
  })
  const skala = Math.max(30, ...tage.map(t => Math.max(t.plan?.min || 0, t.ist?.min || 0)))

  // Acht Wochen
  const acht = useMemo(() => {
    const jeWoche = wochenSummen(verlauf || [])
    const m = parseTag(montag)
    return Array.from({ length: 8 }, (_, i) => {
      const d = new Date(m)
      d.setDate(m.getDate() - (7 - i) * 7)
      const w = isoTag(d)
      return { montag: w, min: w === montag ? summe.min : jeWoche[w]?.min || 0, jetzt: w === montag }
    })
  }, [verlauf, montag, summe.min])
  const achtMax = Math.max(1, ...acht.map(w => w.min))

  // Ist gegen Plan, aus der Bilanz
  const geplantMin = (bilanz?.disziplinen || []).reduce((a, d) => a + (d.geplant_min || 0), 0)
  const jeSportIst = {}
  let ungeplant = 0
  for (const d of bilanz?.disziplinen || []) {
    const k = SPORTEN.includes(d.discipline) ? d.discipline : 'other'
    jeSportIst[k] = (jeSportIst[k] || 0) + (d.absolviert_min - d.ungeplant_min)
    ungeplant += d.ungeplant_min || 0
  }
  const imPlanIst = Object.values(jeSportIst).reduce((a, b) => a + b, 0)
  const quote = geplantMin ? Math.round((imPlanIst / geplantMin) * 100) : null
  const leisteMax = Math.max(geplantMin, imPlanIst + ungeplant)

  // Hintergrund: die Sportarten der Woche, nach Zeit gewichtet, höchstens drei.
  const jeSportWoche = {}
  aktiv.forEach(s => { jeSportWoche[sportVon(s)] = (jeSportWoche[sportVon(s)] || 0) + (s.duration_min || 0) })
  const farben = Object.entries(jeSportWoche).sort((a, b) => b[1] - a[1]).slice(0, 3)
    .map(([sp]) => DISCIPLINE_COLOR[sp] || DISCIPLINE_COLOR.other)
  const hintergrund = farben.length
    ? `linear-gradient(115deg, ${farben[0]}17 0%, ${(farben[1] || farben[0])}0d 40%, ${(farben[2] || farben[1] || farben[0])}08 60%, transparent 80%), #111318`
    : '#111318'

  const von = parseTag(montag)
  const bisTag = new Date(von)
  bisTag.setDate(von.getDate() + 6)
  const monat = d => d.toLocaleDateString('en-GB', { month: 'short' }).toUpperCase()
  const zeitraumText = `${von.getDate()}${von.getMonth() !== bisTag.getMonth() ? ` ${monat(von)}` : ''}–${bisTag.getDate()} ${monat(bisTag)}`
  const gezeigt = hover

  return (
    <div className="rounded-xl p-5 sm:p-6 relative overflow-hidden"
         style={{ background: hintergrund, border: `1px solid ${farben[0] ? `${farben[0]}2a` : '#1e2228'}` }}>
      <div className="flex items-baseline justify-between mb-4">
        <span className="text-xs font-mono tracking-[0.25em] text-[var(--text-secondary)]">THIS WEEK</span>
        <span className="text-[10px] font-mono tracking-widest text-[var(--text-muted)]">{zeitraumText}</span>
      </div>

      {/* ── Zahlen und acht Wochen ── */}
      <div className="flex items-end justify-between gap-x-6 gap-y-5 flex-wrap">
        <div className="grid grid-cols-3 flex-1 min-w-[16rem] max-w-2xl">
          {[
            { name: 'SESSIONS', wert: Math.round(n), delta: <Delta jetzt={summe.n} davor={davor?.n} absolut /> },
            { name: 'TIME', wert: zeitText(min), delta: <Delta jetzt={summe.min} davor={davor?.min} /> },
            { name: 'DISTANCE', wert: km.toFixed(1), einheit: 'km', delta: <Delta jetzt={summe.km} davor={davor?.km} /> },
          ].map((f, i) => (
            <div key={f.name} className={i ? 'pl-4 sm:pl-6 border-l border-[#ffffff0f]' : 'pr-4 sm:pr-6'}>
              <div className={KOPF}>{f.name}</div>
              <div className="flex items-baseline gap-1 mt-2">
                <span className="text-4xl sm:text-6xl font-black leading-none tabular-nums text-[#f2f4f8]"
                      style={{ ...DISPLAY, textShadow: '0 0 28px #ffffff14' }}>
                  {f.wert}
                </span>
                {f.einheit && <span className="text-xs font-mono text-[var(--text-muted)]">{f.einheit}</span>}
              </div>
              {f.delta}
            </div>
          ))}
        </div>

        {verlauf && (
          <div className="shrink-0">
            <div className={`${KOPF} mb-1.5 text-right`}>8 WEEKS</div>
            <div className="flex items-end gap-1.5 h-12">
              {acht.map(w => (
                <div key={w.montag} className="w-3 h-full flex flex-col justify-end"
                     title={`Week of ${parseTag(w.montag).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}: ${stunden(w.min)}`}>
                  <div className="w-full rounded-t-[2px] transition-[height] duration-700 ease-out"
                       style={{
                         height: da ? `${Math.max(4, (w.min / achtMax) * 100)}%` : '4%',
                         background: w.jetzt ? ACCENT : w.min ? '#4a5263' : '#1e2228',
                         boxShadow: w.jetzt ? `0 0 10px ${ACCENT}88` : 'none',
                       }} />
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ── Wochenband Mo–So ── */}
      <div className="mt-6">
        <div className="relative grid grid-cols-7 gap-2 sm:gap-3" style={{ height: BAND_HOEHE }}>
          {tage.map(t => {
            const planMin = t.plan?.min || 0
            const istMin = t.ist?.min || 0
            const imPlan = Math.min(istMin, planMin || istMin)
            const drueber = planMin ? Math.max(0, istMin - planMin) : 0
            const planFarbe = DISCIPLINE_COLOR[Object.entries(t.plan?.jeSport || {}).sort((a, b) => b[1] - a[1])[0]?.[0]] || '#5b6475'
            const an = hover?.tag === t.tag
            return (
              <div key={t.tag} className="relative h-full flex flex-col justify-end"
                   onMouseEnter={() => setHover(t)} onMouseLeave={() => setHover(null)}>
                {/* Geplant: feiner Umriss */}
                {planMin > 0 && (
                  <div className="absolute inset-x-0 bottom-0 rounded-[4px] transition-[height] duration-700 ease-out"
                       style={{
                         height: da ? `${(planMin / skala) * 100}%` : 0,
                         boxShadow: `inset 0 0 0 1px ${planFarbe}${t.zukunft ? '88' : '55'}`,
                         background: t.zukunft ? `${planFarbe}0c` : 'transparent',
                       }} />
                )}
                {/* Absolviert: gestapelt nach Sportart, Überschuss schraffiert */}
                {istMin > 0 && (
                  <div className="relative w-full flex flex-col-reverse rounded-[4px] overflow-hidden transition-[height] duration-700 ease-out"
                       style={{
                         height: da ? `${(istMin / skala) * 100}%` : 0,
                         opacity: hover && !an ? 0.6 : 1,
                         boxShadow: an ? '0 0 14px #ffffff22' : 'none',
                       }}>
                    {SPORTEN.filter(sp => t.ist.jeSport[sp]).map(sp => (
                      <div key={sp} style={{
                        height: `${(t.ist.jeSport[sp] / istMin) * 100}%`,
                        background: DISCIPLINE_COLOR[sp] || DISCIPLINE_COLOR.other,
                        opacity: 0.9,
                      }} />
                    ))}
                    {drueber > 0 && (
                      <div className="absolute inset-x-0 top-0 pointer-events-none"
                           style={{ height: `${(drueber / istMin) * 100}%`, backgroundImage: SCHRAFFUR }} />
                    )}
                  </div>
                )}
                {/* Leere Vergangenheit ohne Plan: eine Grundlinie */}
                {!planMin && !istMin && (
                  <div className="w-full h-[2px] rounded-full" style={{ background: '#1e2228' }} />
                )}
                {imPlan === 0 && null}
              </div>
            )
          })}
        </div>
        <div className="grid grid-cols-7 gap-2 sm:gap-3 mt-2">
          {tage.map(t => (
            <div key={t.tag} className="text-center">
              <div className="text-[9px] font-mono tracking-widest"
                   style={{ color: t.heute ? ACCENT : 'var(--text-muted)', textShadow: t.heute ? `0 0 8px ${ACCENT}` : 'none' }}>
                {t.kurz}
              </div>
              <div className="text-[10px] font-mono tabular-nums mt-0.5"
                   style={{ color: t.ist?.min ? '#e8eaf0' : 'var(--text-muted)' }}>
                {t.ist?.min ? stunden(t.ist.min) : t.plan?.min ? stunden(t.plan.min) : '—'}
              </div>
            </div>
          ))}
        </div>
        {/* Was unter dem Zeiger liegt — feste Höhe, damit nichts springt */}
        <div className="mt-2 h-5 flex items-center gap-x-3 text-[10px] font-mono text-[var(--text-secondary)] overflow-hidden whitespace-nowrap">
          {gezeigt ? (
            <>
              <span className="text-[#e8eaf0]">
                {parseTag(gezeigt.tag).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' }).toUpperCase()}
              </span>
              <span>{stunden(gezeigt.ist?.min || 0)}{gezeigt.plan?.min ? ` / ${stunden(gezeigt.plan.min)} PLANNED` : ''}</span>
              {gezeigt.ist?.tss > 0 && <span>{Math.round(gezeigt.ist.tss)} TSS</span>}
              {SPORTEN.filter(sp => gezeigt.ist?.jeSport[sp]).map(sp => (
                <span key={sp} style={{ color: DISCIPLINE_COLOR[sp] }}>
                  {(DISCIPLINE_LABEL[sp] || sp).toUpperCase()} {stunden(gezeigt.ist.jeSport[sp])}
                </span>
              ))}
            </>
          ) : (
            <span className="text-[var(--text-muted)] tracking-widest text-[9px]">FILLED = DONE · OUTLINE = PLANNED</span>
          )}
        </div>
      </div>

      {/* ── Ist gegen Plan ── */}
      {geplantMin > 0 && (
        <div className="mt-4 pt-4 border-t border-[#ffffff0d]">
          <div className="flex items-baseline justify-between gap-3 mb-2">
            <span className="text-[10px] font-mono tracking-widest text-[var(--text-secondary)]">
              <span className="text-[#e8eaf0] tabular-nums">{stunden(imPlanIst)}</span>
              <span className="text-[var(--text-muted)]"> / {stunden(geplantMin)} PLANNED</span>
              {ungeplant > 0 && <span className="text-[var(--text-muted)]"> · +{stunden(ungeplant)} UNPLANNED</span>}
            </span>
            <span className="text-3xl font-black leading-none tabular-nums"
                  style={{ ...DISPLAY, color: quote >= 100 ? STATUS_COLOR.green : '#f2f4f8' }}>
              {quote}<span className="text-sm font-mono text-[var(--text-muted)] ml-0.5">%</span>
            </span>
          </div>
          <div className="relative h-2.5 rounded-full" style={{ background: '#0a0c0f' }}>
            {/* Rahmen: der Plan */}
            <div className="absolute inset-y-0 left-0 rounded-full"
                 style={{ width: `${(geplantMin / leisteMax) * 100}%`, boxShadow: 'inset 0 0 0 1px #ffffff22' }} />
            {/* Füllung: was davon gemacht ist, nach Sportart */}
            <div className="absolute inset-y-0 left-0 flex rounded-full overflow-hidden transition-[width] duration-700 ease-out"
                 style={{ width: da ? `${((imPlanIst + ungeplant) / leisteMax) * 100}%` : 0 }}>
              {SPORTEN.filter(sp => jeSportIst[sp] > 0).map(sp => (
                <div key={sp} title={`${DISCIPLINE_LABEL[sp] || sp}: ${stunden(jeSportIst[sp])}`}
                     style={{ flexGrow: jeSportIst[sp], flexBasis: 0, background: DISCIPLINE_COLOR[sp] || DISCIPLINE_COLOR.other, opacity: 0.9 }} />
              ))}
              {ungeplant > 0 && (
                <div title={`Unplanned: ${stunden(ungeplant)}`}
                     style={{ flexGrow: ungeplant, flexBasis: 0, background: '#5b6475', backgroundImage: SCHRAFFUR }} />
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
