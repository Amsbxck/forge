import { useEffect, useState } from 'react'
import { getWeekMetrics, getLatestHrv, getHrv, getHrvRange, getHrvLage, getSaison, getSessions, getSessionsSeit, getProfile, getIntakeStatus, getMe, getFtpCheck, getPmc, getBenchmarkTiming, getPlannedByMonday, getWochenBilanz } from '../services/api'
import HRVInput from '../components/HRVInput'
import HealthStatus from '../components/HealthStatus'
import HRVHistoryChart from '../components/HRVHistoryChart'
import PerformanceChart from '../components/PerformanceChart'
import { HRV_URTEIL } from '../components/HrvAmpel'
import SaisonStrahl from '../components/leisten/SaisonStrahl'
import WocheHero from '../components/leisten/WocheHero'
import SegmentLeiste from '../components/leisten/SegmentLeiste'
import SpannenSkala, { hrvZonen } from '../components/leisten/SpannenSkala'
import Onboarding from '../components/Onboarding'
import IntakeDialog from '../components/IntakeDialog'
import EmailBestaetigung from '../components/EmailBestaetigung'
import FtpHinweis from '../components/FtpHinweis'
import Glossary from '../components/Glossary'
import TodayCard from '../components/TodayCard'
import SportIcon from '../components/SportIcon'
import { isoTag, kalenderwoche } from '../utils/dates'
import SessionDetail from '../components/SessionDetail'
import ReflectionEditor from '../components/ReflectionEditor'
import { calculatePMC, formColor, formLabel } from '../components/PerformanceChart'
import { useNavigate } from 'react-router-dom'

import {
  DISCIPLINE_COLOR, DISCIPLINE_LABEL, HR_ZONE_COLOR, HR_ZONE_LABEL,
  STATUS_COLOR as HRV_COLOR, disciplineColor, disciplineLabel,
} from '../utils/colors'

const HRV_TEXT = {
  green: 'Train as planned',
  yellow: 'Possible — lower the intensity',
  red: 'Easy or rest day',
  keine: 'Not measured today',
}

// ─── Glossary ─────────────────────────────────────────────────────────────────

// ─── Main Dashboard ───────────────────────────────────────────────────────────

export default function Dashboard() {
  const navigate = useNavigate()
  // Angeklickte Einheit — öffnet die Detailansicht mit dem Reflexionsfeld.
  const [offeneEinheit, setOffeneEinheit] = useState(null)
  // Angeklickte Sportart filtert die Einheitenliste darunter.
  const [gewaehlteDisziplin, setGewaehlteDisziplin] = useState(null)
  const [metrics, setMetrics] = useState(null)
  const [hrv, setHrv] = useState(null)
  const [hrvHistory, setHrvHistory] = useState([])
  const [sessions, setSessions] = useState([])
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  // Willkommensfenster für neue Konten. `null` heißt: noch nicht geprüft —
  // ohne diesen dritten Zustand blitzte das Fenster bei jedem Laden kurz auf.
  const [intakeFaellig, setIntakeFaellig] = useState(null)
  // Konto nur für den Bestätigungshinweis. Getrennt vom Profil, weil die
  // Bestätigung am Konto hängt und nicht am Athletenprofil.
  const [konto, setKonto] = useState(null)
  const [ftpBefund, setFtpBefund] = useState(null)
  const [pmcServer, setPmcServer] = useState(null)
  // Ersatz, falls die Formkurve vom Server ausfällt — aus allen Einheiten des
  // letzten Jahres, nicht aus den 50 neuesten: Mit 50 begann die Fitness bei
  // null am Tag der 50. Einheit, und die Form stand viel zu hoch.
  const [pmcErsatz, setPmcErsatz] = useState(null)
  const [hrvGrenzen, setHrvGrenzen] = useState(null)
  // Mit Garmin kommt die HRV automatisch, und das Backend lehnt die
  // Handeingabe ab (409). Der Zustand kommt aus `GET /hrv/range`, das hier
  // ohnehin geladen wird — kein zusätzlicher Aufruf. `null` heißt „noch
  // unbekannt": Bis die Antwort da ist, steht an der Stelle nichts, sonst
  // blitzte bei Garmin-Athleten kurz die Handeingabe auf.
  const [garminVerbunden, setGarminVerbunden] = useState(null)
  const [testTermin, setTestTermin] = useState(null)
  // Für die Leisten: Saison (Strahl im Kopf) und HRV-Lage (Ø 7 Tage in der
  // Ampelfarbe, dieselbe Rechnung wie in der Doppeltag-Kachel).
  const [saison, setSaison] = useState(null)
  const [hrvLage, setHrvLage] = useState(null)

  // Für die THIS-WEEK-Kachel: Plan, Bilanz und acht Wochen Verlauf. Eigener
  // Effekt statt im `load`: Fehlt einer davon, fällt nur sein Teil der
  // Kachel weg, die übrige Seite lädt unberührt.
  const [geplantWoche, setGeplantWoche] = useState(null)
  const [bilanzWoche, setBilanzWoche] = useState(null)
  const [verlaufAcht, setVerlaufAcht] = useState(null)
  const wochenMontag = kalenderwoche().von
  useEffect(() => {
    const m = new Date(`${wochenMontag}T00:00:00`)
    m.setDate(m.getDate() - 49)
    getPlannedByMonday(wochenMontag).then(r => setGeplantWoche(r.data || [])).catch(() => {})
    getWochenBilanz(wochenMontag).then(r => setBilanzWoche(r.data)).catch(() => {})
    getSessionsSeit(isoTag(m)).then(r => setVerlaufAcht(r.data || [])).catch(() => {})
  }, [wochenMontag])

  const load = async () => {
    setLoading(true)
    // Vor dem Promise.all und nicht danach: Scheitert `getWeekMetrics` (es hat
    // als einziges keinen eigenen Fehlerfang), springt `load` in den äußeren
    // catch. Stünde dieser Aufruf dahinter, bliebe `garminVerbunden` auf `null`
    // und weder Handeingabe noch Garmin-Zeile erschienen.
    getHrvRange().then(({ data }) => {
      setHrvGrenzen(data?.grenzen || null)
      setGarminVerbunden(!!data?.garmin_verbunden)
    }).catch(() => {
      setHrvGrenzen(null)
      // Im Zweifel die Handeingabe zeigen. Ist Garmin doch verbunden,
      // lehnt das Backend mit 409 und verständlichem Text ab.
      setGarminVerbunden(false)
    })
    try {
      const [m, h, hh, s, p] = await Promise.all([
        getWeekMetrics(),
        getLatestHrv().catch(() => ({ data: null })),
        getHrv(90).catch(() => ({ data: [] })),
        getSessions().catch(() => ({ data: [] })),
        getProfile().catch(() => ({ data: null })),
      ])
      // Bewusst nach den übrigen Daten und mit eigenem Fehlerfang: Ein
      // Ausfall dieser Abfrage darf das Dashboard nicht leer lassen.
      getIntakeStatus()
        .then(({ data }) => setIntakeFaellig(!!data?.faellig))
        .catch(() => setIntakeFaellig(false))
      getMe().then(({ data }) => setKonto(data)).catch(() => setKonto(null))
      // Eigener Aufruf mit eigenem Fehlerfang: Die Prüfung liest die
      // Leistungsdaten mehrerer Fahrten; ein Ausfall darf das Dashboard nicht
      // aufhalten.
      getFtpCheck().then(({ data }) => setFtpBefund(data?.befund || null)).catch(() => setFtpBefund(null))
      getPmc().then(({ data }) => setPmcServer(Array.isArray(data) ? data : null)).catch(() => {
        setPmcServer(null)
        const vor = new Date(); vor.setDate(vor.getDate() - 365)
        getSessionsSeit(isoTag(vor)).then(({ data }) => setPmcErsatz(calculatePMC(data))).catch(() => {})
      })
      getBenchmarkTiming().then(({ data }) => setTestTermin(data)).catch(() => setTestTermin(null))
      // Eigene Fehlerfänge: Fehlen Strahl oder Lage, bleibt das übrige
      // Dashboard stehen — die Kachel fällt dann auf die Tageswerte zurück.
      getSaison().then(({ data }) => setSaison(data)).catch(() => setSaison(null))
      getHrvLage().then(({ data }) => setHrvLage(data || null)).catch(() => setHrvLage(null))
      setMetrics(m.data)
      setHrv(h.data)
      setHrvHistory(Array.isArray(hh.data) ? hh.data : [])
      setSessions(Array.isArray(s.data) ? s.data : [])
      setProfile(p.data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  if (loading) return (
    <div className="flex items-center justify-center py-20 text-[var(--text-secondary)]">
      <div className="text-sm font-mono tracking-widest">LÄDT…</div>
    </div>
  )

  // Nur eine Messung von **heute** gibt die Ampel für heute. Vorher galt der
  // letzte Wert beliebigen Alters, und ohne jede Messung stand Grün da.
  const heuteGemessen = hrv?.measured_at === isoTag(new Date())
  const status = heuteGemessen && hrv?.hrv_status ? hrv.hrv_status : 'keine'
  const statusColor = HRV_COLOR[status] || '#8a909e'
  // Die große Zahl ist der 7-Tage-Schnitt in der Farbe, mit der die Urne
  // gewichtet (jüngste Messung der letzten drei Tage). Vorher stand hier ein
  // Ring, dessen Füllung die Lage in der Spanne zeigen sollte — ohne jede
  // Marke, wo grün beginnt, ließ sich die Füllung nicht lesen. Die Empfehlung
  // darunter bleibt bei der Messung von heute.
  const lageFarbe = HRV_COLOR[hrvLage?.status] || statusColor
  const spanne = hrvLage?.spanne || hrvGrenzen

  // Form (TSB) aus derselben Funktion wie das Diagramm weiter unten — eine
  // zweite Rechnung würde früher oder später eine andere Zahl zeigen.
  // Der Durchschnittspuls gehört zur Wochenbilanz, nicht zur Bereitschaft:
  // er beschreibt, wie hart trainiert wurde, nicht wie erholt man ist.
  const avgHr = metrics?.avg_hr
  const hrZoneIndex = !avgHr || !profile ? null
    : avgHr <= profile.z1_hr_max ? 0
    : avgHr <= profile.z2_hr_max ? 1
    : avgHr <= profile.z3_hr_max ? 2
    : avgHr <= profile.z4_hr_max ? 3
    : 4
  const hrColor = hrZoneIndex == null ? '#e8eaf0' : HR_ZONE_COLOR[hrZoneIndex]

  // Serverwert zuerst, lokale Rechnung nur als Rückfall — genau wie im
  // Diagramm weiter unten. Vorher rechnete die Kachel immer selbst, und
  // sobald sich die beiden Formeln unterschieden, zeigten Kachel und
  // Diagramm verschiedene Zahlen für denselben Tag. Zwei Rechnungen für
  // eine Grösse laufen früher oder später auseinander.
  const pmc = pmcServer?.length ? pmcServer : (pmcErsatz || [])
  const form = pmc.length ? pmc[pmc.length - 1].tsb : null
  const formFarbe = formColor(form)
  const formText = formLabel

  const fmtTime = (min) => { const h = Math.floor(min/60), m = min%60; return h > 0 ? `${h}h${m>0?` ${m}m`:''}` : `${m}m` }

  // Reihenfolge der geplanten Disziplinen; alles andere hängt sich hinten an.
  // Eine feste Liste hätte jede fremde Sportart verschluckt — eine
  // StairMaster-Einheit stand in History und Zonen, fehlte hier aber
  // vollständig, obwohl sie stattgefunden hat.
  const DISC_ORDER = ['swim', 'bike', 'run', 'brick', 'gym', 'hike', 'other']

  // Nach Kalenderwoche, nicht nach Planwochennummer. Über die Nummer
  // gefiltert zeigte der Breakdown bei jedem Athleten, dessen Aufbau noch
  // nicht begonnen hat, sämtliche jemals absolvierten Einheiten: Vor dem
  // Startdatum bekommt jede Einheit die Nummer 1, und die laufende Woche
  // ist dann ebenfalls 1. Dieselbe Korrektur wie im Backend — hier stand
  // sie ein zweites Mal.
  const { von: wocheVon, bis: wocheBis } = kalenderwoche()
  const weekSessions = sessions.filter(
    s => !s.deleted_at && s.session_date >= wocheVon && s.session_date <= wocheBis
  )
  const totals = { count: 0, km: 0, min: 0 }
  const byDisc = {}
  weekSessions.forEach(s => {
    const d = s.discipline?.toLowerCase()
    totals.count++; totals.km += s.distance_km || 0; totals.min += s.duration_min || 0
    if (!byDisc[d]) {
      byDisc[d] = { count: 0, km: 0, min: 0, dates: [], reflektiert: 0, sport_type: s.sport_type }
    }
    byDisc[d].count++; byDisc[d].km += s.distance_km || 0; byDisc[d].min += s.duration_min || 0
    byDisc[d].dates.push(s.session_date)
    if (s.reflection) byDisc[d].reflektiert++
  })

  // Aus den tatsächlich absolvierten Einheiten aufgebaut, nicht aus einer
  // Aufzählung im Code.
  const discEntries = Object.keys(byDisc)
    .sort((a, b) => {
      const ia = DISC_ORDER.indexOf(a), ib = DISC_ORDER.indexOf(b)
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib)
    })
    .map(d => [d, {
      label: disciplineLabel(d, byDisc[d].sport_type),
      color: disciplineColor(d),
    }])

  const CARD = 'bg-[#111318] border border-[#1e2228] rounded-xl'
  const LABEL = 'text-xs font-mono tracking-widest text-[var(--text-secondary)]'
  const SECTION_TITLE = 'text-xs font-mono tracking-widest text-[var(--text-secondary)] mb-4'

  return (
    <div className="space-y-4 page-enter">
      {/* Liegt vor dem übrigen Inhalt: Das Dashboard ist dahinter sichtbar,
          aber abgedunkelt — der Athlet sieht, wohin er kommt, kann es aber
          noch nicht bedienen. */}
      <IntakeDialog open={intakeFaellig === true} name={profile?.name} onFertig={() => { setIntakeFaellig(false); load() }} />

      {/* Vor der Checkliste: Solange die Adresse unbestätigt ist, ist der
          erste Schritt nicht das Ziel, sondern das Postfach. */}
      {konto && konto.email_verified === false && <EmailBestaetigung email={konto.email} />}

      <FtpHinweis befund={ftpBefund} onTestwoche={() => navigate('/races')} />

      {/* Vorwarnung auf die nächste Testwoche. Eine Woche vorher, damit die
          Woche freigehalten werden kann — wer am Montag erfährt, dass diese
          Woche gemessen wird, hat den Wettkampf am Sonntag schon zugesagt. */}
      {testTermin?.vorwarnung && (
        <div className="rounded-xl p-4 flex items-start gap-3 flex-wrap"
             style={{ background: '#111318', border: '1px solid #1e2228', borderLeft: '3px solid #f59e0b' }}>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-bold text-[#e8eaf0]">Testwoche steht an</div>
            <p className="text-[13px] text-[var(--text-secondary)] mt-1 leading-relaxed">
              {testTermin.vorwarnung}
            </p>
          </div>
          <button
            onClick={() => navigate('/races')}
            className="px-3 py-1.5 rounded-lg text-[12px] font-mono tracking-wide flex-shrink-0"
            style={{ background: '#f59e0b20', border: '1px solid #f59e0b44', color: '#f59e0b' }}>
            ZUR TESTWOCHE
          </button>
        </div>
      )}

      <Onboarding warten={intakeFaellig !== false} />

      {/* Page header — rechts der laufende Tag. Die TODAY-Kachel nennt den
          Wochentag, aber nirgends stand bisher das Datum. */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
      <div>
        <h1 className="text-3xl font-black tracking-tight text-[#e8eaf0]" style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>
          DASHBOARD
        </h1>
      </div>

        <div className="text-right">
          <div className="text-2xl font-black tracking-tight text-[#e8eaf0]"
               style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>
            {new Date().toLocaleDateString('de-DE', { weekday: 'long' }).toUpperCase()}
          </div>
          <div className="text-xs font-mono text-[var(--text-muted)] tabular-nums">
            {new Date().toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })}
          </div>
        </div>
      </div>

      {/* Die Saison als Strahl statt „WEEK 8 / 20 BUILD 2 · NOCH 37 TAGE" als
          Überschrift: wo die Woche liegt, wie lange die Phase noch dauert,
          wann der Deload kommt und wo die Rennen sitzen — auf einen Blick. */}
      {saison && (
        <div className={`${CARD} px-5 py-4`}>
          <SaisonStrahl saison={saison} />
        </div>
      )}

      {/* ── Umfang der Woche: Anzahl, Zeit, Strecke ──
          Ganz oben, weil es die Fakten sind — was tatsächlich passiert ist,
          bevor es um Bewertung und Bereitschaft geht. */}
      <WocheHero sessions={weekSessions} geplant={geplantWoche} bilanz={bilanzWoche}
                 verlauf={verlaufAcht} montag={wochenMontag} />

      {/* ── Wie es dir geht: HRV und Gesundheitszustand ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* HRV — Schnitt, Urteil und Spanne. Eine 14-Tage-Linie stand hier
            auch, Amir hat sie gestrichen: Der Verlauf steht weiter unten in
            der HRV History, zweimal dasselbe Bild war eins zu viel.
            Flach gehalten (Amir: „zu dick"): Empfehlung und Garmin-Hinweis
            stehen in den Zeilen, die es ohnehin gibt, statt in eigenen —
            die Gesundheitskachel daneben wächst auf dieselbe Höhe mit. */}
        <div
          className={`${CARD} px-5 py-4 lg:col-span-2 relative overflow-hidden`}
          style={{
            background: `linear-gradient(100deg, ${lageFarbe}10, transparent 55%), #111318`,
            borderColor: `${lageFarbe}2a`,
          }}
        >
          <div>
            <div className="min-w-0">
              <div className="flex items-baseline justify-between gap-3">
                <div className={LABEL}>
                  HRV
                  {garminVerbunden === true && (
                    <span className="ml-2 text-[9px] tracking-wider text-[var(--text-muted)] font-normal">· GARMIN CONNECT</span>
                  )}
                </div>
                <span className="text-[10px] font-mono tracking-widest" style={{ color: lageFarbe }}>
                  {hrvLage ? (HRV_URTEIL[hrvLage.status] || 'NOT CURRENT') : ''}
                </span>
              </div>

              {/* Zwei Zahlen nebeneinander statt einer großen und einer
                  winzigen: Der Schnitt entscheidet (über ihn gewichtet auch
                  die Urne), der Tageswert ist, wonach man morgens schaut.
                  Jede trägt das Zeichen ihrer Marke auf der Skala darunter —
                  Strich für den Schnitt, Ring für heute. */}
              <div className="flex items-end mt-1.5">
                {hrvLage && (
                  <div className="pr-6">
                    <div className="flex items-center gap-1.5 text-[9px] font-mono tracking-[0.2em] text-[var(--text-muted)]">
                      <span className="inline-block w-[3px] h-2.5 rounded-full" style={{ background: '#e8eaf0' }} />
                      Ø 7 DAYS
                    </div>
                    <div className="flex items-baseline gap-1 mt-1.5">
                      <span
                        className="text-[2.6rem] font-black leading-none tabular-nums"
                        style={{ color: lageFarbe, fontFamily: 'Barlow Condensed, sans-serif', textShadow: `0 0 18px ${lageFarbe}40` }}
                      >
                        {Math.round(hrvLage.schnitt_7)}
                      </span>
                      <span className="text-xs font-mono text-[var(--text-muted)]">ms</span>
                    </div>
                  </div>
                )}
                {hrv && (
                  <div className={hrvLage ? 'pl-6 border-l border-[#1e2228]' : ''}>
                    <div className="flex items-center gap-1.5 text-[9px] font-mono tracking-[0.2em] text-[var(--text-muted)]">
                      <span className="inline-block w-2.5 h-2.5 rounded-full"
                            style={{ border: `2px solid ${HRV_COLOR[hrv.hrv_status] || '#a7aebd'}` }} />
                      {heuteGemessen ? 'TODAY' : `LAST ${hrv.measured_at.slice(8, 10)}.${hrv.measured_at.slice(5, 7)}.`}
                    </div>
                    <div className="flex items-baseline gap-1 mt-1.5">
                      <span
                        className={`${hrvLage ? 'text-3xl' : 'text-5xl'} font-black leading-none tabular-nums`}
                        style={{ color: HRV_COLOR[hrv.hrv_status] || '#e8eaf0', fontFamily: 'Barlow Condensed, sans-serif' }}
                      >
                        {Math.round(hrv.rmssd)}
                      </span>
                      <span className="text-xs font-mono text-[var(--text-muted)]">ms</span>
                    </div>
                  </div>
                )}
                {!hrvLage && !hrv && (
                  <span className="text-5xl font-black leading-none text-[var(--text-muted)]"
                        style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>–</span>
                )}
                {/* Die Empfehlung rechts neben den Zahlen statt in einer
                    eigenen Zeile darunter. */}
                <div className="ml-auto pl-4 text-right text-sm font-bold leading-tight"
                     style={{ color: statusColor, fontFamily: 'Barlow Condensed, sans-serif', letterSpacing: '0.02em' }}>
                  {HRV_TEXT[status].toUpperCase()}
                </div>
              </div>

              <SpannenSkala
                className="mt-6 mb-4"
                zonen={hrvZonen(spanne)}
                marken={[
                  { wert: hrvLage?.schnitt_7, name: 'Ø', titel: `Ø 7 days ${hrvLage?.schnitt_7} ms` },
                  ...(hrv ? [{
                    wert: hrv.rmssd,
                    art: 'neben',
                    name: heuteGemessen ? 'TODAY' : `${hrv.measured_at.slice(8, 10)}.${hrv.measured_at.slice(5, 7)}.`,
                    farbe: HRV_COLOR[hrv.hrv_status] || '#a7aebd',
                    titel: `${heuteGemessen ? 'Today' : 'Last'} ${hrv.rmssd} ms`,
                  }] : []),
                ]}
              />
              {spanne?.gruen_ab && spanne?.gruen_bis && (
                <div className="flex justify-between mt-1.5 text-[9px] font-mono text-[var(--text-muted)] tabular-nums">
                  <span>RED &lt; {Math.round(spanne.rot_unter)}</span>
                  <span>NORMAL {Math.round(spanne.gruen_ab)}–{Math.round(spanne.gruen_bis)}</span>
                </div>
              )}
            </div>

            {garminVerbunden === false && (
              <div className="mt-3 flex justify-end"><HRVInput onSaved={load} /></div>
            )}
          </div>
        </div>

        <HealthStatus variant="tile" onChanged={load} />
      </div>

      {/* ── Heute: die Frage, mit der man das Dashboard öffnet ── */}
      <TodayCard onOpenPlan={() => navigate('/plan')} />

      {/* ── Aufschlüsselung der Woche ── */}
      {discEntries.length > 0 && (
        <div className={`${CARD} p-5`}>
          <div className={SECTION_TITLE}>
            BREAKDOWN <span className="text-[var(--text-muted)]">· SPORTART ANKLICKEN FÜR INSIGHTS UND REFLEXION</span>
          </div>

          {/* Discipline cards */}
          {/* Disziplinen links, Zonenverteilung rechts: dieselbe Woche einmal
              nach Sportart und einmal nach Intensität. Untereinander ließ
              jede der beiden die halbe Breite leer. */}
          {/* Feste Breite für die Zonen statt halbe-halbe: das Diagramm braucht
              nicht mehr, und die Disziplinkarten passen dadurch in eine Reihe
              statt in zwei mit einer angebrochenen. */}
          <div className="grid gap-5"
               style={metrics?.hr_zones_avg
                 ? { gridTemplateColumns: 'minmax(0, 1fr) minmax(300px, 340px)' }
                 : undefined}>
          <div className="grid gap-3 content-start"
               style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))' }}>
            {discEntries.map(([disc, cfg]) => {
              const s = byDisc[disc]
              const aktiv = gewaehlteDisziplin === disc
              return (
                <button
                  key={disc}
                  onClick={() => setGewaehlteDisziplin(aktiv ? null : disc)}
                  title={aktiv ? 'Filter aufheben' : `Nur ${cfg.label} zeigen`}
                  className="rounded-xl p-4 text-left transition-all"
                  style={{
                    background: aktiv ? `${cfg.color}1c` : `${cfg.color}0a`,
                    border: `1px solid ${cfg.color}${aktiv ? '66' : '25'}`,
                    borderLeft: `3px solid ${cfg.color}`,
                  }}
                >
                  <div className="flex items-center gap-1.5 text-xs font-mono font-semibold mb-2.5"
                       style={{ color: cfg.color }}>
                    <SportIcon discipline={disc} size={15} />
                    <span className="flex-1 min-w-0 truncate">{cfg.label}</span>
                    <span className="text-[var(--text-muted)]">{aktiv ? '▴' : '▾'}</span>
                  </div>
                  <div className="text-3xl font-black leading-none mb-2 font-mono" style={{ color: cfg.color, fontFamily: 'Barlow Condensed, sans-serif' }}>{s.count}</div>
                  <div className="space-y-0.5">
                    <div className="text-sm font-mono text-[#e8eaf0]">{fmtTime(s.min)}</div>
                    {s.km > 0 && <div className="text-xs font-mono text-[var(--text-secondary)]">{s.km.toFixed(1)} km</div>}
                    {/* An welchen Tagen — ohne das ist „2 Einheiten" nur eine
                        Zahl und man muss unten nachsehen. */}
                    <div className="text-[10px] font-mono text-[var(--text-secondary)] pt-1">
                      {s.dates
                        .slice()
                        .sort()
                        .map(d => new Date(d + 'T00:00:00').toLocaleDateString('de-DE', { weekday: 'short' }))
                        .join(' · ')}
                    </div>
                    {/* Wie viele Einheiten schon eine Reflexion haben —
                        sonst muss man jede Kachel aufklappen, um es zu sehen. */}
                    <div className="text-[10px] font-mono pt-0.5"
                         style={{ color: s.reflektiert === s.count ? '#22c55e' : 'var(--text-muted)' }}>
                      {s.reflektiert === s.count
                        ? '✓ reflektiert'
                        : `${s.reflektiert}/${s.count} reflektiert`}
                    </div>
                  </div>
                </button>
              )
            })}
          </div>

          {metrics?.hr_zones_avg && (
            <div className="lg:border-l lg:border-[#1e2228] lg:pl-5">
              {/* Belastung und Durchschnittspuls gehören zur Zusammensetzung
                  der Woche, nicht zu ihrem Umfang — neben Anzahl und Strecke
                  standen sie ohne erkennbaren Bezug. */}
              {/* Belastung, Puls und Form gleichmäßig über der Zonenverteilung:
                  drei Zahlen zur selben Woche, gleich gewichtet. */}
              <div className="grid grid-cols-3 gap-3 mb-4 pb-4 border-b border-[#1e2228]">
                {[
                  { label: 'TSS', wert: metrics?.total_tss ?? 0, farbe: '#e8eaf0', zusatz: null },
                  {
                    label: 'Ø PULS', wert: avgHr ?? '–', farbe: hrColor,
                    zusatz: avgHr ? (hrZoneIndex == null ? 'bpm' : `bpm · ${HR_ZONE_LABEL[hrZoneIndex]}`) : null,
                  },
                  {
                    label: 'FORM · TSB',
                    wert: form == null ? '–' : `${form > 0 ? '+' : ''}${form}`,
                    farbe: formFarbe,
                    zusatz: form == null ? null : formText(form).toUpperCase(),
                  },
                ].map(({ label, wert, farbe, zusatz }) => (
                  <div key={label}>
                    <div className={LABEL}>{label}</div>
                    <div className="text-3xl font-black font-mono leading-none mt-1"
                         style={{ color: farbe, fontFamily: 'Barlow Condensed, sans-serif' }}>
                      {wert}
                    </div>
                    {zusatz && (
                      <div className="text-[10px] font-mono mt-1" style={{ color: farbe, opacity: 0.75 }}>
                        {zusatz}
                      </div>
                    )}
                  </div>
                ))}
              </div>
              {/* Eine Leiste statt fünf Säulen: Die Zonen sind Anteile einer
                  Woche, die zusammen 100 % ergeben — das zeigt eine Leiste
                  direkt, Säulen nur über die Achse. Nach Dauer gewichtet
                  (Backend), sonst zählte ein Auslaufen wie eine lange Fahrt. */}
              <SegmentLeiste
                kopf="HR ZONES · SHARE OF THE WEEK"
                mindestens={1}
                segmente={HR_ZONE_LABEL.map((z, i) => ({
                  key: z,
                  name: z,
                  wert: Math.round(metrics.hr_zones_avg[`z${i + 1}`] || 0),
                  farbe: HR_ZONE_COLOR[i],
                  textFarbe: HR_ZONE_COLOR[i],
                }))}
              />
            </div>
          )}
          </div>

          {/* Aufgeklappte Sportart: alles zu diesen Einheiten an einer Stelle
              — Abweichung vom Plan und das Feld für die Reflexion. Eine
              zweite Liste unter den Kacheln hätte dieselbe Information ein
              weiteres Mal aufgeführt. */}
          {gewaehlteDisziplin && (
            <div className="mt-5 pt-5 border-t border-[#1e2228] space-y-3">
              {[...weekSessions]
                .filter(s => s.discipline?.toLowerCase() === gewaehlteDisziplin)
                .sort((a, b) => (a.session_date < b.session_date ? 1 : -1))
                .map(s => {
                  const farbe = DISCIPLINE_COLOR[gewaehlteDisziplin] || '#8a909e'
                  const tag = new Date(s.session_date + 'T00:00:00')
                    .toLocaleDateString('de-DE', {
                      weekday: 'long', day: '2-digit', month: '2-digit', year: 'numeric',
                    })
                  return (
                    <div key={s.id} className="rounded-xl p-4"
                         style={{ background: '#0d0f17', border: `1px solid ${farbe}22` }}>
                      <div className="flex items-baseline justify-between gap-3 flex-wrap mb-3">
                        <div className="flex items-baseline gap-3 flex-wrap">
                          <SportIcon discipline={gewaehlteDisziplin} size={16} color={farbe} />
                          <span className="text-sm font-mono" style={{ color: farbe }}>{tag}</span>
                          {s.intensity_label && (
                            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded"
                                  style={{ background: `${farbe}12`, border: `1px solid ${farbe}2e`, color: farbe }}>
                              {s.intensity_label}
                            </span>
                          )}
                        </div>
                        <button
                          onClick={() => setOffeneEinheit(s)}
                          className="text-[10px] font-mono text-[var(--text-muted)] hover:text-[#00d4ff]"
                          title="Diagramme, Zonen und Streams"
                        >
                          DETAILS ▸
                        </button>
                      </div>

                      {/* Kennzahlen der Einheit */}
                      <div className="flex gap-5 flex-wrap mb-3">
                        {[
                          ['DAUER', s.duration_min ? fmtTime(s.duration_min) : '—'],
                          ['STRECKE', s.distance_km ? `${s.distance_km.toFixed(1)} km` : '—'],
                          ['TSS', s.tss ? Math.round(s.tss) : '—'],
                          ['Ø PULS', s.avg_hr ? `${s.avg_hr} bpm` : '—'],
                          ...(s.avg_watts ? [['Ø WATT', `${s.avg_watts} W`]] : []),
                        ].map(([label, wert]) => (
                          <div key={label}>
                            <div className="text-[9px] font-mono tracking-widest text-[var(--text-muted)]">{label}</div>
                            <div className="text-sm font-mono tabular-nums text-[#e8eaf0] mt-0.5">{wert}</div>
                          </div>
                        ))}
                      </div>

                      {/* Der Plan/Ist-Abgleich — die eigentliche Erkenntnis. */}
                      {s.deviation_note && (
                        <div className="text-[11px] font-mono text-[var(--text-secondary)] leading-relaxed mb-3 pl-2 border-l"
                             style={{ borderColor: `${farbe}44` }}>
                          {s.deviation_note}
                        </div>
                      )}

                      <div className="text-[9px] font-mono tracking-widest text-[var(--text-muted)] mb-1.5">REFLEXION</div>
                      <ReflectionEditor session={s} rows={2} onSaved={load} />
                    </div>
                  )
                })}
            </div>
          )}
        </div>
      )}

      {/* ── Form über die Zeit ── */}
      <div className={`${CARD} p-5`}>
        <div className={SECTION_TITLE}>PERFORMANCE MANAGEMENT</div>
        <PerformanceChart sessions={sessions} />
      </div>

      {/* ── HRV-Verlauf ── */}
      <div className={`${CARD} p-5`}>
        <div className={SECTION_TITLE}>HRV HISTORY · GREEN AREA = YOUR NORMAL RANGE</div>
        <HRVHistoryChart data={hrvHistory} />
      </div>

      {/* ── Begriffe ── */}
      <Glossary />

      {offeneEinheit && (
        <SessionDetail
          session={offeneEinheit}
          onClose={() => { setOffeneEinheit(null); load() }}
        />
      )}

      <style>{`
        @keyframes hrvBreath {
          0%, 100% { opacity: 0.4; transform: scale(0.95); }
          50%       { opacity: 1;   transform: scale(1.05); }
        }
        @keyframes hrvGlow {
          0%, 100% { opacity: 0.6; }
          50%       { opacity: 1; }
        }
      `}</style>
    </div>
  )
}
