import { useEffect, useRef, useState } from 'react'
import { clearPlannedReplacement, setPlannedReplacement, swapPlannedSessions } from '../services/api'
import Modal from './Modal'
import { DISCIPLINE_COLOR, DONE_COLOR, INTENSITY_META, ZONE_COLOR as ZONE_FARBEN } from '../utils/colors'
import SollIstLeiste from './leisten/SollIstLeiste'
import SportIcon from './SportIcon'
import { DISPLAY, KOPF, NEBEN, TITEL, toenung } from './leisten/Kachel'
import { fehlerText } from '../utils/fehler'

// Die Farbe für "ersetzt". Bernstein, also aus der Ampelfamilie: Es ist eine
// Aussage über den Tag, keine Sportart — und sie schlägt deshalb die
// Disziplinfarbe, sonst sieht ein ersetzter Radtag wie ein gefahrener aus.
const ERSETZT_COLOR = '#f59e0b'

// Als Ersatz sinnvoll. `brick` fehlt mit Absicht: Ein Koppeltraining plant man,
// es passiert nicht spontan.
//
// `rest` stand zuerst auch nicht hier — mit der Begründung, ein Ruhetag sei kein
// Ersatz. Das war falsch gedacht: Wer die Einheit ausfallen lässt und sich
// stattdessen ausruht, hat eine Entscheidung getroffen, und der Coach soll den
// Unterschied zu einer unerklärten Lücke sehen. Ohne die Angabe steht dort
// "nicht absolviert, kein Grund gemeldet", und die nächste Woche wird
// zurückgefahren, als wäre etwas schiefgegangen.
const ERSATZ_SPORTARTEN = [
  { key: 'swim', label: 'SCHWIMMEN' },
  { key: 'bike', label: 'RAD' },
  { key: 'run', label: 'LAUF' },
  { key: 'gym', label: 'KRAFT' },
  { key: 'hike', label: 'WANDERN' },
  { key: 'other', label: 'SONSTIGES' },
  { key: 'rest', label: 'RUHETAG' },
]

// Dieselben vier Stufen wie überall in der Anwendung, in denselben Farben der
// Zonenskala. `sweet_spot` heisst beim Laufen "Tempo" — der Schlüssel bleibt,
// damit Plan, Verlauf und Auswertung dieselbe Sprache sprechen.
const ERSATZ_STUFEN = [
  { key: 'base', label: 'GRUNDLAGE', color: INTENSITY_META.base.color },
  { key: 'sweet_spot', label: 'TEMPO / SWEETSPOT', color: INTENSITY_META.sweet_spot.color },
  { key: 'threshold', label: 'SCHWELLE', color: INTENSITY_META.threshold.color },
  { key: 'vo2max', label: 'VO₂MAX', color: INTENSITY_META.vo2max.color },
]

// Aus der gemeinsamen Farbtabelle abgeleitet — Rahmen, Fläche und Schrift
// derselben Farbe, nur in unterschiedlicher Deckkraft.
//
// Im Kleid der Dashboard-Kacheln: Die Sportfarbe tönt die Karte von oben
// (`toenung`) und färbt Rand und Schrift leise. Vorher war jede Karte voll
// in ihrer Farbe gefüllt und kräftig umrandet — sieben bunte Säulen, in denen
// Dauer und Zielwerte untergingen.
const TYPE_COLOR = Object.fromEntries(
  // `other` fehlte: Ersatztraining (StairMaster, Rudern) fiel auf das Grau
  // des Ruhetags zurück und sah aus wie ein freier Tag.
  ['rest', 'bike', 'run', 'swim', 'gym', 'brick', 'hike', 'other'].map(d => [
    d,
    d === 'rest'
      ? { border: '#1e2228', bg: '#111318', text: '#8a909e', farbe: null }
      : { border: `${DISCIPLINE_COLOR[d]}33`, bg: toenung(DISCIPLINE_COLOR[d], 0.9).background, text: DISCIPLINE_COLOR[d], farbe: DISCIPLINE_COLOR[d] },
  ])
)

// Englisch wie die Kacheln im Dashboard. Die Tage kommen als deutsche Namen
// aus dem Plan (`day`), die Sportarten als Schlüssel.
const TAG_EN = { Montag: 'MON', Dienstag: 'TUE', Mittwoch: 'WED', Donnerstag: 'THU', Freitag: 'FRI', Samstag: 'SAT', Sonntag: 'SUN' }
const SPORT_EN = { swim: 'SWIMMING', bike: 'CYCLING', run: 'RUNNING', gym: 'GYM', brick: 'BRICK', hike: 'HIKING', rest: 'REST', other: 'OTHER' }
const STUFE_EN = { base: 'BASE', sweet_spot: 'SWEET SPOT', threshold: 'THRESHOLD', vo2max: 'VO₂MAX' }
const kurzDatum = iso => iso
  ? new Date(`${iso}T00:00:00`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }).toUpperCase()
  : ''

/** Sportart mit Zeichen in ihrer Farbe — wie die Sportzeilen im BREAKDOWN. */
function SportMarke({ typ, farbe }) {
  const t = (typ || '').toLowerCase()
  return (
    <div className="flex items-center gap-1.5 min-w-0" style={{ color: farbe }}>
      {t !== 'rest' && <SportIcon discipline={t} size={13} />}
      <span className="text-[11px] font-mono font-semibold tracking-wider truncate">{SPORT_EN[t] || t.toUpperCase()}</span>
    </div>
  )
}

/** Dauer groß wie die Zahlen der Dashboard-Kacheln, „min" klein daneben. */
function Dauer({ min }) {
  if (!(min > 0)) return ' '
  return (
    <span className="flex items-baseline gap-1">
      <span className="text-2xl font-black leading-none tabular-nums text-[#f2f4f8]" style={DISPLAY}>{min}</span>
      <span className="text-[10px] font-mono text-[var(--text-muted)]">min</span>
    </span>
  )
}

// Zonen- und Stufenfarben aus der gemeinsamen Tabelle (`utils/colors.js`).
// Hier stand eine eigene Kopie: andere Palette als der Verlauf, und Z6/Z7 in
// Fuchsia und Violett — den Farben der Sportarten.
const ZONE_COLOR = Object.fromEntries(
  Object.entries(ZONE_FARBEN).map(([nummer, farbe]) => [`Z${nummer}`, farbe])
)

function getColors(type) {
  return TYPE_COLOR[type?.toLowerCase()] || TYPE_COLOR.rest
}

/** Eine Leiste pro Tag — immer an derselben Stelle, damit die Woche als Block lesbar bleibt.
 *  Rad/Lauf/Brick zeigen die Intensitätsstufe in Zonenfarbe, alles andere
 *  (Schwimmen, Kraft, Ruhetag) eine neutrale Zeile statt einer Lücke. */
function IntensityBadge({ intensity, fallbackLabel, sessionType }) {
  const meta = INTENSITY_META[intensity]
  // Ohne Stufe nichts: Der Trainingstyp steht in der Zeile darüber schon,
  // als Ersatzplakette stand er zweimal in derselben Karte („ENDURANCE").
  if (!meta) return null

  const color = meta.color
  const label = STUFE_EN[intensity] || meta.label

  // Eine Plakette wie die Intensität in der TODAY-Kachel, statt eines
  // gefüllten Streifens mit Randstrich.
  return (
    <span
      className="inline-flex items-baseline gap-1.5 rounded px-1.5 py-0.5 text-[9px] font-mono tracking-widest uppercase leading-none"
      style={{ background: `${color}14`, border: `1px solid ${color}33`, color }}
    >
      {label}
      <span style={{ opacity: 0.7 }}>{meta.zone}</span>
    </span>
  )
}

function formatPace(seconds) {
  if (!seconds && seconds !== 0) return null
  const m = Math.floor(seconds / 60)
  const s = String(Math.round(seconds % 60)).padStart(2, '0')
  return `${m}:${s}`
}

/** Numerische Zielwerte — die maschinenlesbare Hälfte einer Einheit. */
function TargetsReadout({ targets, showZone = true }) {
  if (!targets) return null

  const chips = []
  const { watts_low, watts_high, pace_low_s_per_km, pace_high_s_per_km,
          tss, distance_km } = targets
  // Die Zone erscheint nur, wenn sie nicht schon in der Intensitätsleiste
  // steht — sonst stand dieselbe Information zweimal in derselben Karte.
  const hr_zone = showZone ? targets.hr_zone : null

  if (watts_low || watts_high) {
    const range = watts_low && watts_high && watts_low !== watts_high
      ? `${watts_low}–${watts_high}` : (watts_low || watts_high)
    chips.push({ key: 'w', value: range, unit: 'W' })
  }
  if (pace_low_s_per_km || pace_high_s_per_km) {
    const lo = formatPace(pace_low_s_per_km)
    const hi = formatPace(pace_high_s_per_km)
    chips.push({ key: 'p', value: lo && hi && lo !== hi ? `${lo}–${hi}` : (lo || hi), unit: '/km' })
  }
  if (distance_km) chips.push({ key: 'd', value: distance_km, unit: 'km' })
  if (tss) chips.push({ key: 't', value: Math.round(tss), unit: 'TSS' })

  if (!chips.length && !hr_zone) return null

  return (
    <div className="mt-1 flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
      {/* Werte schlicht wie in der TODAY-Kachel. Cyan steht in der App für
          Schwimmen und Bedienung — als Farbe jeder Zahl las es sich wie
          beides. */}
      {chips.map(c => (
        <span key={c.key} className="text-[11px] font-mono tabular-nums leading-none text-[#e8eaf0]">
          {c.value}
          <span className="text-[9px] ml-0.5 text-[var(--text-muted)]">{c.unit}</span>
        </span>
      ))}
      {hr_zone && (
        <span
          className="text-[9px] font-mono tracking-widest leading-none px-1.5 py-0.5 rounded"
          style={{
            background: `${ZONE_COLOR[hr_zone] || '#3a3f4a'}14`,
            border: `1px solid ${ZONE_COLOR[hr_zone] || '#3a3f4a'}33`,
            color: ZONE_COLOR[hr_zone] || '#8a909e',
          }}
        >
          {hr_zone}
        </span>
      )}
    </div>
  )
}

function BlocksTable({ blocks }) {
  if (!blocks?.length) return null
  return (
    <div className="mt-1 space-y-1">
      {blocks.map((b, i) => {
        const isRest = b.block === 'Erholung'
        const label = b.block ?? `Block ${i + 1}`
        const { block: _, ...rest } = b
        const values = Object.values(rest).filter(Boolean)
        return (
          <div key={i} className="rounded-md px-2 py-1" style={{ background: '#0d0f14', border: '1px solid #1a1d24' }}>
            <div className="text-[9px] font-mono uppercase tracking-widest mb-0.5" style={{ color: isRest ? 'var(--text-muted)' : '#e8eaf0' }}>
              {label}
            </div>
            <div className="flex flex-wrap gap-x-2 gap-y-0.5">
              {values.map((v, j) => (
                <span key={j} className="text-[11px] text-[var(--text-secondary)]">{v}</span>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

const SUBSECTION_COLOR = {
  bike: DISCIPLINE_COLOR.bike,
  run: DISCIPLINE_COLOR.run,
  swim: DISCIPLINE_COLOR.swim,
  transition: DISCIPLINE_COLOR.transition,
}

// Bricks sollen immer in der Reihenfolge stehen, in der sie absolviert werden:
// Rad, Wechsel, Lauf. Claude liefert die Schlüssel in wechselnder Reihenfolge
// und mal auf Deutsch, mal auf Englisch — ohne feste Sortierung stand der
// Lauf mal oben, mal unten.
const SUBSECTION_ORDER = [
  ['bike', 'rad', 'radfahren'],
  ['transition', 'wechsel', 'uebergang', 'übergang'],
  ['run', 'lauf', 'laufen'],
]

/** Rang eines Schlüssels. Bewusst kein reines includes(): "grundlage" enthält
 *  "run" und würde sonst als Laufabschnitt einsortiert. */
function subsectionRank(key) {
  const k = String(key).toLowerCase()
  for (let rank = 0; rank < SUBSECTION_ORDER.length; rank++) {
    for (const hint of SUBSECTION_ORDER[rank]) {
      if (
        k === hint ||
        k.startsWith(`${hint}_`) || k.startsWith(`${hint}-`) ||
        k.endsWith(`_${hint}`) || k.endsWith(`-${hint}`) ||
        k.includes(`_${hint}_`)
      ) {
        return rank
      }
    }
  }
  return SUBSECTION_ORDER.length
}

function orderedEntries(details) {
  return Object.entries(details)
    .map((entry, index) => ({ entry, index, rank: subsectionRank(entry[0]) }))
    .sort((a, b) => (a.rank - b.rank) || (a.index - b.index))
    .map(item => item.entry)
}

function DetailsSection({ details, sessionType, depth = 0 }) {
  if (!details || typeof details !== 'object' || Object.keys(details).length === 0) return null
  return (
    <div className={depth === 0 ? 'mt-2 space-y-1.5' : 'mt-1 space-y-1 pl-2'}>
      {orderedEntries(details).map(([k, v]) => {
        if (v == null || v === '') return null

        if (Array.isArray(v)) {
          return (
            <div key={k}>
              <div className={`${KOPF} uppercase mb-0.5`}>{k}</div>
              <BlocksTable blocks={v} sessionType={sessionType} />
            </div>
          )
        }

        if (typeof v === 'object') {
          const color = SUBSECTION_COLOR[k.toLowerCase()] || '#a7aebd'
          return (
            <div key={k} className="pl-2 mt-1.5" style={{ boxShadow: `inset 1px 0 0 ${color}66` }}>
              <div className="text-[9px] font-mono uppercase tracking-widest mb-0.5" style={{ color }}>
                {k}
              </div>
              <DetailsSection details={v} sessionType={k} depth={depth + 1} />
            </div>
          )
        }

        return (
          <div key={k} className="text-xs text-[var(--text-secondary)] leading-snug">
            <span className="text-[var(--text-muted)]">{k}:</span> {String(v)}
          </div>
        )
      })}
    </div>
  )
}

const DAY_ORDER = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']

function sortDays(list) {
  return [...(list || [])].sort((a, b) => {
    if (a.date && b.date && a.date !== b.date) return a.date < b.date ? -1 : 1
    return DAY_ORDER.indexOf(a.day) - DAY_ORDER.indexOf(b.day)
  })
}

/** Heutiges Datum als YYYY-MM-DD — dieselbe Form wie `day.date`. */
function heutigesDatum() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** Was wurde stattdessen gemacht?
 *
 *  Bewusst zwei Felder und kein Auswahlmenü: Die Gründe, warum jemand statt
 *  des Plans etwas anderes tut, lassen sich nicht aufzählen — und eine Liste
 *  aus „Krankheit / keine Zeit / Sonstiges" liest sich wie eine Rechtfertigung.
 *  Hier soll nichts entschuldigt, sondern erfasst werden.
 */
function ErsatzDialog({ einheit, onClose, onSpeichern }) {
  const [disziplin, setDisziplin] = useState('')
  const [dauer, setDauer] = useState('')
  const [stufe, setStufe] = useState('')
  const [text, setText] = useState('')

  useEffect(() => {
    setDisziplin(''); setDauer(''); setStufe(''); setText('')
  }, [einheit?.id])
  if (!einheit) return null

  // Sportart genügt. Eine Beschreibung darf dazu, muss aber nicht — vorher war
  // sie das Einzige, und aus "war schwimmen" liess sich für die Planung nichts
  // ableiten.
  const gueltig = disziplin !== '' || text.trim().length > 0

  // Ein Ruhetag hat keine Dauer und keine Intensität. Sie trotzdem
  // mitzuschicken hiesse, einem Ruhetag eine Belastung zuzuschreiben.
  const istRuhe = disziplin === 'rest'

  const speichern = () => onSpeichern(einheit.id, {
    discipline: disziplin || null,
    durationMin: istRuhe || !dauer ? null : Number(dauer),
    intensity: istRuhe ? null : (stufe || null),
    text: text.trim(),
  })

  return (
    <Modal
      open={!!einheit}
      onClose={onClose}
      title="Etwas anderes gemacht"
      subtitle={`Geplant war ${einheit.session_type?.toUpperCase()}${einheit.duration_min ? ` · ${einheit.duration_min} min` : ''} am ${einheit.date?.slice(5)}`}
    >
      <div className="space-y-4">
        <div>
          <label className="block text-[10px] font-mono tracking-widest text-[var(--text-secondary)] mb-1.5">
            WAS STATTDESSEN?
          </label>
          <div className="flex gap-1.5 flex-wrap">
            {ERSATZ_SPORTARTEN.map(({ key, label }) => {
              const aktiv = disziplin === key
              const farbe = DISCIPLINE_COLOR[key] || '#64748b'
              return (
                <button
                  key={key} type="button"
                  onClick={() => setDisziplin(aktiv ? '' : key)}
                  className="px-2.5 py-1.5 rounded-lg text-[11px] font-mono tracking-wide border transition-colors"
                  style={{
                    borderColor: aktiv ? farbe : '#1e2228',
                    background: aktiv ? `${farbe}1e` : '#0d0f14',
                    color: aktiv ? farbe : 'var(--text-muted)',
                  }}
                >
                  {label}
                </button>
              )
            })}
          </div>
        </div>

        {istRuhe ? (
          <p className="text-xs font-mono leading-relaxed rounded-lg px-3 py-2"
             style={{ background: `${ERSETZT_COLOR}0d`, border: `1px solid ${ERSETZT_COLOR}26`, color: 'var(--text-secondary)' }}>
            Dauer und Intensität entfallen. Der Tag zählt als bewusste Erholung,
            nicht als Ausfall — der Coach sieht den Unterschied.
          </p>
        ) : (
        <div className="flex gap-4 flex-wrap">
          <div>
            <label className="block text-[10px] font-mono tracking-widest text-[var(--text-secondary)] mb-1.5">
              DAUER IN MINUTEN
            </label>
            <input
              type="number" min="1" inputMode="numeric"
              value={dauer}
              onChange={e => setDauer(e.target.value)}
              placeholder="—"
              className="w-28 rounded-lg border px-3 py-2 text-sm font-mono text-[#e8eaf0] outline-none focus:border-[#00d4ff55]"
              style={{ background: '#0d0f14', borderColor: '#1e2228' }}
            />
          </div>

          <div className="flex-1 min-w-[15rem]">
            <label className="block text-[10px] font-mono tracking-widest text-[var(--text-secondary)] mb-1.5">
              INTENSITÄT
            </label>
            <div className="flex gap-1.5 flex-wrap">
              {ERSATZ_STUFEN.map(({ key, label, color }) => {
                const aktiv = stufe === key
                return (
                  <button
                    key={key} type="button"
                    onClick={() => setStufe(aktiv ? '' : key)}
                    className="px-2 py-1.5 rounded-lg text-[10px] font-mono tracking-wide border transition-colors"
                    style={{
                      borderColor: aktiv ? color : '#1e2228',
                      background: aktiv ? `${color}1e` : '#0d0f14',
                      color: aktiv ? color : 'var(--text-muted)',
                    }}
                  >
                    {label}
                  </button>
                )
              })}
            </div>
          </div>
        </div>
        )}

        <div>
          <label className="block text-[10px] font-mono tracking-widest text-[var(--text-secondary)] mb-1.5">
            NOTIZ (OPTIONAL)
          </label>
          <input
            value={text}
            onChange={e => setText(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && gueltig) speichern() }}
            placeholder="z. B. mit Freunden, spontan"
            className="w-full rounded-lg border px-3 py-2 text-sm text-[#e8eaf0] outline-none focus:border-[#00d4ff55]"
            style={{ background: '#0d0f14', borderColor: '#1e2228' }}
          />
        </div>

        <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
          Das zählt als Belastung, nicht als Ausfall — der Coach fährt die
          nächste Woche deswegen nicht zurück. Mit Sportart und Intensität kann
          er die Woche danach darauf aufbauen statt nur den Ausfall zu buchen.
        </p>

        <div className="flex gap-2 justify-end pt-1">
          <button onClick={onClose}
                  className="px-4 py-2 rounded-lg text-xs font-mono tracking-wide text-[var(--text-secondary)] hover:text-[#e8eaf0]">
            ABBRECHEN
          </button>
          <button
            disabled={!gueltig}
            onClick={speichern}
            className="px-4 py-2 rounded-lg text-xs font-mono tracking-wide border transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            style={{ borderColor: `${ERSETZT_COLOR}55`, background: `${ERSETZT_COLOR}1e`, color: ERSETZT_COLOR }}
          >
            EINTRAGEN
          </button>
        </div>
      </div>
    </Modal>
  )
}

/** `istJeEinheit`: was zu jeder geplanten Einheit tatsächlich absolviert wurde
 *  (`GET /planned/am/{montag}/bilanz`, Schlüssel = id als Text). Damit zeigt
 *  ein erledigter Tag „75 / 60 min" als Leiste statt nur ein Häkchen. */
function aufDieUhr(day, heute) {
  if (day.id == null || !day.date || day.date < heute) return false
  if (!['planned', 'moved', 'completed'].includes(day.status || 'planned')) return false
  const teile = day.session_type === 'brick'
    ? [day.details?.bike, day.details?.run].filter(t => t && typeof t === 'object' && Object.keys(t).length)
    : ['run', 'bike'].includes(day.session_type) ? [day.details || {}] : []
  const rennen = t => ['typ', 'workout'].some(f => String(t?.[f] || '').toLowerCase().includes('wettkampf'))
  return teile.some(t => !rennen(t))
}

export default function WeekCalendar({ days: initialDays, onPersisted, istJeEinheit, anUhr = false }) {
  const [days, setDays] = useState(() => sortDays(initialDays))
  const heute = heutigesDatum()
  const [dragIndex, setDragIndex] = useState(null)
  const [overIndex, setOverIndex] = useState(null)
  const [savingIds, setSavingIds] = useState([])
  const [flashIds, setFlashIds] = useState([])
  const [error, setError] = useState(null)
  // Welche Einheit gerade ersetzt wird — null heißt: Dialog zu.
  const [ersetze, setErsetze] = useState(null)
  const flashTimer = useRef(null)

  // Ohne diesen Sync zeigt der Kalender nach "Generate Plan" weiter die alten
  // Tage: useState übernimmt den Prop nur beim ersten Mount.
  useEffect(() => { setDays(sortDays(initialDays)) }, [initialDays])

  useEffect(() => () => clearTimeout(flashTimer.current), [])

  if (!days?.length) return null

  // Persistenz ist nur möglich, wenn die Einheiten aus planned_sessions kommen.
  const persistent = days.some(d => d.id != null)

  // Das Ist zu einer geplanten Einheit, sofern das Backend eine zugeordnet hat.
  const istVon = (day) => (day.id != null ? istJeEinheit?.[String(day.id)] : null)

  const flash = (ids) => {
    setFlashIds(ids)
    clearTimeout(flashTimer.current)
    flashTimer.current = setTimeout(() => setFlashIds([]), 900)
  }

  const speichereErsatz = async (id, angabe) => {
    // Der Kalender zeigt den Ersatz sofort; scheitert der Aufruf, wird der
    // alte Zustand wiederhergestellt statt eine Änderung vorzutäuschen.
    const vorher = days
    // Sofort im Kalender: Der Tag nimmt die Ersetzt-Farbe an, noch bevor die
    // Antwort da ist. Scheitert der Aufruf, wird der alte Zustand
    // wiederhergestellt statt eine Änderung vorzutäuschen.
    setDays(ds => ds.map(d => d.id === id
      ? {
          ...d,
          status: 'replaced',
          replacement: angabe.text || null,
          replacement_min: angabe.durationMin,
          replacement_discipline: angabe.discipline,
          replacement_intensity: angabe.intensity,
        }
      : d))
    setErsetze(null)
    try {
      await setPlannedReplacement(id, angabe)
      flash([id])
      onPersisted?.()
    } catch (e) {
      setDays(vorher)
      setError('Ersatz konnte nicht gespeichert werden.')
    }
  }

  const nimmErsatzZurueck = async (id) => {
    const vorher = days
    setDays(ds => ds.map(d => d.id === id
      ? { ...d, status: 'planned', replacement: null, replacement_min: null,
            replacement_discipline: null, replacement_intensity: null }
      : d))
    try {
      await clearPlannedReplacement(id)
      onPersisted?.()
    } catch (e) {
      setDays(vorher)
      setError('Ersatz konnte nicht zurückgenommen werden.')
    }
  }

  const onDragStart = (i) => setDragIndex(i)
  const onDragOver = (e, i) => { e.preventDefault(); setOverIndex(i) }
  const onDragEnd = () => { setDragIndex(null); setOverIndex(null) }

  const onDrop = async (targetIndex) => {
    const sourceIndex = dragIndex
    setDragIndex(null)
    setOverIndex(null)
    if (sourceIndex === null || sourceIndex === targetIndex) return

    const before = days
    const a = days[sourceIndex]
    const b = days[targetIndex]

    // Die Tagesslots (Name + Datum) bleiben stehen, die Einheiten tauschen —
    // exakt das, was der Swap-Endpoint serverseitig macht.
    const swapFields = ['id', 'session_type', 'training_type', 'duration_min',
                        'notes', 'details', 'targets', 'status', 'moved_from_date']
    const next = [...days]
    const patchA = { ...a }
    const patchB = { ...b }
    swapFields.forEach(f => {
      patchA[f] = b[f]
      patchB[f] = a[f]
    })
    next[sourceIndex] = patchA
    next[targetIndex] = patchB
    setDays(next)
    setError(null)

    if (a.id == null || b.id == null) return  // Altplan ohne Projektion: nur lokal

    setSavingIds([a.id, b.id])
    try {
      await swapPlannedSessions(a.id, b.id)
      flash([a.id, b.id])
      onPersisted?.()
    } catch (e) {
      setDays(before)  // Rollback — der Kalender darf nie etwas zeigen, was nicht in der DB steht
      setError(fehlerText(e, 'Verschieben fehlgeschlagen — Änderung zurückgenommen'))
    } finally {
      setSavingIds([])
    }
  }

  // Ein Tag kann mehrere Einheiten tragen — ein Doppeltag sind zwei Einträge
  // mit demselben Datum. Das Raster hat aber genau sieben Spalten, und jede
  // Karte spannt alle Zeilen: Bekam jede Einheit ihre eigene Karte, fanden die
  // achte und neunte keinen Platz mehr, der Browser legte rechts neue Spalten
  // an, und die Woche lief aus dem Bild.
  //
  // Deshalb eine Spalte je **Tag**. Der flache Index jeder Einheit wird
  // mitgeführt: Ziehen und Tauschen arbeiten weiter über `days[i]`, und eine
  // zweite Einheit lässt sich genauso verschieben wie die erste.
  const gruppen = []
  {
    const nachDatum = new Map()
    days.forEach((day, i) => {
      const schluessel = day.date ?? `ohne-datum-${i}`
      if (!nachDatum.has(schluessel)) {
        const g = { datum: day.date ?? null, schluessel, eintraege: [] }
        nachDatum.set(schluessel, g)
        gruppen.push(g)
      }
      nachDatum.get(schluessel).eintraege.push({ day, i })
    })
    // Nach Datum, falls die Einträge nicht sortiert ankommen — der Rohplan
    // aus dem Modell garantiert keine Reihenfolge.
    gruppen.sort((a, b) => (a.datum && b.datum ? a.datum.localeCompare(b.datum) : 0))
  }

  /** Was unter den Kennzahlen einer Einheit steht: Verschiebung, Ersatz oder
   *  Notiz, der Ersatz-Knopf und die Details. Für die erste und jede weitere
   *  Einheit eines Tages derselbe Block — zwei Fassungen liefen auseinander. */
  const detailsBlock = (day) => (
    <>
      {/* Verschoben — zeigt den ursprünglichen Termin wie eine Anzeigetafel */}
      {day.moved_from_date && day.moved_from_date !== day.date && (
        <div className="text-[9px] font-mono text-[var(--text-muted)] tracking-wide mb-1">
          ↳ MOVED FROM {kurzDatum(day.moved_from_date)}
        </div>
      )}
      {/* Auch ohne Freitext: Der Dialog erlaubt, nur die Sportart oder die
          Dauer anzugeben. Vorher verschwand der Block dann nach dem Neuladen,
          und der Tag sah aus wie geplant. */}
      {day.status === 'replaced' && (day.replacement || day.replacement_discipline || day.replacement_min > 0) ? (
        /* Der Ersatz tritt an die Stelle der Vorgabe, statt darunter
           zu stehen: Was an dem Tag passiert ist, ist der Ersatz —
           die geplante Einheit ist nur noch Herkunft. */
        <div className="rounded-md px-2 py-1.5 mb-1"
             style={{ border: `1px solid ${ERSETZT_COLOR}33`, background: `${ERSETZT_COLOR}0d` }}>
          <div className="text-[9px] font-mono tracking-widest mb-0.5"
               style={{ color: ERSETZT_COLOR }}>
            INSTEAD
          </div>
          <p className="text-xs text-[#e8eaf0] leading-snug">
            {day.replacement || (day.replacement_discipline || '').toUpperCase()}
          </p>
          {day.replacement_min > 0 && (
            <div className="text-[10px] font-mono text-[var(--text-secondary)] mt-0.5">
              {day.replacement_min} min
            </div>
          )}
          <button
            onClick={() => nimmErsatzZurueck(day.id)}
            className="text-[9px] font-mono tracking-widest text-[var(--text-muted)] hover:text-[#e8eaf0] mt-1"
          >
            UNDO
          </button>
        </div>
      ) : (
        day.notes && (
          <p className="text-xs text-[var(--text-secondary)] leading-relaxed">{day.notes}</p>
        )
      )}
      {persistent && day.id != null && day.session_type !== 'rest'
        && day.status !== 'replaced' && day.status !== 'completed' && (
        <button
          onClick={() => setErsetze(day)}
          className="block text-left text-[9px] font-mono tracking-widest uppercase text-[var(--text-muted)] hover:text-[#f59e0b] transition-colors mt-1 whitespace-nowrap"
        >
          + REPLACED
        </button>
      )}
      {/* Läuft über intervals.icu von selbst auf die Geräte. Nur ein Stand,
          kein Knopf: Gesendet wird nach jeder Änderung ohnehin. Dieselbe
          Auswahl wie im Backend (`geplantes_workout.workouts`): Läufe,
          Radeinheiten und beide Teile eines Bricks ab heute, keine Rennen.
          „Device" statt „Watch": Ob es auf Uhr oder Radcomputer landet,
          entscheidet jeder in intervals.icu selbst. */}
      {anUhr && aufDieUhr(day, heute) && (
        <div className="text-[9px] font-mono tracking-widest text-[var(--text-muted)] mt-1"
             title="Über intervals.icu auf die dort verbundenen Geräte (Garmin, Wahoo)">
          ↑ ON YOUR DEVICE
        </div>
      )}
      <DetailsSection details={day.details} sessionType={day.session_type} />
    </>
  )

  /** Jede weitere Einheit eines Tages, kompakt unter der ersten.
   *
   *  Eigene Ziehgriffe, und die Ereignisse gehen nicht an die Karte darüber
   *  weiter — sonst zöge man immer die erste Einheit des Tages, egal wo man
   *  anfasst. */
  const weitereEinheit = (day, i, nr) => {
    const c = getColors(day.session_type)
    const erledigt = day.status === 'completed' && day.session_type !== 'rest'
    const ersetzt = day.status === 'replaced'
    const ziehend = dragIndex === i
    const darueber = overIndex === i && dragIndex !== i
    const speichernd = day.id != null && savingIds.includes(day.id)
    const blinkend = day.id != null && flashIds.includes(day.id)
    return (
      <div
        key={day.id ?? `${day.date}-${i}`}
        draggable={!speichernd}
        onDragStart={(e) => { e.stopPropagation(); onDragStart(i) }}
        onDragOver={(e) => { e.stopPropagation(); onDragOver(e, i) }}
        onDrop={(e) => { e.stopPropagation(); onDrop(i) }}
        onDragEnd={(e) => { e.stopPropagation(); onDragEnd() }}
        className="mt-3 rounded-lg border p-2.5 space-y-1.5 transition-all"
        style={{
          borderColor: darueber || blinkend ? '#00d4ff'
            : (ersetzt ? `${ERSETZT_COLOR}44`
              : (erledigt ? `${DONE_COLOR}44` : c.border)),
          background: darueber ? '#00d4ff0d'
            : (ersetzt ? toenung(ERSETZT_COLOR).background
              : (erledigt ? toenung(DONE_COLOR).background : '#0d0f14')),
          opacity: ziehend ? 0.4 : (speichernd ? 0.6 : 1),
          cursor: speichernd ? 'progress' : 'grab',
          animation: blinkend ? 'savedPulse 0.9s ease-out' : 'none',
        }}
      >
        <div className="flex justify-between items-center gap-2">
          <SportMarke typ={day.session_type} farbe={c.text} />
          <span className="flex items-center gap-1.5">
            {erledigt && (
              <span className="text-[9px] font-mono font-bold tracking-widest px-1.5 py-0.5 rounded"
                    style={{ background: `${DONE_COLOR}22`, border: `1px solid ${DONE_COLOR}66`, color: DONE_COLOR }}
                    title="Absolviert und dem Plan zugeordnet">
                ✓
              </span>
            )}
            <span className="text-[9px] font-mono tracking-widest text-[var(--text-muted)]">
              #{nr}
            </span>
          </span>
        </div>
        {day.training_type && !['rest', 'brick'].includes(day.training_type) && (
          <div className={`${KOPF} uppercase`}>
            {day.training_type.replace(/_/g, ' ')}
          </div>
        )}
        <div className="flex items-center gap-2 flex-wrap">
          <IntensityBadge
            intensity={day.intensity}
            fallbackLabel={day.training_type}
            sessionType={day.session_type}
          />
          {day.duration_min > 0 && !(erledigt && istVon(day)) && <Dauer min={day.duration_min} />}
        </div>
        {erledigt && istVon(day) && (
          <SollIstLeiste kompakt soll={day.duration_min || 0} ist={istVon(day).ist_min} farbe={c.text} />
        )}
        <TargetsReadout targets={day.targets} showZone={!INTENSITY_META[day.intensity]} />
        {detailsBlock(day)}
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <span className={TITEL}>THE WEEK</span>
        <span className={NEBEN}>
          {savingIds.length > 0
            ? <span className="text-[#e8eaf0]">SAVING…</span>
            : persistent ? '⠿ DRAG TO SWAP · SAVED' : '⠿ DRAG TO SWAP · VIEW ONLY, NOT SAVED'}
        </span>
      </div>

      {error && (
        <div
          className="rounded-lg px-3 py-2 font-mono text-xs"
          style={{ background: '#ef444415', border: '1px solid #ef444430', color: '#ef4444' }}
        >
          {error}
        </div>
      )}

      <div className="week-grid">
        {gruppen.map(({ datum, schluessel, eintraege }) => {
          // Die erste Einheit des Tages ist die volle Karte, über das
          // Untergitter mit allen sieben Spalten ausgerichtet. Weitere stehen
          // darunter in derselben Spalte.
          const [{ day, i }, ...weitere] = eintraege
          const colors = getColors(day.session_type)
          // Der heutige Tag bekommt einen Schein statt nur einer Kante: in
          // sieben gleich aussehenden Karten sucht man ihn sonst jedes Mal.
          const istHeute = day.date === heute
          // Absolviert: Die Projektion setzt `completed`, sobald eine echte
          // Einheit der geplanten zugeordnet wurde. Ein Ruhetag gilt nicht als
          // Leistung — er bekommt kein Häkchen, sonst wäre "erledigt" beim
          // Nichtstun dasselbe Signal wie nach drei Stunden auf dem Rad.
          const istErledigt = day.status === 'completed' && day.session_type !== 'rest'
          // Ersetzt ist eine Aussage über den Tag, keine Sportart — und sie
          // schlägt deshalb die Disziplinfarbe. Vorher war nur ein kleines
          // Abzeichen bernsteinfarben, und ein ersetzter Radtag sah aus wie ein
          // gefahrener.
          const istErsetzt = day.status === 'replaced'
          const isDragging = dragIndex === i
          const isOver = overIndex === i && dragIndex !== i
          const isSaving = day.id != null && savingIds.includes(day.id)
          const isFlashing = day.id != null && flashIds.includes(day.id)

          return (
            <div
              // Eine Spalte je Datum: eindeutig und stabil, auch beim Ziehen —
              // das tauscht Inhalte, nicht Tage.
              key={schluessel}
              draggable={!isSaving}
              onDragStart={() => onDragStart(i)}
              onDragOver={(e) => onDragOver(e, i)}
              onDrop={() => onDrop(i)}
              onDragEnd={onDragEnd}
              className="day-card rounded-xl border p-3.5 transition-all select-none relative"
              style={{
                borderColor: isOver ? '#00d4ff'
                  : (isFlashing ? '#00d4ff'
                    : (istHeute ? `${colors.farbe || '#e8eaf0'}77`
                      : (istErsetzt ? `${ERSETZT_COLOR}44`
                        : (istErledigt ? `${DONE_COLOR}44` : colors.border)))),
                // Erledigt schlägt die Disziplinfarbe im Grund, nicht in der
                // Kante: Die Sportart bleibt an Zeichen und Schrift ablesbar,
                // der Grund sagt "gemacht".
                background: isOver ? '#00d4ff0d'
                  : (istErsetzt ? toenung(ERSETZT_COLOR).background
                    : (istErledigt ? toenung(DONE_COLOR).background : colors.bg)),
                opacity: isDragging ? 0.4 : (isSaving ? 0.6 : 1),
                cursor: isSaving ? 'progress' : 'grab',
                boxShadow: isOver
                  ? '0 0 0 1px #00d4ff44'
                  : (istHeute ? `0 0 24px -12px ${colors.farbe || '#e8eaf0'}` : 'none'),
                animation: isFlashing ? 'savedPulse 0.9s ease-out' : 'none',
              }}
            >
              {/* Jede Zeile ist ein eigener Slot. Über subgrid teilen sich alle
                  sieben Karten dieselben Zeilenspuren — dadurch stehen Dauer,
                  Zielwerte und Intensität überall auf gleicher Höhe, auch wenn
                  eine Karte einzelne Angaben nicht hat. */}
              <div className="flex justify-between items-baseline gap-1">
                <span className={`${TITEL} text-[#e8eaf0]`}>
                  {TAG_EN[day.day] || day.day?.slice(0, 3).toUpperCase()}
                </span>
                <span className="flex items-center gap-1.5">
                  {istErledigt && (
                    <span className="text-[9px] font-mono font-bold tracking-widest px-1.5 py-0.5 rounded"
                          style={{ background: `${DONE_COLOR}22`, border: `1px solid ${DONE_COLOR}66`, color: DONE_COLOR }}
                          title="Absolviert und dem Plan zugeordnet">
                      ✓
                    </span>
                  )}
                  {weitere.length > 0 && (
                    <span className="text-[9px] font-mono font-bold tracking-widest px-1.5 py-0.5 rounded"
                          style={{ border: '1px solid #ffffff26', color: '#e8eaf0' }}
                          title={`${weitere.length + 1} Einheiten an diesem Tag`}>
                      ×{weitere.length + 1}
                    </span>
                  )}
                  {istHeute ? (
                    <span className="text-[9px] font-mono tracking-widest px-1.5 py-0.5 rounded"
                          style={{ background: '#ffffff14', border: '1px solid #ffffff26', color: '#e8eaf0' }}>
                      TODAY
                    </span>
                  ) : (
                    <span className={`${NEBEN} text-[9px]`}>{kurzDatum(datum)}</span>
                  )}
                </span>
              </div>

              <div className="mt-2">
                <SportMarke typ={day.session_type} farbe={colors.text} />
              </div>

              <div className={`${KOPF} uppercase`}>
                {day.training_type && !['rest', 'brick'].includes(day.training_type)
                  ? day.training_type.replace(/_/g, ' ')
                  : ' '}
              </div>

              <div>
                <IntensityBadge
                  intensity={day.intensity}
                  fallbackLabel={day.training_type}
                  sessionType={day.session_type}
                />
              </div>

              {/* Erledigt: geplant gegen absolviert als Leiste. Gleiche Zeile wie
                  sonst die Dauer, damit die Karten über das Untergitter
                  ausgerichtet bleiben. */}
              <div className="text-xs font-mono text-[var(--text-secondary)] mt-1">
                {istErledigt && istVon(day)
                  ? <SollIstLeiste kompakt soll={day.duration_min || 0} ist={istVon(day).ist_min} farbe={colors.text} />
                  : <Dauer min={day.duration_min} />}
              </div>

              <div>
                <TargetsReadout targets={day.targets} showZone={!INTENSITY_META[day.intensity]} />
              </div>

              <div>
                {detailsBlock(day)}
                {weitere.map(({ day: d, i: j }, n) => weitereEinheit(d, j, n + 2))}
              </div>
            </div>
          )
        })}
      </div>

      <ErsatzDialog
        einheit={ersetze}
        onClose={() => setErsetze(null)}
        onSpeichern={speichereErsatz}
      />

      <style>{`
        .week-grid {
          display: grid;
          grid-template-columns: 1fr;
          gap: 0.75rem;
        }

        @media (min-width: 768px) {
          .week-grid {
            /* Sechs Kopfzeilen fester Höhe, der Rest wächst mit dem Inhalt */
            grid-template-columns: repeat(7, minmax(0, 1fr));
            grid-template-rows: repeat(6, auto) 1fr;
            column-gap: 0.75rem;
            row-gap: 0.35rem;
          }

          /* Die Karte spannt alle Zeilen und übernimmt die Spuren des
             Elterngitters — nur so richten sich die Abschnitte über alle
             sieben Spalten hinweg aneinander aus. */
          .day-card {
            grid-row: 1 / -1;
            display: grid;
            grid-template-rows: subgrid;
            align-content: start;
          }
        }

        @keyframes savedPulse {
          0%   { box-shadow: 0 0 0 0 #00d4ff66; }
          70%  { box-shadow: 0 0 0 6px #00d4ff00; }
          100% { box-shadow: 0 0 0 0 #00d4ff00; }
        }
      `}</style>
    </div>
  )
}
