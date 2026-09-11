import { useEffect, useRef, useState } from 'react'
import { clearPlannedReplacement, setPlannedReplacement, swapPlannedSessions } from '../services/api'
import Modal from './Modal'
import { DISCIPLINE_COLOR } from '../utils/colors'

// Aus der gemeinsamen Farbtabelle abgeleitet — Rahmen, Fläche und Schrift
// derselben Farbe, nur in unterschiedlicher Deckkraft.
const TYPE_COLOR = Object.fromEntries(
  ['rest', 'bike', 'run', 'swim', 'gym', 'brick', 'hike'].map(d => [
    d,
    d === 'rest'
      ? { border: '#1e2228', bg: '#111318', text: '#8a909e' }
      : { border: DISCIPLINE_COLOR[d], bg: `${DISCIPLINE_COLOR[d]}20`, text: DISCIPLINE_COLOR[d] },
  ])
)

// Zonenfarben aus dem Trainingsmodell — bewusst andere Skala als die
// Sportartfarben, damit Intensität und Disziplin nicht verwechselt werden.
const ZONE_COLOR = {
  Z1: '#2d6a4f',
  Z2: '#40916c',
  Z3: '#f4a261',
  Z4: '#e76f51',
  Z5: '#e63946',
}

// Intensitätsstufen in der Sprache der Trainingslehre. Farbe folgt der Zone,
// damit sich die Härte einer Woche auf einen Blick ablesen lässt.
const INTENSITY_META = {
  base:       { label: 'Base / Endurance', zone: 'Z1–Z2', color: ZONE_COLOR.Z2 },
  sweet_spot: { label: 'Sweet Spot',       zone: 'Z3',    color: ZONE_COLOR.Z3 },
  threshold:  { label: 'Threshold',        zone: 'Z4',    color: ZONE_COLOR.Z4 },
  vo2max:     { label: 'VO₂max',           zone: 'Z5',    color: ZONE_COLOR.Z5 },
}

function getColors(type) {
  return TYPE_COLOR[type?.toLowerCase()] || TYPE_COLOR.rest
}

/** Eine Leiste pro Tag — immer an derselben Stelle, damit die Woche als Block lesbar bleibt.
 *  Rad/Lauf/Brick zeigen die Intensitätsstufe in Zonenfarbe, alles andere
 *  (Schwimmen, Kraft, Ruhetag) eine neutrale Zeile statt einer Lücke. */
function IntensityBadge({ intensity, fallbackLabel, sessionType }) {
  const meta = INTENSITY_META[intensity]
  const isRest = sessionType === 'rest'
  if (!meta && (isRest || !fallbackLabel)) return null

  const color = meta ? meta.color : '#3a3f4a'
  const label = meta ? meta.label : fallbackLabel.replace(/_/g, ' ')

  return (
    <div
      className="mt-1.5 flex items-baseline gap-1.5 rounded px-1.5 py-1"
      style={{
        background: meta ? `${color}18` : '#ffffff06',
        borderLeft: `2px solid ${meta ? color : '#1e2228'}`,
      }}
    >
      <span
        className="text-[10px] font-bold uppercase tracking-wider leading-none"
        style={{ color: meta ? color : 'var(--text-secondary)', fontFamily: 'Barlow Condensed, sans-serif' }}
      >
        {label}
      </span>
      {meta && (
        <span className="text-[9px] font-mono leading-none" style={{ color, opacity: 0.7 }}>
          {meta.zone}
        </span>
      )}
    </div>
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
    <div className="mt-2 flex flex-wrap items-center gap-1.5">
      {chips.map(c => (
        <span
          key={c.key}
          className="text-[11px] font-mono tabular-nums leading-none px-1.5 py-1 rounded"
          style={{ background: '#00d4ff10', border: '1px solid #00d4ff20', color: '#00d4ff' }}
        >
          {c.value}
          <span className="text-[9px] ml-0.5 opacity-60">{c.unit}</span>
        </span>
      ))}
      {hr_zone && (
        <span
          className="text-[10px] font-mono font-bold leading-none px-1.5 py-1 rounded"
          style={{
            background: `${ZONE_COLOR[hr_zone] || '#3a3f4a'}25`,
            border: `1px solid ${ZONE_COLOR[hr_zone] || '#3a3f4a'}`,
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
          <div key={i} className="rounded-lg px-2 py-1 bg-white/5">
            <div className="text-[10px] font-semibold uppercase tracking-wide mb-0.5" style={{ color: isRest ? 'var(--text-muted)' : '#00d4ff' }}>
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
              <div className="text-[10px] uppercase text-[var(--text-muted)] font-medium mb-0.5">{k}</div>
              <BlocksTable blocks={v} sessionType={sessionType} />
            </div>
          )
        }

        if (typeof v === 'object') {
          const color = SUBSECTION_COLOR[k.toLowerCase()] || '#00d4ff'
          return (
            <div key={k} className="border-l-2 pl-2 mt-1.5" style={{ borderColor: color }}>
              <div className="text-[10px] font-bold uppercase tracking-widest mb-0.5" style={{ color }}>
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
  const [text, setText] = useState('')
  const [dauer, setDauer] = useState('')

  useEffect(() => { setText(''); setDauer('') }, [einheit?.id])
  if (!einheit) return null

  const gueltig = text.trim().length > 0

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
          <input
            autoFocus
            value={text}
            onChange={e => setText(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && gueltig) onSpeichern(einheit.id, text.trim(), dauer ? Number(dauer) : null) }}
            placeholder="z. B. Wandern mit Freunden"
            className="w-full rounded-lg border px-3 py-2 text-sm text-[#e8eaf0] outline-none focus:border-[#00d4ff55]"
            style={{ background: '#0d0f14', borderColor: '#1e2228' }}
          />
        </div>

        <div>
          <label className="block text-[10px] font-mono tracking-widest text-[var(--text-secondary)] mb-1.5">
            DAUER IN MINUTEN (OPTIONAL)
          </label>
          <input
            type="number" min="1" inputMode="numeric"
            value={dauer}
            onChange={e => setDauer(e.target.value)}
            placeholder="—"
            className="w-32 rounded-lg border px-3 py-2 text-sm font-mono text-[#e8eaf0] outline-none focus:border-[#00d4ff55]"
            style={{ background: '#0d0f14', borderColor: '#1e2228' }}
          />
        </div>

        <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
          Das zählt als Belastung, nicht als Ausfall — der Coach fährt die
          nächste Woche deswegen nicht zurück.
        </p>

        <div className="flex gap-2 justify-end pt-1">
          <button onClick={onClose}
                  className="px-4 py-2 rounded-lg text-xs font-mono tracking-wide text-[var(--text-secondary)] hover:text-[#e8eaf0]">
            ABBRECHEN
          </button>
          <button
            disabled={!gueltig}
            onClick={() => onSpeichern(einheit.id, text.trim(), dauer ? Number(dauer) : null)}
            className="px-4 py-2 rounded-lg text-xs font-mono tracking-wide border transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            style={{ borderColor: '#f59e0b55', background: '#f59e0b1e', color: '#f59e0b' }}
          >
            EINTRAGEN
          </button>
        </div>
      </div>
    </Modal>
  )
}


export default function WeekCalendar({ days: initialDays, onPersisted }) {
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

  const flash = (ids) => {
    setFlashIds(ids)
    clearTimeout(flashTimer.current)
    flashTimer.current = setTimeout(() => setFlashIds([]), 900)
  }

  const speichereErsatz = async (id, text, dauer) => {
    // Der Kalender zeigt den Ersatz sofort; scheitert der Aufruf, wird der
    // alte Zustand wiederhergestellt statt eine Änderung vorzutäuschen.
    const vorher = days
    setDays(ds => ds.map(d => d.id === id
      ? { ...d, status: 'replaced', replacement: text, replacement_min: dauer }
      : d))
    setErsetze(null)
    try {
      await setPlannedReplacement(id, text, dauer)
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
      ? { ...d, status: 'planned', replacement: null, replacement_min: null }
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
      setError(e.response?.data?.detail || 'Verschieben fehlgeschlagen — Änderung zurückgenommen')
    } finally {
      setSavingIds([])
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="text-[10px] font-mono tracking-widest text-[var(--text-muted)]">
          {persistent
            ? '⠿ ZIEHEN ZUM VERSCHIEBEN — WIRD GESPEICHERT'
            : '⠿ ZIEHEN ZUM VERSCHIEBEN — NUR ANSICHT, NICHT GESPEICHERT'}
        </div>
        {savingIds.length > 0 && (
          <span className="text-[10px] font-mono tracking-widest text-[#00d4ff]">SPEICHERT…</span>
        )}
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
        {days.map((day, i) => {
          const colors = getColors(day.session_type)
          // Der heutige Tag bekommt einen Schein statt nur einer Kante: in
          // sieben gleich aussehenden Karten sucht man ihn sonst jedes Mal.
          const istHeute = day.date === heute
          const isDragging = dragIndex === i
          const isOver = overIndex === i && dragIndex !== i
          const isSaving = day.id != null && savingIds.includes(day.id)
          const isFlashing = day.id != null && flashIds.includes(day.id)

          return (
            <div
              key={day.date || i}
              draggable={!isSaving}
              onDragStart={() => onDragStart(i)}
              onDragOver={(e) => onDragOver(e, i)}
              onDrop={() => onDrop(i)}
              onDragEnd={onDragEnd}
              className="day-card rounded-xl border p-3 transition-all select-none relative"
              style={{
                borderColor: isOver ? '#00d4ff' : (isFlashing ? '#00d4ff' : (istHeute ? `${colors.text}99` : colors.border)),
                background: isOver ? '#00d4ff0d' : colors.bg,
                opacity: isDragging ? 0.4 : (isSaving ? 0.6 : 1),
                cursor: isSaving ? 'progress' : 'grab',
                boxShadow: isOver
                  ? '0 0 0 1px #00d4ff44'
                  : (istHeute ? `0 0 0 1px ${colors.text}44, 0 0 22px -6px ${colors.text}` : 'none'),
                animation: isFlashing ? 'savedPulse 0.9s ease-out' : 'none',
              }}
            >
              {/* Jede Zeile ist ein eigener Slot. Über subgrid teilen sich alle
                  sieben Karten dieselben Zeilenspuren — dadurch stehen Dauer,
                  Zielwerte und Intensität überall auf gleicher Höhe, auch wenn
                  eine Karte einzelne Angaben nicht hat. */}
              <div className="flex justify-between items-start">
                <span className="font-bold text-sm text-[#e8eaf0]" style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>
                  {day.day?.slice(0, 2).toUpperCase()}
                </span>
                {istHeute ? (
                  <span className="text-[9px] font-mono tracking-widest px-1.5 py-0.5 rounded"
                        style={{ background: `${colors.text}1e`, border: `1px solid ${colors.text}55`, color: colors.text }}>
                    HEUTE
                  </span>
                ) : (
                  <span className="text-[10px] font-mono text-[var(--text-muted)]">{day.date?.slice(5)}</span>
                )}
              </div>

              <div className="text-[10px] font-mono font-bold uppercase tracking-widest" style={{ color: colors.text }}>
                {day.session_type}
              </div>

              <div className="text-[10px] font-mono uppercase tracking-wider text-[var(--text-secondary)]">
                {day.training_type && !['rest', 'brick'].includes(day.training_type)
                  ? day.training_type.replace(/_/g, ' ')
                  : ' '}
              </div>

              <div>
                <IntensityBadge
                  intensity={day.intensity}
                  fallbackLabel={day.training_type}
                  sessionType={day.session_type}
                />
              </div>

              <div className="text-xs font-mono text-[var(--text-secondary)]">
                {day.duration_min > 0 ? `${day.duration_min} min` : ' '}
              </div>

              <div>
                <TargetsReadout targets={day.targets} showZone={!INTENSITY_META[day.intensity]} />
              </div>

              <div>
                {/* Verschoben — zeigt den ursprünglichen Termin wie eine Anzeigetafel */}
                {day.moved_from_date && day.moved_from_date !== day.date && (
                  <div className="text-[9px] font-mono text-[var(--text-muted)] tracking-wide mb-1">
                    ↳ ursprünglich {day.moved_from_date.slice(5)}
                  </div>
                )}
                {day.status === 'replaced' && day.replacement ? (
                  /* Der Ersatz tritt an die Stelle der Vorgabe, statt darunter
                     zu stehen: Was an dem Tag passiert ist, ist der Ersatz —
                     die geplante Einheit ist nur noch Herkunft. */
                  <div className="rounded-lg border px-2 py-1.5 mb-1"
                       style={{ borderColor: '#f59e0b55', background: '#f59e0b14' }}>
                    <div className="text-[9px] font-mono tracking-widest mb-0.5"
                         style={{ color: '#f59e0b' }}>
                      STATTDESSEN
                    </div>
                    <p className="text-xs text-[#e8eaf0] leading-snug">{day.replacement}</p>
                    {day.replacement_min > 0 && (
                      <div className="text-[10px] font-mono text-[var(--text-secondary)] mt-0.5">
                        {day.replacement_min} min
                      </div>
                    )}
                    <button
                      onClick={() => nimmErsatzZurueck(day.id)}
                      className="text-[10px] font-mono text-[var(--text-secondary)] hover:text-[#e8eaf0] mt-1 underline"
                    >
                      zurücknehmen
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
                    + ERSETZT
                  </button>
                )}
                <DetailsSection details={day.details} sessionType={day.session_type} />
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
