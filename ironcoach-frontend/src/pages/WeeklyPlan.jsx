import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  generatePlan, adjustPlanDays,
  getPlanByMonday, getPlannedByMonday, cancelPlan,
  getWeekMetrics, getNeuplanung, getDoppeltagZiehung, getSaison, getWochenBilanz,
} from '../services/api'
import { fehlerText } from '../utils/fehler'
import WeekCalendar from '../components/WeekCalendar'
import PlanExport from '../components/PlanExport'
import HealthStatus from '../components/HealthStatus'
import PlanOptionen from '../components/PlanOptionen'
import WunschKonsole from '../components/WunschKonsole'
import { montagMitVersatz } from '../utils/dates'
import { disciplineColor, phaseColor } from '../utils/colors'
import SaisonStrahl from '../components/leisten/SaisonStrahl'
import SollIstLeiste from '../components/leisten/SollIstLeiste'
import { DISPLAY, KOPF, Knopf, TITEL, toenung } from '../components/leisten/Kachel'
import { OPTIONEN, wunschText } from '../utils/trainingsoptionen'

const CARD = 'bg-[#111318] border border-[#1e2228] rounded-xl'

/** „19–25 OCT" wie der Zeitraum in THIS WEEK, statt „2026-10-19 – 2026-10-25". */
function zeitraumKurz(von, bis) {
  if (!von || !bis) return ''
  const a = new Date(`${von}T00:00:00`)
  const b = new Date(`${bis}T00:00:00`)
  const monat = d => d.toLocaleDateString('en-GB', { month: 'short' }).toUpperCase()
  return `${a.getDate()}${a.getMonth() !== b.getMonth() ? ` ${monat(a)}` : ''}–${b.getDate()} ${monat(b)}`
}
const LABEL = KOPF

/** planned_sessions → Kalenderformat. Trägt die id, damit Drag & Drop speichern kann. */
function fromPlannedSessions(rows) {
  return rows.map(r => ({
    id: r.id,
    day: r.day_name,
    date: r.planned_date,
    session_type: r.discipline,
    training_type: r.training_type,
    intensity: r.intensity,
    duration_min: r.duration_min,
    notes: r.notes,
    details: r.details,
    status: r.status,
    replacement: r.replacement,
    replacement_min: r.replacement_min,
    // Fehlten hier: Nach dem Neuladen war ein Ersatz nur aus Sportart oder
    // Intensität verschwunden, obwohl er gespeichert war.
    replacement_discipline: r.replacement_discipline,
    replacement_intensity: r.replacement_intensity,
    moved_from_date: r.moved_from_date,
    targets: {
      tss: r.target_tss,
      watts_low: r.target_watts_low,
      watts_high: r.target_watts_high,
      pace_low_s_per_km: r.target_pace_low_s_per_km,
      pace_high_s_per_km: r.target_pace_high_s_per_km,
      hr_zone: r.target_hr_zone,
      distance_km: r.target_distance_km,
    },
  }))
}

/** Fallback auf den Claude-Rohoutput — für Pläne ohne Projektion. Ohne id, also nicht speicherbar. */
function fromPlanContent(days) {
  return (days || []).map(d => ({
    id: null,
    day: d.day,
    date: d.date,
    session_type: d.session_type,
    training_type: d.training_type,
    duration_min: d.duration_min,
    notes: d.notes,
    details: d.details,
    targets: d.targets,
  }))
}

export default function WeeklyPlan() {
  const [plan, setPlan] = useState(null)
  const [planned, setPlanned] = useState(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [requests, setRequests] = useState('')
  // Angeklickte Wünsche für diese Woche, als Menge von Options-Kennungen.
  //
  // Nicht als Text im Eingabefeld: Ein Abwählen müsste dort einen Satz aus
  // dem String herausschneiden, und wer den Text zwischendurch bearbeitet,
  // bekommt Bruch — der halb gelöschte Satz ginge wörtlich an das Modell.
  // Zusammengesetzt wird erst beim Absenden (`wunschText`).
  //
  // Absichtlich nicht gespeichert: Jede Woche beginnt mit leerer Auswahl.
  const [gewaehlt, setGewaehlt] = useState(() => new Set())
  // Die Phase, wenn noch kein Plan existiert — sonst wären die Knöpfe genau
  // bei der ersten Planerstellung unsichtbar. `/api/metrics/week` liefert die
  // Phase der **laufenden** Woche; beim Vorblättern über eine Phasengrenze
  // kann sie um eine Stufe daneben liegen. Für die beiden Knopfarten (Doppeltag
  // in jeder Phase außer der Wettkampfwoche, Blockwoche im Aufbau) ist
  // das tragbar — der Coach prüft die Bedingung ohnehin selbst.
  const [metrikPhase, setMetrikPhase] = useState(null)
  const [error, setError] = useState(null)
  // Versatz in Kalenderwochen: 0 = laufende, -1 = vorige, +1 = kommende.
  //
  // Vorher stand hier die Planwochennummer. Die entsteht aus `max(1, …)` und
  // ist vor dem Beginn des Aufbaus für jedes Datum 1 — "eine Woche vor"
  // führte dort auf Nummer 2, für die es nie einen Plan gibt, während die
  // kommende Woche unter derselben 1 lag wie die laufende.
  // Sonntags auf die kommende Woche starten. Am letzten Tag einer Woche will
  // niemand mehr den Plan für diese Woche sehen oder erzeugen — und der Knopf
  // plant die Woche, die hier steht. Ohne das müsste man sonntagabends jedes
  // Mal erst vorblättern.
  const [versatz, setVersatz] = useState(() => (new Date().getDay() === 0 ? 1 : 0))
  const [currentWeek, setCurrentWeek] = useState(null)
  // Zieldauer statt fester 33: Eine 14-Wochen-Vorbereitung ließ sich bis
  // Woche 33 durchblättern (alles leer), eine 40-Wochen-Saison brach bei 33 ab.
  const [totalWeeks, setTotalWeeks] = useState(null)
  const [notFound, setNotFound] = useState(false)
  const [hinweis, setHinweis] = useState(null)
  // Die für die angezeigte Woche gezogene Doppeltag-Form (nur ohne Plan) und
  // der Schalter „ohne Doppeltag". Beides nicht gespeichert, siehe
  // `components/DoppeltagZiehung.jsx`.
  const [ziehung, setZiehung] = useState(null)
  const [ohneDoppeltag, setOhneDoppeltag] = useState(false)
  // Saison (Strahl in der Wochenkarte) und die Bilanz der angezeigten Woche
  // (geplant gegen absolviert, für die Leisten und die Tageskarten).
  const [saison, setSaison] = useState(null)
  const [bilanz, setBilanz] = useState(null)

  // Die Woche, die gerade angezeigt wird — als Ref, damit verspätete
  // Antworten und Zeitgeber wissen, ob sie noch gemeint sind. Vorher lud ein
  // Nachladen nach 30 Sekunden die Woche, die beim Auslösen angezeigt war,
  // auch wenn längst weitergeblättert wurde.
  const versatzRef = useRef(versatz)
  useEffect(() => { versatzRef.current = versatz }, [versatz])

  const loadPlanned = useCallback(async (offset) => {
    // Ohne Angabe die angezeigte Woche. Der Kalender ruft das nach einem
    // Tausch ohne Argument auf — vorher wurde dann die aktuelle Woche
    // geladen, und unter der Kachel der nächsten Woche standen die Einheiten
    // dieser.
    const woche = offset ?? versatzRef.current
    // Die Bilanz neben den Einheiten, mit eigenem Fehlerfang: Fehlt sie,
    // zeigt der Kalender die Dauer wie bisher.
    getWochenBilanz(montagMitVersatz(woche))
      .then(({ data }) => { if (woche === versatzRef.current) setBilanz(data) })
      .catch(() => { if (woche === versatzRef.current) setBilanz(null) })
    try {
      const resp = await getPlannedByMonday(montagMitVersatz(woche))
      if (woche !== versatzRef.current) return
      setPlanned(resp.data?.length ? resp.data : null)
    } catch (e) {
      // 503 = Projektion noch nicht migriert. Kein Fehler für den Nutzer,
      // der Kalender fällt dann auf plan_content zurück.
      setPlanned(null)
    }
  }, [])

  const load = useCallback(async (offset = 0) => {
    setLoading(true)
    setError(null)
    setNotFound(false)
    try {
      // Immer über den Montag — dieselbe Auswahl wie der Kalender, und nur
      // diese Antwort sagt auch, ob die Woche stornierbar ist.
      const resp = await getPlanByMonday(montagMitVersatz(offset))
      if (offset !== versatzRef.current) return
      setPlan(resp.data)
      // Die erste Antwort definiert, welche Woche "aktuell" ist.
      setCurrentWeek(prev => (prev == null && offset === 0 ? resp.data.week_number : prev))
      await loadPlanned(offset)
    } catch (e) {
      if (offset !== versatzRef.current) return
      if (e.response?.status === 404) {
        setPlan(null)
        setPlanned(null)
        setNotFound(true)
      } else {
        setError(fehlerText(e, 'Plan konnte nicht geladen werden.'))
      }
    } finally {
      setLoading(false)
    }
  }, [loadPlanned])

  // Liegt für die angezeigte Woche ein Plan, ist "anpassen" gemeint, nicht
  // "neu bauen". Vorher ging beides an dieselbe Stelle: Wer "ändere Donnerstag
  // bis Sonntag" eintippte, bekam sieben neu geschriebene Tage.
  const anpassen = async () => {
    setGenerating(true)
    setError(null)
    try {
      const { data } = await adjustPlanDays(wunschText(gewaehlt, requests), zielMontag)
      if (data.status === 'angepasst') {
        setRequests('')
        setGewaehlt(new Set())
        setHinweis({
          ok: true,
          text: `${data.geaendert.length} Tag(e) angepasst: ${data.geaendert.join(', ')}`
            + (data.abgewiesen?.length ? ` · nicht geändert: ${data.abgewiesen.join(', ')}` : '')
            + (data.hinweis ? ` — ${data.hinweis}` : ''),
        })
        await load(versatz)
      } else {
        setHinweis({ ok: false, text: data.hinweis || 'Es wurde nichts geändert.' })
      }
    } catch (e) {
      setError(fehlerText(e, 'Anpassung fehlgeschlagen'))
    } finally {
      setGenerating(false)
    }
  }

  const generate = async () => {
    setGenerating(true)
    setError(null)
    try {
      // Für die Woche, die gerade angezeigt wird — nicht blind für heute.
      const resp = await generatePlan(
        wunschText(gewaehlt, requests), zielMontag,
        // Auch eine Blockwoche ohne: fünf harte Einheiten und dazu ein
        // verdichteter Tag wären mehr, als die Blockwoche vorsieht.
        !(ohneDoppeltag || doppelGewuenscht || ganzeWocheGewaehlt),
      )
      setPlan(resp.data)
      setRequests('')
      setGewaehlt(new Set())
      setOhneDoppeltag(false)
      // Danach die Einheiten derselben Woche nachladen. Vorher stand hier
      // `loadPlanned(null)`: Der neue Plan erschien in der Kachel, während
      // darunter noch die Einheiten der vorigen Woche standen — es sah aus,
      // als wäre der alte Plan verschwunden.
      await loadPlanned(versatz)
    } catch (e) {
      setError(fehlerText(e, 'Plan konnte nicht erstellt werden.'))
    } finally {
      setGenerating(false)
    }
  }

  useEffect(() => { load(versatz) }, [versatz, load])

  // Stornieren: null | 'frage' | 'laeuft'. Beim Blättern zurückgesetzt —
  // eine offene Rückfrage gehört zu der Woche, für die sie gestellt wurde.
  const [storno, setStorno] = useState(null)
  useEffect(() => { setStorno(null) }, [versatz])
  // Escape schließt die Rückfrage, egal wo der Fokus gerade steht.
  useEffect(() => {
    if (storno !== 'frage') return
    const taste = e => { if (e.key === 'Escape') setStorno(null) }
    document.addEventListener('keydown', taste)
    return () => document.removeEventListener('keydown', taste)
  }, [storno])

  // Ob storniert werden kann, sagt der Server (`plan.stornierbar`, nach
  // `services/plan_storno.py`). Vorher rechnete die Seite selbst — mit einer
  // anderen Regel: Eine künftige Woche mit einer ersetzten Einheit galt hier
  // als gesperrt, am Server nicht, und ohne geladene Einheiten erschien der
  // Knopf auch dort, wo der Server ablehnte.
  const stornierbar = !!plan && plan.stornierbar !== false && versatz >= 0
  const stornoGrund = plan?.stornierbar === false ? plan.storno_grund : null

  const neuplanungVerfolgen = useCallback(async () => {
    setHinweis({ ok: true, text: 'Der Plan wird an die Meldung angepasst …' })
    for (let i = 0; i < 40; i++) {
      await new Promise(r => setTimeout(r, 5000))
      try {
        const { data } = await getNeuplanung()
        if (data.status === 'fertig') {
          setHinweis({ ok: true, text: `Der Plan für die Woche ab ${data.montag} ist angepasst.` })
          load(versatzRef.current)
          return
        }
        if (data.status === 'fehlgeschlagen' || data.status === 'unbekannt') {
          setHinweis({ ok: false, text: data.detail || 'Der Plan wurde nicht angepasst.' })
          return
        }
      } catch { /* weiter versuchen */ }
    }
    setHinweis({ ok: false, text: 'Die Anpassung dauert ungewöhnlich lange — sieh gleich noch einmal nach.' })
  }, [load])

  const stornieren = async () => {
    setStorno('laeuft')
    setError(null)
    try {
      const { data } = await cancelPlan(zielMontag)
      setStorno(null)
      setHinweis({ ok: true, text: data.message })
      await load(versatz)
    } catch (e) {
      setStorno(null)
      setError(fehlerText(e, 'Stornieren fehlgeschlagen'))
    }
  }

  // Die Phase für die Knopfreihe, wenn noch kein Plan vorliegt. Einmal beim
  // Öffnen; sie ändert sich nicht im Minutentakt, und ein Fehlschlag darf die
  // Seite nicht beeinträchtigen — dann fehlen eben die Knöpfe.
  useEffect(() => {
    let abgebrochen = false
    getWeekMetrics()
      .then(({ data }) => { if (!abgebrochen) setMetrikPhase(data?.phase ?? null) })
      .catch(() => {})
    getSaison()
      .then(({ data }) => { if (!abgebrochen) setSaison(data) })
      .catch(() => {})
    return () => { abgebrochen = true }
  }, [])

  // Welche Phase die Knöpfe filtert: die des Plans, sonst die der Metriken.
  const knopfPhase = plan?.plan_phase || metrikPhase

  // Eine Blockwoche ist eine **ganze** Woche, keine Tagesänderung.
  //
  // `/plan/anpassen` liefert nur geänderte Tage und verlangt ausdrücklich,
  // nicht zwei harte Einheiten hintereinander zu setzen — das Gegenteil einer
  // Blockwoche mit fünf. Ein solcher Wunsch muss deshalb über einen neuen
  // Wochenplan laufen, auch wenn schon einer existiert.
  const ganzeWocheGewaehlt = useMemo(
    () => OPTIONEN.some(o => o.ganzeWoche && gewaehlt.has(o.id)),
    [gewaehlt]
  )

  // Ein gewählter Doppeltag-Knopf ersetzt die gezogene Form — sonst bekäme die
  // Woche zwei Doppeltage, und das hat niemand bestellt.
  const doppelGewuenscht = useMemo(
    () => [...gewaehlt].some(id => id.startsWith('doppel_')),
    [gewaehlt]
  )

  const absenden = () => {
    if (plan && ganzeWocheGewaehlt) {
      const ok = window.confirm(
        'Eine Blockwoche verändert die ganze Woche, nicht einzelne Tage — '
        + 'der Plan dieser Woche wird dafür neu erstellt. Fortfahren?'
      )
      if (!ok) return
      return generate()
    }
    return plan ? anpassen() : generate()
  }

  const absendbar = !generating
    && (!plan || requests.trim() !== '' || gewaehlt.size > 0)

  const shownWeek = plan?.week_number ?? currentWeek
  // Gibt es für die betrachtete Woche keinen Plan, ist keine Wochennummer
  // bekannt — die des geladenen Plans wäre die einer anderen Woche. Dann
  // steht dort der Montag statt einer Nummer, die nicht stimmt.
  const wochenMarke = plan
    // Negative Nummern sind die Wochen vor dem Aufbaubeginn: 0 ist die Woche
    // unmittelbar davor, -7 die achte davor. Der Zusatz erklärt das, ohne
    // dass man die Rechnung kennen muss.
    ? (plan.week_number < 1 ? `WK ${plan.week_number} · PREP` : `WK ${plan.week_number}`)
    : new Date(montagMitVersatz(versatz) + 'T00:00:00').toLocaleDateString('de-DE',
        { day: '2-digit', month: '2-digit' })
  // Am Versatz erkannt, nicht am Vergleich der Wochennummern: Vor dem
  // Beginn des Aufbaus tragen laufende und kommende Woche dieselbe Nummer,
  // und die Seite hielte die kommende für die laufende.
  const isCurrent = versatz === 0
  // Eine vorbei gegangene Woche: nichts mehr zu planen oder zu ziehen. Vorher
  // bot die Konsole dort „Plan erstellen" an, und die Urne schlug bei Justin
  // für eine Woche, bevor er die App hatte, „langen Lauf teilen" vor. Das
  // Backend lehnt beides für vergangene Wochen ab (`routers/plan._vergangen`).
  const vergangen = versatz < 0

  // Der Montag der angezeigten Woche — Ziel des Erstellen-Knopfes und
  // gleichzeitig seine Beschriftung.
  const zielMontag = montagMitVersatz(versatz)

  // Die Ziehung nur laden, solange die Woche keinen Plan hat: Danach steht der
  // Doppeltag im Plan selbst. Beim Blättern zurücksetzen, damit „ohne
  // Doppeltag" nicht in die nächste Woche mitwandert.
  useEffect(() => {
    setOhneDoppeltag(false)
    if (!notFound || vergangen) { setZiehung(null); return }
    let aktuell = true
    getDoppeltagZiehung(zielMontag)
      .then(({ data }) => { if (aktuell) setZiehung(data) })
      // Ohne Ziehung bleibt die Kachel wie bisher — der Plan entsteht trotzdem.
      .catch(() => { if (aktuell) setZiehung(null) })
    return () => { aktuell = false }
  }, [zielMontag, notFound, vergangen])

  const zielSpanne = (() => {
    const mo = new Date(zielMontag + 'T00:00:00')
    const so = new Date(mo); so.setDate(mo.getDate() + 6)
    const f = d => d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })
    return `${f(mo)}–${f(so)}`
  })()

  // Bevorzugt die normalisierten Einheiten — nur die tragen ids und Zielwerte.
  const calendarDays = useMemo(
    () => (planned ? fromPlannedSessions(planned) : fromPlanContent(plan?.plan_content?.days)),
    [planned, plan]
  )

  // Geplant gegen absolviert je Disziplin. Nur für die laufende und
  // vergangene Wochen: In einer kommenden Woche hieße jede Leiste „0 / 240",
  // und das sähe nach Versäumnis aus statt nach Plan.
  const bilanzZeilen = (bilanz?.disziplinen || []).filter(d => d.geplant_min > 0 || d.absolviert_min > 0)
  const bilanzSkala = Math.max(0, ...bilanzZeilen.map(d => Math.max(d.geplant_min, d.absolviert_min)))
  const wochenBilanz = versatz <= 0 && bilanzZeilen.some(d => d.geplant_min > 0) ? (
    <div className="mb-4 rounded-lg p-3" style={{ background: '#0a0c0f99', border: '1px solid #1e2228' }}>
      <div className="flex items-baseline justify-between mb-2.5">
        <span className={LABEL}>PLANNED / DONE</span>
        {bilanz.tss?.soll > 0 && (
          <span className="text-[10px] font-mono tabular-nums text-[var(--text-secondary)]">
            TSS <span className="text-[#e8eaf0]">{Math.round(bilanz.tss.ist)}</span> / {Math.round(bilanz.tss.soll)}
          </span>
        )}
      </div>
      <div className="grid gap-x-5 gap-y-2.5 sm:grid-cols-2">
        {bilanzZeilen.map(d => (
          <SollIstLeiste
            key={d.discipline}
            name={d.discipline.toUpperCase()}
            soll={d.geplant_min}
            ist={d.absolviert_min}
            farbe={disciplineColor(d.discipline)}
            skala={bilanzSkala}
          />
        ))}
      </div>
    </div>
  ) : null

  return (
    <div className="space-y-6 page-enter">

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-baseline gap-x-3 gap-y-2 flex-wrap">
          <h1
            className="text-3xl font-black tracking-tight text-[#e8eaf0] whitespace-nowrap"
            style={{ fontFamily: 'Barlow Condensed, sans-serif' }}
          >
            WEEKLY PLAN
          </h1>

          {/* Wochennavigation — ein im Voraus erstellter Plan war sonst bis
              zum Wochenwechsel unsichtbar.

              Ohne Bedingung: Sie hing daran, dass eine Wochennummer bekannt
              ist, und die wird erst gesetzt, wenn ein Plan geladen werden
              konnte. Wer für die laufende Woche keinen Plan hat, bekam
              dadurch gar keine Pfeile — und damit keinen Weg zu der Woche,
              in der einer liegt. Gerade dann braucht man sie. */}
          <div className="flex items-center gap-1">
              {[
                { dir: -1, label: '‹', title: 'Woche zurück' },
                { dir: 1, label: '›', title: 'Woche vor' },
              ].map(({ dir, label, title }, i) => (
                <button
                  key={dir}
                  title={title}
                  // Nach vorn genau eine Woche: Weiter gibt es nichts zu
                  // sehen, weil Pläne immer nur für die kommende Woche
                  // entstehen. Nach hinten offen — dort liegt die Historie.
                  // Gesperrt, solange ein Storno läuft: Dessen Neuladen gehört
                  // zur Woche, in der es ausgelöst wurde. Wer währenddessen
                  // weiterblätterte, bekam danach die stornierte Woche über
                  // die gerade angezeigte gelegt — mit „kein Plan".
                  disabled={(dir === 1 && versatz >= 1) || storno === 'laeuft'}
                  onClick={() => setVersatz(v => Math.min(1, v + dir))}
                  className={`px-2 py-0.5 rounded-md font-mono text-[var(--text-secondary)] transition-colors ${i === 1 ? 'order-3' : ''} ${(dir === 1 && versatz >= 1) || storno === 'laeuft' ? 'opacity-30 cursor-not-allowed' : 'hover:text-[#e8eaf0] hover:bg-[#ffffff0a]'}`}
                  style={{ border: '1px solid #1e2228' }}
                >
                  {label}
                </button>
              ))}
              <span className="text-xs font-mono tracking-[0.2em] order-2 px-2"
                    style={{ color: versatz === 0 ? 'var(--text-muted)' : '#e8eaf0' }}>
                {wochenMarke}
                {versatz === 1 && <span className="text-[9px] ml-1.5 text-[var(--text-muted)]">NEXT</span>}
                {versatz < 0 && <span className="text-[9px] ml-1.5 text-[var(--text-muted)]">PAST</span>}
              </span>
          </div>

          {!isCurrent && (
            <Knopf onClick={() => setVersatz(0)} disabled={storno === 'laeuft'}>
              BACK TO THIS WEEK
            </Knopf>
          )}
        </div>

        {/* Rechts im Kopf nur noch der Export. Wünsche, Doppeltag und der
            Erstellen-Knopf stehen in der Konsole darunter (`WunschKonsole`) —
            in der Kopfzeile brachen sie je nach Breite irgendwo um. */}
        {plan && (
          <div className="flex gap-2 items-center">
            <PlanExport plan={plan} />
          </div>
        )}
      </div>

      {/* Gesundheit steht über dem Plan: wer krank ist, muss zuerst wissen,
          ob der Plan darunter überhaupt noch gilt. */}
      <HealthStatus variant="bar" onChanged={(antwort) => {
        load(versatzRef.current)
        // Die Neuplanung läuft im Hintergrund. Statt nach fester Zeit einmal
        // nachzusehen, wird ihr Stand abgefragt — und gesagt, wenn sie nicht
        // geklappt hat. Vorher kam die Meldung „Plan wird angepasst" auch
        // dann, wenn das Guthaben aufgebraucht war.
        if (antwort?.plan_wird_angepasst) neuplanungVerfolgen()
      }} />

      {/* Gesundheit davor: Wer krank ist, soll das sehen, bevor er plant. */}
      {!vergangen && <WunschKonsole
        plan={plan}
        phase={knopfPhase}
        zielSpanne={zielSpanne}
        modus={!plan ? 'CREATE PLAN' : ganzeWocheGewaehlt ? 'REBUILD WEEK' : 'ADJUST DAYS'}
        requests={requests}
        onRequests={setRequests}
        vorschau={wunschText(gewaehlt, requests)}
        gewaehlt={gewaehlt}
        onToggle={id => setGewaehlt(v => {
          const n = new Set(v)
          n.has(id) ? n.delete(id) : n.add(id)
          return n
        })}
        ziehung={ziehung}
        ohneDoppeltag={ohneDoppeltag}
        ersetzt={doppelGewuenscht || ganzeWocheGewaehlt}
        onDoppeltag={() => setOhneDoppeltag(v => !v)}
        absendbar={absendbar}
        absenden={absenden}
        generating={generating}
      />}

      {hinweis && (
        <div className="rounded-xl px-4 py-3 font-mono text-[11px] flex items-start gap-3"
             style={{
               background: hinweis.ok ? '#10b98112' : '#f59e0b14',
               border: `1px solid ${hinweis.ok ? '#10b98133' : '#f59e0b40'}`,
               color: hinweis.ok ? '#10b981' : '#f59e0b',
             }}>
          <span className="flex-1">{hinweis.text}</span>
          <button onClick={() => setHinweis(null)} className="opacity-60 hover:opacity-100">✕</button>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="rounded-xl p-4 font-mono text-sm" style={{ background: '#ef444415', border: '1px solid #ef444430', color: '#ef4444' }}>
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="text-[var(--text-muted)] font-mono text-[10px] py-8 text-center tracking-[0.25em]">
          LOADING…
        </div>
      )}

      {/* Empty state */}
      {!loading && !plan && !error && (
        <div className={`${CARD} p-10 text-center`}>
          <div
            className="text-2xl font-black text-[var(--text-muted)] mb-2"
            style={{ fontFamily: 'Barlow Condensed, sans-serif' }}
          >
            {notFound && !isCurrent ? 'NO PLAN FOR THIS WEEK' : 'NO PLAN YET'}
          </div>
          <p className="text-sm font-mono text-[var(--text-muted)]">
            {vergangen
              ? 'Für diese Woche gab es keinen Plan. Sie ist vorbei, geplant wird nur noch ab dieser Woche.'
              : notFound && !isCurrent
              ? 'Für diese Woche wurde noch kein Plan erstellt.'
              : 'Mit „Plan erstellen“ entsteht der Wochenplan für diese Woche.'}
          </p>
        </div>
      )}

      {/* Plan */}
      {plan && (
        <div className="space-y-5">

          {/* Coaching brief card */}
          {/* Getönt in der Phasenfarbe wie THIS WEEK in seinen Sportfarben —
              vorher ein Cyan-Streifen links und ein Lichtkegel. */}
          <div className="rounded-xl p-5 border relative overflow-hidden" style={toenung(phaseColor(plan.plan_phase))}>
            <div>
              <div className="mb-1"><span className={TITEL}>COACHING BRIEF</span></div>
              <div className="flex flex-wrap items-end gap-x-6 gap-y-3 mb-4 mt-3">
                <div>
                  <div className={LABEL}>PHASE</div>
                  <div className="text-2xl font-black leading-none mt-1.5"
                       style={{ ...DISPLAY, color: phaseColor(plan.plan_phase) }}>
                    {plan.plan_phase?.toUpperCase()}
                  </div>
                </div>
                <div className="pl-6 border-l border-[#ffffff0f]">
                  <div className={LABEL}>PERIOD</div>
                  <div className="text-2xl font-black leading-none mt-1.5 tabular-nums text-[#f2f4f8]" style={DISPLAY}>
                    {zeitraumKurz(plan.week_start, plan.week_end)}
                  </div>
                </div>
                {/* Stornieren: zurückhaltend, weil es löscht. Vergangene
                    Wochen bekommen den Knopf gar nicht — sie bleiben als
                    Protokoll. In der laufenden Woche mit erledigten Tagen
                    steht er da, sagt aber, warum er nicht geht. */}
                {versatz >= 0 && storno === null && (
                  <Knopf
                    art={stornierbar ? 'gefahr' : 'leise'}
                    onClick={() => setStorno('frage')}
                    disabled={!stornierbar}
                    title={stornierbar ? 'Plan dieser Woche stornieren' : (stornoGrund || '')}
                    className="ml-auto self-start"
                  >
                    CANCEL PLAN
                  </Knopf>
                )}
              </div>

              {/* Der Grund als Text, nicht nur als Tooltip — auf dem Telefon
                  gibt es keinen Tooltip, und ein grauer Knopf ohne Erklärung
                  sieht nach einem Fehler aus. */}
              {versatz >= 0 && storno === null && !stornierbar && stornoGrund && (
                <p className="-mt-1 mb-3 text-[11px] font-mono text-[var(--text-muted)] leading-relaxed">
                  Stornieren geht nicht: {stornoGrund}
                </p>
              )}

              {storno !== null && (
                <div
                  className="mb-3 rounded-lg px-3 py-2.5 flex items-center gap-3 flex-wrap"
                  style={{ background: '#ef44440f', border: '1px solid #ef444455' }}
                >
                  <p className="text-[13px] text-[#e8eaf0] leading-snug flex-1 min-w-[14rem]">
                    Plan für {zielSpanne} stornieren? Plan und alle geplanten
                    Einheiten dieser Woche werden gelöscht
                    {plan.plan_phase === 'Benchmark' ? ', die Testwoche wird freigegeben' : ''},
                    die Notiz in Obsidian wird entfernt. Danach kannst du die Woche neu erstellen.
                  </p>
                  <div className="flex gap-2">
                    <Knopf art="gefahr" onClick={stornieren} disabled={storno === 'laeuft'}>
                      {storno === 'laeuft' ? 'CANCELLING…' : 'YES, CANCEL'}
                    </Knopf>
                    {/* Der Fokus liegt auf dem harmlosen Knopf: Ein Enter direkt
                        nach dem Öffnen soll nicht den Plan löschen. */}
                    <Knopf onClick={() => setStorno(null)} disabled={storno === 'laeuft'} autoFocus>
                      KEEP
                    </Knopf>
                  </div>
                </div>
              )}

              {/* Wo diese Woche in der Saison liegt — die angezeigte eingerahmt,
                  die heutige als Strich. Ohne Kopf: Phase und Zeitraum stehen
                  oben schon. */}
              {saison?.phasen?.length > 0 && (
                <div className="mb-4">
                  <SaisonStrahl
                    saison={saison}
                    kompakt
                    ohneKopf
                    fokus={{ von: plan.week_start, bis: plan.week_end }}
                  />
                </div>
              )}

              {wochenBilanz}

              {plan.plan_content?.coaching_comment && (
                <p className="text-sm text-[#e8eaf0] leading-relaxed">
                  {plan.plan_content.coaching_comment}
                </p>
              )}

              {plan.adjustments_applied?.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {plan.adjustments_applied.map((adj, i) => (
                    <span
                      key={i}
                      className="text-[11px] font-mono px-2 py-0.5 rounded-md text-[var(--text-secondary)]"
                      style={{ background: '#0d0f14', border: '1px solid #1e2228' }}
                    >
                      {adj}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Calendar */}
          <WeekCalendar
            days={calendarDays}
            istJeEinheit={bilanz?.einheiten}
            onPersisted={() => loadPlanned(versatzRef.current)}
          />

          {/* Was sich der Athlet wünschen kann — direkt unter der Woche, weil
              die Entscheidung dort fällt. Ein Klick übernimmt den Wunsch nach
              oben, statt ihn nur nachzuschlagen. */}
          <div className="mt-4">
            <PlanOptionen
              phase={knopfPhase}
              onWunsch={o => {
                // Hat die Form einen Knopf in der Reihe oben, wird dieser
                // gesetzt — nicht Text angehängt. Sonst zeigten Panel und
                // Knopfreihe verschiedene Zustände für dieselbe Entscheidung,
                // und ein Abwählen wirkte nur an einer der beiden Stellen.
                if (o.kuerzel) {
                  setGewaehlt(v => new Set(v).add(o.id))
                } else {
                  setRequests(v => (v.trim() ? `${v.trim()} ${o.wunsch}` : o.wunsch))
                }
                window.scrollTo({ top: 0, behavior: 'smooth' })
              }}
            />
          </div>
        </div>
      )}

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 0.3; transform: scale(0.8); }
          50% { opacity: 1; transform: scale(1); }
        }
      `}</style>
    </div>
  )
}
