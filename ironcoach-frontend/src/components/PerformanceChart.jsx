import { useEffect, useLayoutEffect, useMemo, useState } from 'react'
import { isoTag, parseTag } from '../utils/dates'
import { DISCIPLINE_COLOR, DISCIPLINE_LABEL, phaseColor } from '../utils/colors'
import { tagesSummen } from '../utils/einheiten'
import { FORM_ZONEN, formColor, formLabel, formZone } from '../utils/form'

export { formColor, formLabel }

/** Fitness, Ermüdung und Form — die Performance-Kachel im Dashboard.
 *
 *  Vorher ein Recharts-Diagramm mit zwei y-Achsen, 3-px-Formbalken in
 *  Rot/Grün, Gitter, Legende und drei Badges darunter. Amir: das, was ihn
 *  im Dashboard „am meisten nervt". Jetzt in vier Spuren, die sich eine
 *  Zeitachse teilen:
 *
 *  1. **Kopf:** Fitness groß, Ermüdung und Form daneben, darunter wie schnell
 *     die Fitness steigt und wo sie am höchsten war.
 *  2. **Hauptspur:** Fitness als Fläche, Ermüdung als Linie. Die **Lücke
 *     dazwischen ist die Form** — grün, wo die Fitness über der Ermüdung
 *     liegt, rot, wo die Ermüdung sie überholt hat. Unten die TSS je Tag in
 *     der Farbe der Hauptsportart.
 *  3. **Form-Band:** die Form durch ihre Zonen (`utils/form.js`).
 *  4. **Saisonband:** Phasen, Deloads und Rennen aus `/metrics/saison`.
 *
 *  Rechts von heute gestrichelt die **Vorschau aus dem Plan**: dieselbe
 *  Formel, weitergerechnet mit den `target_tss` der geplanten Einheiten.
 *
 *  Fitness ist bewusst nicht cyan: Neben den Sportfarben der TSS-Balken las
 *  sich Cyan als Schwimmen — dieselbe Verwechslung wie im Monatskopf des
 *  Verlaufs.
 *
 *  Die Reihe kommt vom Dashboard (`/metrics/pmc`, sonst `calculatePMC`).
 *  Vorher holte die Kachel sie ein zweites Mal selbst.
 */

const K_ATL = 1 - Math.exp(-1 / 7)
const K_CTL = 1 - Math.exp(-1 / 42)
const TAG_MS = 86400000

const FITNESS = '#e8eaf0'
const ERMUEDUNG = '#f97316'
const FRISCH_FLAECHE = '#22c55e'
const MUEDE_FLAECHE = '#ef4444'

const HAUPT_HOEHE = 200
const BAND_HOEHE = 64
// Das Form-Band zeigt −40 bis +25. Ausreißer werden an den Rand geklemmt,
// sonst drückt ein Rennen mit TSB −60 alle übrigen Tage in einen Strich.
const FORM_MIN = -40
const FORM_MAX = 25
// Ab mehr als 7 Fitnesspunkten pro Woche gilt der Anstieg als steil — die
// übliche Faustregel liegt bei 5–8 CTL pro Woche. Nur ein Hinweis, kein Urteil.
const RAMPE_STEIL = 7

const ZEITRAEUME = [
  { name: '6W', tage: 42 },
  { name: '3M', tage: 91 },
  { name: '6M', tage: 182 },
  { name: '1Y', tage: 365 },
]

/** Fitness (CTL), Ermüdung (ATL) und Form (TSB) je Tag.
 *
 *  **Rückfallebene.** Maßgeblich ist `GET /api/metrics/pmc` — dort rechnet
 *  dieselbe Formel, mit der auch der Coach plant. Diese Fassung springt nur
 *  ein, wenn der Aufruf scheitert: Ein Diagramm, das bei einem Netzfehler
 *  leer bleibt, wäre schlechter als eines mit lokal gerechneten Werten.
 *
 *  Weichen beide je voneinander ab, gilt die Antwort des Servers. */
export function calculatePMC(sessions) {
  if (!sessions?.length) return []
  const dailyTSS = {}
  sessions.forEach(s => {
    if (s.tss != null && s.session_date && !s.deleted_at) {
      const d = s.session_date.slice(0, 10)
      dailyTSS[d] = (dailyTSS[d] || 0) + s.tss
    }
  })
  const dates = Object.keys(dailyTSS).sort()
  if (!dates.length) return []

  // Lokale Tage, nicht UTC: Kurz nach Mitternacht war „heute" in UTC noch
  // gestern, und die Kurve endete einen Tag zu früh.
  const start = parseTag(dates[0])
  const heute = isoTag(new Date())
  const allDays = []
  for (let d = new Date(start); isoTag(d) <= heute; d.setDate(d.getDate() + 1)) {
    allDays.push(isoTag(d))
  }

  let atl = 0, ctl = 0
  return allDays.map(date => {
    // Die Form eines Tages ist der Stand von **gestern** — vor dem Training
    // dieses Tages. Sonst zieht jede Einheit die eigene Form herunter.
    // Dieselbe Definition wie in services/season_summary.py; weicht sie ab,
    // zeigen Kachel und Diagramm verschiedene Zahlen für denselben Tag.
    const tsb = ctl - atl

    const tss = dailyTSS[date] || 0
    atl = atl + (tss - atl) * K_ATL
    ctl = ctl + (tss - ctl) * K_CTL
    return {
      date,
      label: date.slice(5),
      tss: tss || null,
      atl: parseFloat(atl.toFixed(1)),
      ctl: parseFloat(ctl.toFixed(1)),
      tsb: parseFloat(tsb.toFixed(1)),
    }
  })
}

// ─── Reine Rechnungen (exportiert für die Probe) ───────────────────────────

const naechsterTag = tag => {
  const d = parseTag(tag)
  d.setDate(d.getDate() + 1)
  return isoTag(d)
}

/** Fitness und Form vorwärts aus den geplanten Einheiten.
 *
 *  Startet beim letzten gerechneten Tag (`letzter`, in der Regel heute) und
 *  läuft bis zum letzten geplanten Tag nach heute. Dieselbe Formel wie
 *  `calculatePMC` und `season_summary._pmc`, die Form also auch hier der
 *  Stand vom Vortag. Es zählen nur Einheiten nach heute, die noch gelten:
 *  keine Ruhetage, nichts Gestrichenes, nichts Ersetztes. Ohne `target_tss`
 *  zählt eine Einheit null — lieber eine flache Vorschau als eine erfundene.
 */
export function projektion(letzter, geplant, heute = isoTag(new Date())) {
  if (!letzter) return []
  const jeTag = {}
  for (const p of geplant || []) {
    if (!p?.planned_date || p.planned_date <= heute) continue
    if ((p.discipline || '').toLowerCase() === 'rest') continue
    if (p.status === 'skipped' || p.status === 'replaced') continue
    jeTag[p.planned_date] = (jeTag[p.planned_date] || 0) + (p.target_tss || 0)
  }
  const tage = Object.keys(jeTag).filter(t => jeTag[t] > 0).sort()
  if (!tage.length) return []

  const bis = tage[tage.length - 1]
  let { ctl, atl } = letzter
  const ergebnis = []
  for (let t = naechsterTag(letzter.date); t <= bis; t = naechsterTag(t)) {
    const tsb = ctl - atl
    const tss = jeTag[t] || 0
    atl += (tss - atl) * K_ATL
    ctl += (tss - ctl) * K_CTL
    ergebnis.push({
      date: t, tss: tss || null, geplant: true,
      ctl: Math.round(ctl * 10) / 10, atl: Math.round(atl * 10) / 10, tsb: Math.round(tsb * 10) / 10,
    })
  }
  return ergebnis
}

/** Wie sich die Fitness über `tage` Tage verändert hat — gesamt und je Woche. */
export function rampe(pmc, tage = 28) {
  if (!pmc?.length) return null
  const letzter = pmc[pmc.length - 1]
  const d = parseTag(letzter.date)
  d.setDate(d.getDate() - tage)
  const vorher = pmc.find(p => p.date === isoTag(d))
  if (!vorher) return null
  const diff = letzter.ctl - vorher.ctl
  return { diff: Math.round(diff * 10) / 10, jeWoche: Math.round((diff / (tage / 7)) * 10) / 10 }
}

export { formZone }

// ─── Kleinteile ─────────────────────────────────────────────────────────────

const zahl = v => (v == null ? '—' : (Math.round(v * 10) / 10).toFixed(1))
const vorzeichen = v => (v == null ? '—' : `${v > 0 ? '+' : v < 0 ? '−' : '±'}${Math.abs(Math.round(v * 10) / 10).toFixed(1)}`)
const kurz = tag => parseTag(tag).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }).toUpperCase()

function Schalter({ wert, onWahl }) {
  return (
    <div className="flex rounded-lg p-0.5" style={{ background: '#0d0f14', border: '1px solid #1e2228' }}>
      {ZEITRAEUME.map(z => (
        <button
          key={z.name}
          onClick={() => onWahl(z.tage)}
          className="px-2.5 py-1 rounded-md text-[10px] font-mono tracking-widest transition-colors"
          style={{
            color: wert === z.tage ? '#e8eaf0' : '#8a909e',
            background: wert === z.tage ? '#ffffff14' : 'transparent',
            boxShadow: wert === z.tage ? 'inset 0 0 0 1px #ffffff26' : 'none',
          }}
        >
          {z.name}
        </button>
      ))}
    </div>
  )
}

/** Linie durch Punkte als Pfad, Lücken (`null`) unterbrechen ihn. */
function linie(punkte) {
  let d = ''
  let offen = false
  for (const p of punkte) {
    if (!p) { offen = false; continue }
    d += `${offen ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`
    offen = true
  }
  return d
}

// ─── Kachel ────────────────────────────────────────────────────────────────

export default function PerformanceChart({ pmc, sessions, saison, geplant }) {
  const [zeitraum, setZeitraum] = useState(91)
  const [hover, setHover] = useState(null)
  // Gemessen wird über einen Rückruf-Ref, nicht über `useRef` + Effekt mit
  // leeren Abhängigkeiten: Die Kachel erscheint meist zuerst ohne Daten, das
  // Element zum Messen gibt es dann noch nicht, und ein einmal laufender
  // Effekt hätte nie einen Beobachter angehängt — die Spuren blieben leer.
  const [box, setBox] = useState(null)
  const [breite, setBreite] = useState(0)
  useLayoutEffect(() => {
    if (!box) return
    const messen = () => setBreite(box.clientWidth || 0)
    messen()
    const beobachter = new ResizeObserver(messen)
    beobachter.observe(box)
    return () => beobachter.disconnect()
  }, [box])

  // Die Linien zeichnen sich einmal ein — bei „weniger Bewegung" stehen sie.
  const ruhig = typeof window !== 'undefined'
    && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  const [da, setDa] = useState(ruhig)
  const heute = isoTag(new Date())
  const reihe = pmc || []
  const letzter = reihe[reihe.length - 1]
  // Erst einzeichnen, wenn es etwas zu zeichnen gibt — sonst liefe die
  // Animation im Leerzustand ab, bevor die Daten da sind.
  const hatDaten = !!letzter && breite > 0
  useEffect(() => {
    if (da || !hatDaten) return
    const t = setTimeout(() => setDa(true), 30)
    return () => clearTimeout(t)
  }, [da, hatDaten])
  const vorschau = useMemo(() => projektion(letzter, geplant, heute), [letzter, geplant, heute])
  const jeTag = useMemo(() => tagesSummen(sessions || []), [sessions])

  const tage = useMemo(() => {
    const ab = parseTag(heute)
    ab.setDate(ab.getDate() - zeitraum + 1)
    const vonTag = isoTag(ab)
    return [...reihe.filter(p => p.date >= vonTag), ...vorschau]
  }, [reihe, vorschau, zeitraum, heute])

  const steigung = useMemo(() => rampe(reihe), [reihe])
  const spitze = useMemo(() => {
    const ab = parseTag(heute)
    ab.setDate(ab.getDate() - 365)
    const grenze = isoTag(ab)
    return reihe.filter(p => p.date >= grenze).reduce((b, p) => (!b || p.ctl > b.ctl ? p : b), null)
  }, [reihe, heute])

  // `pmc === null`: Das Dashboard lädt noch. Gleiche Höhe wie die fertige
  // Kachel, damit die Seite darunter nicht springt — und kein „keine Daten",
  // solange nur die Antwort fehlt.
  if (pmc === null) {
    return (
      <div>
        <div className="text-xs font-mono tracking-[0.25em] text-[var(--text-secondary)] mb-3">PERFORMANCE</div>
        <div className="h-[380px] rounded-lg" style={{ background: 'linear-gradient(90deg, #0d0f14, #12151b, #0d0f14)' }} />
      </div>
    )
  }

  if (!letzter || !tage.length) {
    return (
      <div>
        <div className="text-xs font-mono tracking-[0.25em] text-[var(--text-secondary)] mb-3">PERFORMANCE</div>
        <div className="py-8 text-center text-[10px] font-mono tracking-widest text-[var(--text-muted)]">
          NO TRAINING DATA YET
        </div>
      </div>
    )
  }

  // ── Geometrie ──
  const W = Math.max(1, breite)
  const n = tage.length
  const x = i => (n > 1 ? (i / (n - 1)) * W : W / 2)
  const istHeute = tage.findIndex(t => t.date === heute)
  const heuteIdx = istHeute >= 0 ? istHeute : tage.findIndex(t => t.geplant) - 1
  const lastMax = Math.max(10, ...tage.map(t => Math.max(t.ctl, t.atl)))
  const yMax = Math.ceil((lastMax * 1.08) / 10) * 10
  const y = v => HAUPT_HOEHE - (v / yMax) * (HAUPT_HOEHE - 6)
  const tssMax = Math.max(50, ...tage.map(t => t.tss || 0))
  const yForm = v => {
    const k = Math.min(FORM_MAX, Math.max(FORM_MIN, v))
    return ((FORM_MAX - k) / (FORM_MAX - FORM_MIN)) * BAND_HOEHE
  }

  const historie = tage.map((t, i) => (t.geplant ? null : [i, t]))
  const plan = tage.map((t, i) => (t.geplant || i === heuteIdx ? [i, t] : null))
  const pfad = (teil, feld, yf = y) => linie(teil.map(e => (e ? [x(e[0]), yf(e[1][feld])] : null)))

  // Fitness als Fläche bis zum Boden, nur über die gerechneten Tage.
  const hist = historie.filter(Boolean)
  const flaeche = hist.length > 1
    ? `${pfad(historie, 'ctl')}L${x(hist[hist.length - 1][0]).toFixed(1)},${HAUPT_HOEHE}L${x(hist[0][0]).toFixed(1)},${HAUPT_HOEHE}Z`
    : ''

  // Die Lücke zwischen Fitness und Ermüdung, tageweise als Trapez. Grün und
  // rot je in einem Pfad — 365 einzelne Polygone wären unnötig viele Knoten.
  let gruen = ''
  let rot = ''
  for (let i = 0; i < n - 1; i++) {
    const a = tage[i]
    const b = tage[i + 1]
    const trapez = `M${x(i).toFixed(1)},${y(a.ctl).toFixed(1)}L${x(i + 1).toFixed(1)},${y(b.ctl).toFixed(1)}`
      + `L${x(i + 1).toFixed(1)},${y(b.atl).toFixed(1)}L${x(i).toFixed(1)},${y(a.atl).toFixed(1)}Z`
    if (a.ctl + b.ctl >= a.atl + b.atl) gruen += trapez
    else rot += trapez
  }

  // Form-Band: Segmente in der Farbe ihrer Zone, Vorschau gestrichelt.
  const formSegmente = { hist: {}, plan: {} }
  for (let i = 0; i < n - 1; i++) {
    const a = tage[i]
    const b = tage[i + 1]
    const farbe = formColor((a.tsb + b.tsb) / 2)
    const art = b.geplant ? 'plan' : 'hist'
    formSegmente[art][farbe] = (formSegmente[art][farbe] || '')
      + `M${x(i).toFixed(1)},${yForm(a.tsb).toFixed(1)}L${x(i + 1).toFixed(1)},${yForm(b.tsb).toFixed(1)}`
  }

  // Monatsnamen am Ersten, bei 6W zusätzlich die Montage. Zu dichte Namen
  // fallen weg (Telefon).
  const marken = []
  tage.forEach((t, i) => {
    const d = parseTag(t.date)
    const monat = d.getDate() === 1
    const montag = zeitraum <= 42 && d.getDay() === 1
    if (!monat && !montag) return
    if (marken.length && x(i) - marken[marken.length - 1].px < 44) return
    marken.push({
      px: x(i),
      text: monat ? d.toLocaleDateString('en-GB', { month: 'short' }).toUpperCase() : kurz(t.date),
    })
  })

  // Saisonband: Grundlage und Blöcke nach Datum, beschnitten auf den Zeitraum.
  // Vom ersten gezeigten Tag aus, nicht vom Beginn des Zeitraums: Hat ein Athlet weniger
  // Daten als den Zeitraum, beginnt die Reihe später, und Band und Kurven
  // lägen gegeneinander verschoben.
  const start = tage[0].date
  const bis = tage[n - 1].date
  const prozent = (tag, plusTage = 0) =>
    ((Math.round((parseTag(tag) - parseTag(start)) / TAG_MS) + plusTage) / Math.max(1, n - 1)) * 100
  const bloecke = saison && saison.lage !== 'off_season' ? [
    ...(saison.grundlage ? [{ name: 'Grundlage', von: saison.grundlage.von, bis: saison.grundlage.bis, stufe: 1 }] : []),
    ...(saison.phasen || []).flatMap(p => {
      const teile = p.teile?.length ? p.teile : [p]
      return teile.map((t, i) => ({ name: t.name, von: t.von, bis: t.bis, stufe: teile.length > 1 ? i / (teile.length - 1) : 1 }))
    }),
  ].filter(b => b.bis >= start && b.von <= bis) : []
  const imZeitraum = tag => tag >= start && tag <= bis

  const gezeigt = hover != null ? tage[hover] : null
  const zone = formZone(letzter.tsb)
  const zeigen = e => {
    const r = box?.getBoundingClientRect()
    if (!r) return
    const px = (e.touches?.[0]?.clientX ?? e.clientX) - r.left
    setHover(Math.max(0, Math.min(n - 1, Math.round((px / W) * (n - 1)))))
  }
  const zeichnen = {
    strokeDasharray: 1,
    strokeDashoffset: da ? 0 : 1,
    transition: ruhig ? 'none' : 'stroke-dashoffset 1.4s cubic-bezier(.2,.7,.2,1)',
  }

  return (
    <div>
      {/* ── Kopf ── */}
      <div className="flex items-start justify-between gap-4 flex-wrap mb-5">
        <div>
          <div className="text-xs font-mono tracking-[0.25em] text-[var(--text-secondary)] mb-3">PERFORMANCE</div>
          <div className="flex items-end gap-6 sm:gap-8 flex-wrap">
            <div>
              <div className="text-[9px] font-mono tracking-[0.2em] text-[var(--text-muted)]">FITNESS · CTL</div>
              <div className="text-5xl font-black leading-none tabular-nums mt-1.5"
                   style={{ fontFamily: 'Barlow Condensed, sans-serif', color: FITNESS, textShadow: '0 0 28px #ffffff1a' }}>
                {zahl(letzter.ctl)}
              </div>
            </div>
            <div className="pl-6 sm:pl-8 border-l border-[#ffffff0f]">
              <div className="text-[9px] font-mono tracking-[0.2em] text-[var(--text-muted)]">FATIGUE · ATL</div>
              <div className="text-3xl font-black leading-none tabular-nums mt-1.5"
                   style={{ fontFamily: 'Barlow Condensed, sans-serif', color: ERMUEDUNG }}>
                {zahl(letzter.atl)}
              </div>
            </div>
            <div className="pl-6 sm:pl-8 border-l border-[#ffffff0f]">
              <div className="text-[9px] font-mono tracking-[0.2em] text-[var(--text-muted)]">FORM · TSB</div>
              <div className="flex items-baseline gap-2 mt-1.5">
                <span className="text-3xl font-black leading-none tabular-nums"
                      style={{ fontFamily: 'Barlow Condensed, sans-serif', color: zone?.farbe }}>
                  {vorzeichen(letzter.tsb)}
                </span>
                <span className="text-[10px] font-mono tracking-widest" style={{ color: zone?.farbe }}>{zone?.en}</span>
              </div>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-[10px] font-mono tracking-widest text-[var(--text-muted)]">
            {steigung && (
              <span>
                <span className="tabular-nums" style={{ color: steigung.jeWoche > RAMPE_STEIL ? '#eab308' : '#e8eaf0' }}>
                  {vorzeichen(steigung.diff)}
                </span>
                {' '}IN 4 WEEKS ·{' '}
                <span className="tabular-nums" style={{ color: steigung.jeWoche > RAMPE_STEIL ? '#eab308' : '#e8eaf0' }}>
                  {vorzeichen(steigung.jeWoche)}
                </span>
                /WEEK
                {steigung.jeWoche > RAMPE_STEIL && <span style={{ color: '#eab308' }}> · STEEP</span>}
              </span>
            )}
            {spitze && (
              <span>
                PEAK <span className="text-[#e8eaf0] tabular-nums">{zahl(spitze.ctl)}</span> · {kurz(spitze.date)}
              </span>
            )}
          </div>
        </div>
        <Schalter wert={zeitraum} onWahl={z => { setZeitraum(z); setHover(null) }} />
      </div>

      {/* ── Spuren ── */}
      <div ref={setBox} className="relative select-none touch-pan-y"
           onMouseMove={zeigen} onMouseLeave={() => setHover(null)}
           onTouchStart={zeigen} onTouchMove={zeigen} onTouchEnd={() => setHover(null)}>
        {breite > 0 && (
          <>
            {/* Hauptspur */}
            <div className="relative" style={{ height: HAUPT_HOEHE }}>
              <span className="absolute right-0 -top-3.5 text-[9px] font-mono tabular-nums text-[var(--text-muted)]">{yMax}</span>
              {vorschau.length > 0 && heuteIdx >= 0 && (
                <>
                  <div className="absolute inset-y-0 right-0"
                       style={{ left: x(heuteIdx), background: 'repeating-linear-gradient(135deg, transparent 0 5px, #ffffff05 5px 6px)' }} />
                  <span className="absolute top-1 text-[8px] font-mono tracking-[0.2em] text-[var(--text-muted)]"
                        style={{ left: x(heuteIdx) + 6 }}>PLAN</span>
                </>
              )}
              <svg width={W} height={HAUPT_HOEHE} className="absolute inset-0 overflow-visible">
                <defs>
                  <linearGradient id="fitness-flaeche" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={FITNESS} stopOpacity="0.16" />
                    <stop offset="100%" stopColor={FITNESS} stopOpacity="0" />
                  </linearGradient>
                </defs>
                <line x1="0" x2={W} y1={y(yMax)} y2={y(yMax)} stroke="#1e2228" strokeDasharray="3 3" />
                <line x1="0" x2={W} y1={y(yMax / 2)} y2={y(yMax / 2)} stroke="#15181e" />

                {/* TSS je Tag, unten, in der Farbe der Hauptsportart */}
                {tage.map((t, i) => t.tss ? (
                  <rect key={t.date} x={x(i) - Math.max(1, W / n / 2 - 0.5)} width={Math.max(1.5, W / n - 1)}
                        y={HAUPT_HOEHE - (t.tss / tssMax) * HAUPT_HOEHE * 0.25}
                        height={(t.tss / tssMax) * HAUPT_HOEHE * 0.25} rx="1"
                        fill={t.geplant ? 'none' : DISCIPLINE_COLOR[jeTag[t.date]?.haupt] || '#5b6475'}
                        stroke={t.geplant ? '#5b6475' : 'none'} strokeDasharray={t.geplant ? '2 2' : undefined}
                        opacity={t.geplant ? 0.8 : 0.42} />
                ) : null)}

                {flaeche && <path d={flaeche} fill="url(#fitness-flaeche)" style={{ opacity: da ? 1 : 0, transition: 'opacity 1s' }} />}
                <path d={gruen} fill={FRISCH_FLAECHE} opacity={da ? 0.16 : 0} style={{ transition: 'opacity 1.2s' }} />
                <path d={rot} fill={MUEDE_FLAECHE} opacity={da ? 0.2 : 0} style={{ transition: 'opacity 1.2s' }} />

                <path d={pfad(historie, 'ctl')} fill="none" stroke={FITNESS} strokeWidth="2" pathLength="1" style={zeichnen} />
                <path d={pfad(historie, 'atl')} fill="none" stroke={ERMUEDUNG} strokeWidth="1.4" pathLength="1" style={zeichnen} />
                {vorschau.length > 0 && (
                  <>
                    <path d={pfad(plan, 'ctl')} fill="none" stroke={FITNESS} strokeWidth="1.6" strokeDasharray="4 4" opacity="0.7" />
                    <path d={pfad(plan, 'atl')} fill="none" stroke={ERMUEDUNG} strokeWidth="1.2" strokeDasharray="4 4" opacity="0.7" />
                  </>
                )}

                {/* Heute */}
                {heuteIdx >= 0 && (
                  <>
                    <line x1={x(heuteIdx)} x2={x(heuteIdx)} y1="0" y2={HAUPT_HOEHE} stroke="#ffffff30" />
                    <circle cx={x(heuteIdx)} cy={y(tage[heuteIdx].ctl)} r="3.5" fill={FITNESS}
                            style={{ filter: 'drop-shadow(0 0 6px #ffffff88)' }} />
                    <circle cx={x(heuteIdx)} cy={y(tage[heuteIdx].atl)} r="2.5" fill={ERMUEDUNG} />
                  </>
                )}

                {/* Zeiger */}
                {gezeigt && (
                  <>
                    <circle cx={x(hover)} cy={y(gezeigt.ctl)} r="3" fill="#0a0c0f" stroke={FITNESS} strokeWidth="1.5" />
                    <circle cx={x(hover)} cy={y(gezeigt.atl)} r="3" fill="#0a0c0f" stroke={ERMUEDUNG} strokeWidth="1.5" />
                  </>
                )}
              </svg>
              {heuteIdx >= 0 && (
                <span className="absolute -top-3.5 -translate-x-1/2 text-[8px] font-mono tracking-[0.2em] text-[var(--text-secondary)]"
                      style={{ left: x(heuteIdx) }}>TODAY</span>
              )}
            </div>

            {/* Form-Band */}
            <div className="relative mt-3" style={{ height: BAND_HOEHE }}>
              <svg width={W} height={BAND_HOEHE} className="absolute inset-0 overflow-visible">
                {FORM_ZONEN.map((z, i) => {
                  const oben = i === 0 ? FORM_MAX : FORM_ZONEN[i - 1].ab
                  const unten = Math.max(FORM_MIN, z.ab)
                  return (
                    <rect key={z.en} x="0" width={W} y={yForm(oben)} height={yForm(unten) - yForm(oben)}
                          fill={z.farbe} opacity={i === 1 ? 0.09 : 0.05} />
                  )
                })}
                <line x1="0" x2={W} y1={yForm(0)} y2={yForm(0)} stroke="#ffffff1a" />
                {Object.entries(formSegmente.hist).map(([farbe, d]) => (
                  <path key={farbe} d={d} fill="none" stroke={farbe} strokeWidth="1.6" strokeLinecap="round" />
                ))}
                {Object.entries(formSegmente.plan).map(([farbe, d]) => (
                  <path key={`p${farbe}`} d={d} fill="none" stroke={farbe} strokeWidth="1.3" strokeDasharray="3 3" opacity="0.75" />
                ))}
                {gezeigt && <circle cx={x(hover)} cy={yForm(gezeigt.tsb)} r="3" fill="#0a0c0f" stroke={formColor(gezeigt.tsb)} strokeWidth="1.5" />}
              </svg>
              {FORM_ZONEN.map((z, i) => {
                const oben = i === 0 ? FORM_MAX : FORM_ZONEN[i - 1].ab
                const unten = Math.max(FORM_MIN, z.ab)
                return (
                  <span key={z.en} className="absolute left-1 text-[7px] font-mono tracking-[0.2em] pointer-events-none"
                        style={{ top: (yForm(oben) + yForm(unten)) / 2 - 4, color: z.farbe, opacity: 0.55 }}>
                    {z.en}
                  </span>
                )
              })}
            </div>

            {/* Saisonband */}
            {bloecke.length > 0 && (
              <div className="relative h-1.5 mt-2.5">
                {bloecke.map(b => {
                  const links = Math.max(0, prozent(b.von))
                  const rechts = Math.min(100, prozent(b.bis, 1))
                  return (
                    <div key={`${b.name}-${b.von}`} className="absolute inset-y-0 rounded-[1px]" title={b.name}
                         style={{ left: `${links}%`, width: `calc(${Math.max(0, rechts - links)}% - 2px)`,
                                  background: phaseColor(b.name), opacity: 0.55 + 0.35 * b.stufe }} />
                  )
                })}
                {(saison.deload || []).filter(d => imZeitraum(d.montag)).map(d => (
                  <span key={d.woche} className="absolute top-full mt-0.5 -translate-x-1/2 block w-0 h-0" title={`Deload · ${kurz(d.montag)}`}
                        style={{ left: `${prozent(d.montag, 3.5)}%`,
                                 borderLeft: '3px solid transparent', borderRight: '3px solid transparent', borderBottom: '4px solid #a7aebd' }} />
                ))}
                {[...(saison.rennen || []).map(r => r.datum), saison.race_date].filter(t => t && imZeitraum(t)).map(t => (
                  <span key={t} className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 w-2 h-2 rotate-45"
                        style={{ left: `${prozent(t)}%`, background: '#0a0c0f', border: '1px solid #e8eaf0' }} title={`Race · ${kurz(t)}`} />
                ))}
              </div>
            )}

            {/* Monate */}
            <div className="relative h-3 mt-2">
              {marken.map(m => (
                <span key={m.px} className="absolute text-[8px] font-mono text-[var(--text-muted)] whitespace-nowrap" style={{ left: m.px }}>
                  {m.text}
                </span>
              ))}
            </div>

            {/* Fadenkreuz über alle Spuren */}
            {gezeigt && (
              <div className="absolute top-0 bottom-0 w-px pointer-events-none" style={{ left: x(hover), background: '#ffffff26' }} />
            )}
          </>
        )}
      </div>

      {/* ── Fuß: was unter dem Zeiger liegt, sonst die Legende ── */}
      {/* Feste Höhe, damit beim Zeigen nichts springt: auf dem Telefon zwei
          Zeilen, sonst eine. */}
      <div className="mt-2 h-9 sm:h-5 overflow-hidden flex flex-wrap content-start items-center gap-x-3 gap-y-1 text-[10px] font-mono text-[var(--text-secondary)]">
        {gezeigt ? (
          <>
            <span className="text-[#e8eaf0]">
              {parseTag(gezeigt.date).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' }).toUpperCase()}
            </span>
            {gezeigt.geplant && <span className="text-[var(--text-muted)] tracking-widest">PLANNED</span>}
            <span>FITNESS <span style={{ color: FITNESS }}>{zahl(gezeigt.ctl)}</span></span>
            <span>FATIGUE <span style={{ color: ERMUEDUNG }}>{zahl(gezeigt.atl)}</span></span>
            <span>FORM <span style={{ color: formColor(gezeigt.tsb) }}>{vorzeichen(gezeigt.tsb)} {formZone(gezeigt.tsb)?.en}</span></span>
            {gezeigt.tss > 0 && (
              <span>
                {Math.round(gezeigt.tss)} TSS
                {!gezeigt.geplant && jeTag[gezeigt.date] && (
                  <span style={{ color: DISCIPLINE_COLOR[jeTag[gezeigt.date].haupt] }}>
                    {' '}{(DISCIPLINE_LABEL[jeTag[gezeigt.date].haupt] || jeTag[gezeigt.date].haupt).toUpperCase()}
                  </span>
                )}
              </span>
            )}
          </>
        ) : (
          <span className="flex flex-wrap gap-x-4 gap-y-1 text-[9px] tracking-widest text-[var(--text-muted)]">
            <span className="flex items-center gap-1.5"><span className="w-3 h-0.5 inline-block" style={{ background: FITNESS }} />FITNESS</span>
            <span className="flex items-center gap-1.5"><span className="w-3 h-0.5 inline-block" style={{ background: ERMUEDUNG }} />FATIGUE</span>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 inline-block rounded-[1px]" style={{ background: FRISCH_FLAECHE, opacity: 0.5 }} />
              <span className="w-2 h-2 inline-block rounded-[1px] -ml-1" style={{ background: MUEDE_FLAECHE, opacity: 0.5 }} />
              GAP = FORM
            </span>
            {vorschau.length > 0 && <span>DASHED = FROM YOUR PLAN</span>}
          </span>
        )}
      </div>
    </div>
  )
}
