import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  getRaceTypes, getActiveGoal, createGoal,
  getRaces, createRace, deleteRace,
  getBenchmarkWeek, getBenchmarkTiming, createBenchmarkPlan, deriveZones, getUpcomingRaces, deleteGoal,
  updateProfile,
  uploadRaceImage, deleteRaceImage, fetchRaceImage, updateRace,
} from '../services/api'
import SeriesBadge from '../components/SeriesBadge'
import Modal from '../components/Modal'
import BenchmarkGuide from '../components/BenchmarkGuide'
import { daysUntil, formatTag } from '../utils/dates'
import { DISCIPLINE_COLOR } from '../utils/colors'

const CARD = 'bg-[#111318] border border-[#1e2228] rounded-xl'
const LABEL = 'text-[10px] font-mono tracking-widest text-[var(--text-secondary)]'
const DISPLAY = { fontFamily: 'Barlow Condensed, sans-serif' }

// A verankert die Saison, B und C liegen darin. Ohne diese Unterscheidung
// würde jeder eingetragene Wettkampf die Planung übernehmen.
const PRIORITAETEN = [
  { key: 'A', label: 'SAISONZIEL', hint: 'Bestimmt Planlänge, Phasen und Wochenzählung. Voller Taper.' },
  { key: 'B', label: 'ZWISCHENWETTKAMPF', hint: 'Wird ernst genommen, ändert die Saison aber nicht. Kurze Entlastung davor.' },
  { key: 'C', label: 'TRAININGSWETTKAMPF', hint: 'Wird als harte Einheit mitgenommen. Keine Entlastung davor.' },
]
const PRIO_COLOR = { A: '#00d4ff', B: '#f59e0b', C: '#8a909e' }

// Platzhalter richten sich nach der gewählten Sportart. Ein fest
// eingetragener Ironman als Beispiel im Laufformular führt in die Irre.
const BEISPIEL = {
  triathlon: {
    name: 'Ironman 70.3 Zell am See',
    ort: 'Zell am See',
    zeit: '5:28:14',
    zielzeit: 'sub 5:30h',
  },
  running: {
    name: 'Berlin Marathon',
    ort: 'Berlin',
    zeit: '3:24:10',
    zielzeit: 'sub 3:30h',
  },
}
const beispielFuer = (sport) => BEISPIEL[sport] || BEISPIEL.triathlon

// Farbe je Teildisziplin — dieselbe Zuordnung wie im Wochenplan.
const LEG_COLOR = {
  swim: DISCIPLINE_COLOR.swim, t1: DISCIPLINE_COLOR.transition,
  bike: DISCIPLINE_COLOR.bike, t2: DISCIPLINE_COLOR.transition,
  run: DISCIPLINE_COLOR.run,
}
const LEG_LABEL = { swim: 'Schwimmen', t1: 'W1', bike: 'Rad', t2: 'W2', run: 'Laufen' }

function fmtTime(seconds) {
  if (!seconds && seconds !== 0) return null
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  return h > 0
    ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
    : `${m}:${String(s).padStart(2, '0')}`
}

/** Splits als proportionaler Balken — zeigt auf einen Blick, wo die Zeit blieb. */
function SplitBar({ race }) {
  const legs = ['swim', 't1', 'bike', 't2', 'run']
    .map(key => ({ key, seconds: race[`${key}_time_s`] }))
    .filter(l => l.seconds)
  const total = legs.reduce((sum, l) => sum + l.seconds, 0)
  if (!total) return null

  return (
    <div className="mt-3">
      <div className="flex h-2 rounded-full overflow-hidden" style={{ background: '#0d0f17' }}>
        {legs.map(l => (
          <div
            key={l.key}
            title={`${LEG_LABEL[l.key]}: ${fmtTime(l.seconds)}`}
            style={{ width: `${(l.seconds / total) * 100}%`, background: LEG_COLOR[l.key] }}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
        {legs.filter(l => !['t1', 't2'].includes(l.key)).map(l => (
          <span key={l.key} className="text-[11px] font-mono" style={{ color: LEG_COLOR[l.key] }}>
            {LEG_LABEL[l.key]} {fmtTime(l.seconds)}
          </span>
        ))}
      </div>
    </div>
  )
}

/** Foto als Hintergrund. Es liegt hinter der Anmeldung, lässt sich also nicht
 *  direkt als src einbinden — deshalb einmal laden und als Objekt-URL halten. */
function useRaceImage(race) {
  const [url, setUrl] = useState(null)

  useEffect(() => {
    if (!race.image_file) { setUrl(null); return }
    let objectUrl = null
    let abgebrochen = false
    fetchRaceImage(race.id)
      .then(({ data }) => {
        if (abgebrochen) return
        objectUrl = URL.createObjectURL(data)
        setUrl(objectUrl)
      })
      .catch(() => setUrl(null))
    // Objekt-URLs bleiben sonst bis zum Neuladen der Seite im Speicher.
    return () => { abgebrochen = true; if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [race.id, race.image_file])

  return url
}

function RaceCard({ race, onDelete, onEdit, onImageChange }) {
  const image = useRaceImage(race)
  const [busy, setBusy] = useState(false)

  const pick = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setBusy(true)
    try { await uploadRaceImage(race.id, file); onImageChange?.() }
    finally { setBusy(false); e.target.value = '' }
  }

  const removeImage = async () => {
    setBusy(true)
    try { await deleteRaceImage(race.id); onImageChange?.() }
    finally { setBusy(false) }
  }

  return (
    <div className={`${CARD} p-5 relative overflow-hidden group`} style={{ borderLeft: '3px solid #00d4ff' }}>
      {/* Foto als Hintergrund, stark abgedunkelt — der Text muss lesbar
          bleiben, das Bild trägt nur die Stimmung. */}
      {image && (
        <>
          <div className="absolute inset-0 pointer-events-none" style={{
            backgroundImage: `url(${image})`, backgroundSize: 'cover',
            backgroundPosition: 'center', opacity: 0.35,
          }} />
          <div className="absolute inset-0 pointer-events-none" style={{
            background: 'linear-gradient(100deg, #111318 18%, #111318cc 48%, #11131866 100%)',
          }} />
        </>
      )}

      {/* Diagonaler Lichtstreifen wie auf der Plan-Seite */}
      {!image && (
        <div className="absolute pointer-events-none" style={{
          top: '-60px', right: '-60px', width: '200px', height: '200px',
          background: 'radial-gradient(circle, #00d4ff10 0%, transparent 65%)',
        }} />
      )}

      <div className="relative z-10">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <SeriesBadge race={race} />
              <span className={LABEL}>{race.race_date} · {race.label}</span>
            </div>
            <h3 className="text-xl font-black tracking-tight text-[#e8eaf0] mt-1 truncate" style={DISPLAY}>
              {race.race_name.toUpperCase()}
            </h3>
            {race.location && (
              <div className="text-xs font-mono text-[var(--text-muted)] mt-0.5">{race.location}</div>
            )}
          </div>

          <div className="text-right flex-shrink-0">
            <div className="text-3xl font-black font-mono tabular-nums text-[#00d4ff]" style={DISPLAY}>
              {fmtTime(race.finish_time_s) || '—'}
            </div>
            {race.overall_rank && (
              <div className="text-[10px] font-mono text-[var(--text-secondary)]">
                Platz {race.overall_rank}{race.finishers ? ` / ${race.finishers}` : ''}
              </div>
            )}
            {race.age_group_rank && (
              <div className="text-[10px] font-mono text-[var(--text-secondary)]">
                AK {race.age_group}: {race.age_group_rank}
              </div>
            )}
          </div>
        </div>

        <SplitBar race={race} />

        {race.notes && (
          <p className="text-xs text-[var(--text-secondary)] leading-relaxed mt-3">{race.notes}</p>
        )}

        {/* Unten rechts statt oben rechts: oben steht die Zielzeit, und die
            Knöpfe lagen darüber. */}
        <div
          className="absolute bottom-0 right-0 flex items-center gap-3 pl-8 opacity-0 group-hover:opacity-100 transition-opacity"
          style={{
            // Weicher Verlauf darunter: bei langen Splits oder einer Notiz
            // liefen die Knöpfe sonst in den Text.
            background: image
              ? 'linear-gradient(90deg, transparent, #11131899 35%)'
              : 'linear-gradient(90deg, transparent, #111318 35%)',
          }}
        >
          <label
            className="text-[10px] font-mono text-[var(--text-muted)] hover:text-[#00d4ff] cursor-pointer"
            title={race.image_file ? 'Foto ersetzen' : 'Foto hinzufügen'}
          >
            {busy ? '…' : (race.image_file ? 'FOTO ▸' : '+ FOTO')}
            <input type="file" accept="image/jpeg,image/png,image/webp"
                   className="hidden" onChange={pick} disabled={busy} />
          </label>
          {race.image_file && (
            <button onClick={removeImage} disabled={busy}
                    className="text-[10px] font-mono text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
                    title="Foto entfernen">
              ✕FOTO
            </button>
          )}
          <button
            onClick={() => onEdit(race)}
            className="text-[10px] font-mono text-[var(--text-muted)] hover:text-[#00d4ff]"
            title="Ergebnis bearbeiten"
          >
            BEARBEITEN
          </button>
          <button
            onClick={() => onDelete(race.id)}
            className="text-xs text-[var(--text-muted)] hover:text-red-500 font-mono"
            title="Rennen entfernen"
          >
            ✕
          </button>
        </div>
      </div>
    </div>
  )
}

const FIELD = 'rounded-lg px-3 py-2 text-sm font-mono text-[#e8eaf0] placeholder-[var(--text-muted)] outline-none w-full'
const FIELD_STYLE = { background: '#0d0f17', border: '1px solid #1e2228' }

function Field({ label, ...props }) {
  return (
    <label className="block">
      <span className={`${LABEL} block mb-1`}>{label}</span>
      <input className={FIELD} style={FIELD_STYLE} {...props} />
    </label>
  )
}

export default function Races() {
  const [types, setTypes] = useState([])
  const [goal, setGoal] = useState(null)
  const [races, setRaces] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showGoalForm, setShowGoalForm] = useState(false)
  const [showRaceForm, setShowRaceForm] = useState(false)
  const [zones, setZones] = useState(null)
  // FTP aus einem Stufentest, von Hand eingetragen.
  const [stufenFtp, setStufenFtp] = useState('')

  const LEERES_ZIEL = {
    sport: 'triathlon', distance: 'middle', race_date: '', race_name: '',
    goal_time: '', priority: 'A',
  }
  const [goalForm, setGoalForm] = useState(LEERES_ZIEL)
  const [termine, setTermine] = useState([])
  const LEERES_RENNEN = {
    sport: 'triathlon', distance: 'middle', race_date: '', race_name: '', location: '',
    finish_time: '', swim_time: '', bike_time: '', run_time: '', overall_rank: '', notes: '',
  }
  const [raceForm, setRaceForm] = useState(LEERES_RENNEN)
  // id des bearbeiteten Rennens; null = neuer Eintrag.
  const [bearbeiteId, setBearbeiteId] = useState(null)

  /** Sekunden zurück ins Eingabeformat — sonst stünde beim Bearbeiten
   *  19794 statt 5:29:54 im Feld. */
  const alsZeit = (sekunden) => {
    if (!sekunden && sekunden !== 0) return ''
    const h = Math.floor(sekunden / 3600)
    const m = Math.floor((sekunden % 3600) / 60)
    const sek = sekunden % 60
    return h > 0
      ? `${h}:${String(m).padStart(2, '0')}:${String(sek).padStart(2, '0')}`
      : `${m}:${String(sek).padStart(2, '0')}`
  }

  const bearbeiten = (race) => {
    setBearbeiteId(race.id)
    setRaceForm({
      sport: race.sport, distance: race.distance, race_date: race.race_date,
      race_name: race.race_name || '', location: race.location || '',
      finish_time: alsZeit(race.finish_time_s), swim_time: alsZeit(race.swim_time_s),
      bike_time: alsZeit(race.bike_time_s), run_time: alsZeit(race.run_time_s),
      overall_rank: race.overall_rank ?? '', notes: race.notes || '',
    })
    setShowRaceForm(true)
  }

  const removeGoal = useCallback(async (id) => {
    if (!window.confirm('Diesen Wettkampf entfernen?')) return
    await deleteGoal(id)
    load()
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [t, r, u] = await Promise.all([getRaceTypes(), getRaces(), getUpcomingRaces()])
      setTypes(t.data.sports)
      setRaces(r.data)
      setTermine(u.data)
      try {
        const g = await getActiveGoal()
        setGoal(g.data)
      } catch { setGoal(null) }
    } catch (e) {
      setError('Daten konnten nicht geladen werden')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // Wann die nächste Testwoche ansteht. Eigener Aufruf mit eigenem
  // Fehlerfang: Die Seite soll auch ohne diese Auskunft benutzbar bleiben.
  useEffect(() => {
    getBenchmarkTiming()
      .then(({ data }) => setTestTermin(data))
      .catch(() => setTestTermin(null))
  }, [zones])

  const distancesFor = useCallback(
    (sport) => types.find(s => s.key === sport)?.distances || [],
    [types]
  )

  // Beim Wechsel der Sportart eine gültige Distanz nachziehen, sonst schickt
  // das Formular eine Kombination, die der Server ablehnt.
  const setSport = (setter, form) => (sport) => {
    const first = distancesFor(sport)[0]
    const neu = { ...form, sport, distance: first ? first.key : '' }
    // Teilzeiten gehören zum Triathlon. Beim Wechsel bleiben sie sonst
    // unsichtbar im Formular stehen und würden mitgespeichert — ein
    // Laufrennen hätte dann eine Schwimmzeit.
    if (sport !== 'triathlon' && 'swim_time' in neu) {
      neu.swim_time = ''
      neu.bike_time = ''
      neu.run_time = ''
    }
    setter(neu)
  }

  const submitGoal = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      const { data } = await createGoal({
        ...goalForm,
        race_name: goalForm.race_name || null,
        goal_time: goalForm.goal_time || null,
      })
      setGoal(data)
      setShowGoalForm(false)
      // Zurücksetzen wie beim Rennenformular. Ohne das standen Renntag,
      // Name und Zielzeit des gerade gespeicherten Wettkampfs beim nächsten
      // Öffnen noch im Formular — und weil ein Platzhalter nur in einem
      // leeren Feld erscheint, waren auch die Beispiele weg.
      //
      // Die Sportart bleibt: Sie wechselt zwischen zwei Einträgen praktisch
      // nie, und mit ihr wechselte die Auswahl der Distanzen.
      //
      // Die Art springt auf B, sobald ein Saisonziel steht. Ein zweites A
      // wäre kein weiterer Wettkampf, sondern würde das Ziel ersetzen und
      // die Saison neu rechnen — nichts, was man beiläufig tut, weil das
      // Formular noch auf A stand.
      setGoalForm({
        ...LEERES_ZIEL,
        sport: goalForm.sport,
        distance: goalForm.distance,
        priority: data?.priority === 'A' || goal ? 'B' : goalForm.priority,
      })
    } catch (err) {
      setError(err.response?.data?.detail || 'Ziel konnte nicht gespeichert werden')
    }
  }

  const submitRace = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      const payload = Object.fromEntries(
        Object.entries(raceForm).map(([k, v]) => [k, v === '' ? null : v])
      )
      if (payload.overall_rank) payload.overall_rank = Number(payload.overall_rank)
      if (bearbeiteId) await updateRace(bearbeiteId, payload)
      else await createRace(payload)
      setShowRaceForm(false)
      setBearbeiteId(null)
      setRaceForm(LEERES_RENNEN)
      load()
    } catch (err) {
      setError(err.response?.data?.detail || 'Rennen konnte nicht gespeichert werden')
    }
  }

  const remove = async (id) => {
    await deleteRace(id)
    setRaces(races.filter(r => r.id !== id))
  }

  const [benchmark, setBenchmark] = useState(null)
  const [testTermin, setTestTermin] = useState(null)
  const [busy, setBusy] = useState(null)

  const checkZones = async () => {
    setBusy('derive')
    try {
      const { data } = await deriveZones(false)
      setZones(data)
    } finally { setBusy(null) }
  }

  const applyZones = async () => {
    setBusy('apply')
    setError(null)
    try {
      const { data } = await deriveZones(true)
      setZones({ ...data, justApplied: true })
    } catch (err) {
      setError(err.response?.data?.detail || 'Zonen konnten nicht übernommen werden')
    } finally { setBusy(null) }
  }

  const planBenchmark = async () => {
    setBusy('plan')
    setError(null)
    try {
      const [{ data: week }, { data: created }] = await Promise.all([
        getBenchmarkWeek(), createBenchmarkPlan(),
      ])
      setBenchmark({ ...week, ...created })
    } catch (err) {
      // Die Sperre kommt als Objekt mit Gründen und Ersatztermin zurück, nicht
      // als Satz. Ohne diese Auswertung landete ein Objekt im JSX — React
      // rendert das nicht und die Seite bliebe stumm.
      const d = err.response?.data?.detail
      if (d && typeof d === 'object') {
        const ab = d.frueheste
          ? ` Frühestens ab ${formatTag(d.frueheste)}.`
          : ''
        setError(`${(d.gruende || []).join(' ')}${ab}`.trim() || d.message)
      } else {
        setError(d || 'Testwoche konnte nicht angelegt werden')
      }
    } finally { setBusy(null) }
  }

  const countdown = useMemo(() => (goal ? daysUntil(goal.race_date) : null), [goal])

  return (
    <div className="space-y-6 page-enter">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-3xl font-black tracking-tight text-[#e8eaf0]" style={DISPLAY}>
          RACES
        </h1>
        <div className="flex gap-2">
          <button
            onClick={() => setShowGoalForm(v => !v)}
            className="px-3 py-2 rounded-lg text-xs font-mono tracking-wide"
            style={{ background: '#00d4ff20', border: '1px solid #00d4ff44', color: '#00d4ff' }}
          >
            {goal ? 'NEUES ZIEL' : 'ZIEL SETZEN'}
          </button>
          <button
            onClick={() => setShowRaceForm(v => !v)}
            className="px-3 py-2 rounded-lg text-xs font-mono tracking-wide text-[var(--text-secondary)]"
            style={{ background: '#111318', border: '1px solid #1e2228' }}
          >
            + ERGEBNIS
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg px-3 py-2 font-mono text-xs"
             style={{ background: '#ef444415', border: '1px solid #ef444430', color: '#ef4444' }}>
          {error}
        </div>
      )}

      {loading && <div className="text-[var(--text-secondary)] font-mono text-sm py-6 text-center tracking-widest">LÄDT…</div>}

      {/* Aktives Ziel — der Countdown ist das Herzstück der Seite */}
      {!loading && goal && (
        <div className={`${CARD} p-6 relative overflow-hidden`}
             style={{ borderLeft: `3px solid ${countdown >= 0 ? '#00d4ff' : 'var(--text-muted)'}` }}>
          <div className="absolute pointer-events-none" style={{
            top: '-80px', left: '-40px', width: '320px', height: '260px',
            background: 'linear-gradient(135deg, #00d4ff12 0%, transparent 60%)', transform: 'rotate(-8deg)',
          }} />
          <div className="relative z-10 flex flex-wrap items-end justify-between gap-6">
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <SeriesBadge race={goal} />
                {/* Ein gelaufenes Rennen ist kein „aktuelles Ziel" mehr. */}
                <span className={LABEL}>
                  {countdown > 0 ? 'AKTUELLES ZIEL'
                    : countdown === 0 ? 'HEUTE IST RENNTAG'
                    : 'LETZTES ZIEL · SAISON ABGESCHLOSSEN'}
                </span>
              </div>
              <div className="text-2xl font-black tracking-tight text-[#e8eaf0] mt-1" style={DISPLAY}>
                {(goal.race_name || goal.label).toUpperCase()}
              </div>
              <div className="text-xs font-mono text-[var(--text-secondary)] mt-1">
                {goal.label} · {goal.race_date}
                {goal.goal_time ? ` · Ziel ${goal.goal_time}` : ''}
              </div>
              <div className="text-xs font-mono text-[var(--text-muted)] mt-0.5">
                {goal.total_weeks} Wochen ab {goal.plan_start_date}
              </div>
            </div>
            <div className="text-right">
              {countdown === 0 ? (
                <>
                  <div className="text-5xl font-black leading-none" style={{ ...DISPLAY, color: '#00d4ff' }}>
                    HEUTE
                  </div>
                  <div className={LABEL}>VIEL ERFOLG</div>
                </>
              ) : (
                <>
                  <div
                    className="text-6xl font-black leading-none tabular-nums"
                    style={{ ...DISPLAY, color: countdown > 0 ? '#00d4ff' : '#8a909e' }}
                  >
                    {Math.abs(countdown)}
                  </div>
                  <div className={LABEL}>
                    {countdown > 0 ? 'TAGE BIS ZUM RENNEN' : 'TAGE SEIT DEM RENNEN'}
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Ein gelaufenes Ziel bleibt stehen, zählt aber nichts mehr hoch.
              Ohne diesen Hinweis wirkt die Kachel, als liefe die Saison noch. */}
          {countdown < 0 && (
            <div className="relative z-10 mt-4 pt-4 border-t border-[#1e2228] flex items-center justify-between gap-3 flex-wrap">
              <div className="text-xs font-mono text-[var(--text-secondary)]">
                Saison abgeschlossen. Setze ein neues Ziel — daraus ergeben sich
                Planlänge, Phasen und die Wochenzählung neu.
              </div>
              <button
                onClick={() => setShowGoalForm(true)}
                className="px-3 py-1.5 rounded-lg text-[11px] font-mono tracking-wide flex-shrink-0"
                style={{ background: '#00d4ff20', border: '1px solid #00d4ff44', color: '#00d4ff' }}
              >
                NEUES ZIEL SETZEN
              </button>
            </div>
          )}
        </div>
      )}

      {/* Wettkämpfe unterwegs — sichtbar getrennt vom Saisonziel, damit
          niemand sie für das Ziel hält. */}
      {!loading && termine.length > 0 && (
        <div className={`${CARD} p-5`}>
          <div className="flex items-baseline justify-between gap-3 mb-3 flex-wrap">
            <span className={LABEL}>WETTKÄMPFE UNTERWEGS</span>
            <span className="text-[10px] font-mono text-[var(--text-muted)]">
              ÄNDERN DIE SAISONSTRUKTUR NICHT
            </span>
          </div>
          <div className="space-y-1">
            {termine.map(t => {
              const tage = daysUntil(t.race_date)
              const farbe = PRIO_COLOR[t.priority] || '#8a909e'
              return (
                <div key={t.id} className="flex items-center gap-3 px-3 py-2 rounded-lg"
                     style={{ background: '#0d0f17', border: '1px solid #1e2228' }}>
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded flex-shrink-0"
                        style={{ background: `${farbe}14`, border: `1px solid ${farbe}33`, color: farbe }}>
                    {t.priority}
                  </span>
                  <SeriesBadge race={t} />
                  <span className="text-sm font-mono text-[#e8eaf0] flex-1 min-w-0 truncate">
                    {t.race_name || t.label}
                  </span>
                  <span className="text-xs font-mono text-[var(--text-secondary)] hidden sm:block">{t.label}</span>
                  <span className="text-xs font-mono text-[var(--text-secondary)] tabular-nums">{t.race_date}</span>
                  <span className="text-xs font-mono tabular-nums w-16 text-right" style={{ color: farbe }}>
                    {tage >= 0 ? `in ${tage} T` : ''}
                  </span>
                  <button
                    onClick={() => removeGoal(t.id)}
                    className="text-xs text-[var(--text-muted)] hover:text-red-500 font-mono flex-shrink-0"
                    title="Wettkampf entfernen"
                  >
                    ✕
                  </button>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {!loading && !goal && (
        <div className={`${CARD} p-8 text-center`}>
          <div className="text-xl font-black text-[var(--text-muted)] mb-1" style={DISPLAY}>KEIN ZIEL GESETZT</div>
          <p className="text-sm font-mono text-[var(--text-muted)]">
            Wähle Sportart und Distanz — daraus ergeben sich Planlänge und Phasen.
          </p>
        </div>
      )}

      {/* Zielformular */}
      <Modal
        open={showGoalForm} onClose={() => setShowGoalForm(false)}
        title={goalForm.priority === 'A' ? 'SAISONZIEL SETZEN' : 'WETTKAMPF EINTRAGEN'}
        subtitle={goalForm.priority === 'A'
          ? 'Planlänge und Phasen ergeben sich aus der Distanz'
          : 'Liegt in der laufenden Saison — Planlänge und Phasen bleiben unverändert'}
        width="max-w-2xl"
      >
        <form onSubmit={submitGoal} className="space-y-4">
          {/* Zuerst die Art des Wettkampfs: davon hängt ab, ob die Saison neu
              gerechnet wird oder nur eine Woche angepasst. */}
          <div>
            <span className={`${LABEL} block mb-1`}>ART DES WETTKAMPFS</span>
            <div className="grid gap-1 sm:grid-cols-3">
              {PRIORITAETEN.map(p => (
                <button
                  key={p.key} type="button"
                  onClick={() => setGoalForm({ ...goalForm, priority: p.key })}
                  className="text-left px-3 py-2 rounded-lg transition-all"
                  style={{
                    background: goalForm.priority === p.key ? `${PRIO_COLOR[p.key]}14` : '#0d0f17',
                    border: `1px solid ${goalForm.priority === p.key ? PRIO_COLOR[p.key] + '44' : '#1e2228'}`,
                  }}
                >
                  <div className="text-[11px] font-mono tracking-wide"
                       style={{ color: goalForm.priority === p.key ? PRIO_COLOR[p.key] : '#8a909e' }}>
                    {p.key} · {p.label}
                  </div>
                  <div className="text-[10px] text-[var(--text-muted)] mt-0.5 leading-snug">{p.hint}</div>
                </button>
              ))}
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <label className="block">
              <span className={`${LABEL} block mb-1`}>SPORTART</span>
              <select
                className={FIELD} style={FIELD_STYLE} value={goalForm.sport}
                onChange={e => setSport(setGoalForm, goalForm)(e.target.value)}
              >
                {types.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
              </select>
            </label>
            <label className="block">
              <span className={`${LABEL} block mb-1`}>DISTANZ</span>
              <select
                className={FIELD} style={FIELD_STYLE} value={goalForm.distance}
                onChange={e => setGoalForm({ ...goalForm, distance: e.target.value })}
              >
                {/* Die Wochenzahl nur beim Saisonziel: Sie ist die Länge des
                    Aufbaus, und den bestimmt allein das A-Rennen. An einem
                    Trainingswettkampf gelesen sagt sie etwas, das nicht
                    stimmt — dort wird nichts geplant, die Einheit wird
                    mitgenommen. */}
                {distancesFor(goalForm.sport).map(d => (
                  <option key={d.key} value={d.key}>
                    {goalForm.priority === 'A' ? `${d.label} · ${d.weeks} Wochen` : d.label}
                  </option>
                ))}
              </select>
            </label>
            <Field label="RENNTAG" type="date" required
                   value={goalForm.race_date}
                   onChange={e => setGoalForm({ ...goalForm, race_date: e.target.value })} />
            <Field label="ZIELZEIT (OPTIONAL)" placeholder={beispielFuer(goalForm.sport).zielzeit}
                   value={goalForm.goal_time}
                   onChange={e => setGoalForm({ ...goalForm, goal_time: e.target.value })} />
          </div>
          <Field label="NAME DES RENNENS (OPTIONAL)" placeholder={beispielFuer(goalForm.sport).name}
                 value={goalForm.race_name}
                 onChange={e => setGoalForm({ ...goalForm, race_name: e.target.value })} />
          <div className="flex gap-2">
            <button type="submit" className="px-4 py-2 rounded-lg text-sm font-mono font-bold"
                    style={{ background: '#00d4ff20', border: '1px solid #00d4ff44', color: '#00d4ff' }}>
              ZIEL SPEICHERN
            </button>
            <button type="button" onClick={() => setShowGoalForm(false)}
                    className="px-4 py-2 rounded-lg text-sm font-mono text-[var(--text-secondary)]"
                    style={{ border: '1px solid #1e2228' }}>
              ABBRECHEN
            </button>
          </div>
          <p className="text-[11px] font-mono text-[var(--text-muted)]">
            {goalForm.priority === 'A'
              ? 'Ein neues Saisonziel setzt das bisherige inaktiv. Planlänge und Phasen ergeben sich aus der Distanz.'
              : 'Dieser Wettkampf ändert weder Planlänge noch Phasen — er wirkt nur auf die Woche, in die er fällt.'}
          </p>
        </form>
      </Modal>

      {/* Ergebnisformular */}
      <Modal
        open={showRaceForm}
        onClose={() => { setShowRaceForm(false); setBearbeiteId(null); setRaceForm(LEERES_RENNEN) }}
        title={bearbeiteId ? 'ERGEBNIS BEARBEITEN' : 'ERGEBNIS EINTRAGEN'}
        subtitle="Zeiten als H:MM:SS oder MM:SS"
        width="max-w-3xl"
      >
        <form onSubmit={submitRace} className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <label className="block">
              <span className={`${LABEL} block mb-1`}>SPORTART</span>
              <select className={FIELD} style={FIELD_STYLE} value={raceForm.sport}
                      onChange={e => setSport(setRaceForm, raceForm)(e.target.value)}>
                {types.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
              </select>
            </label>
            <label className="block">
              <span className={`${LABEL} block mb-1`}>DISTANZ</span>
              <select className={FIELD} style={FIELD_STYLE} value={raceForm.distance}
                      onChange={e => setRaceForm({ ...raceForm, distance: e.target.value })}>
                {distancesFor(raceForm.sport).map(d => (
                  <option key={d.key} value={d.key}>{d.label}</option>
                ))}
              </select>
            </label>
            <Field label="DATUM" type="date" required value={raceForm.race_date}
                   onChange={e => setRaceForm({ ...raceForm, race_date: e.target.value })} />
            <Field label="ORT" placeholder={beispielFuer(raceForm.sport).ort} value={raceForm.location}
                   onChange={e => setRaceForm({ ...raceForm, location: e.target.value })} />
          </div>
          <Field label="NAME" required placeholder={beispielFuer(raceForm.sport).name}
                 value={raceForm.race_name}
                 onChange={e => setRaceForm({ ...raceForm, race_name: e.target.value })} />
          {/* Teilzeiten gibt es nur beim Triathlon. Bei einem Laufrennen
              standen hier Felder für Schwimmen und Rad, die niemand füllen
              kann. */}
          <div className={`grid gap-3 sm:grid-cols-2 ${
            raceForm.sport === 'triathlon' ? 'lg:grid-cols-5' : 'lg:grid-cols-2'
          }`}>
            <Field label="GESAMTZEIT" placeholder={beispielFuer(raceForm.sport).zeit}
                   value={raceForm.finish_time}
                   onChange={e => setRaceForm({ ...raceForm, finish_time: e.target.value })} />
            {raceForm.sport === 'triathlon' && (
              <>
                <Field label="SCHWIMMEN" placeholder="34:20" value={raceForm.swim_time}
                       onChange={e => setRaceForm({ ...raceForm, swim_time: e.target.value })} />
                <Field label="RAD" placeholder="2:52:10" value={raceForm.bike_time}
                       onChange={e => setRaceForm({ ...raceForm, bike_time: e.target.value })} />
                <Field label="LAUFEN" placeholder="1:52:30" value={raceForm.run_time}
                       onChange={e => setRaceForm({ ...raceForm, run_time: e.target.value })} />
              </>
            )}
            <Field label="PLATZ" type="number" placeholder="412" value={raceForm.overall_rank}
                   onChange={e => setRaceForm({ ...raceForm, overall_rank: e.target.value })} />
          </div>
          <Field label="NOTIZEN" placeholder="Wie lief es? Was nimmst du mit?"
                 value={raceForm.notes}
                 onChange={e => setRaceForm({ ...raceForm, notes: e.target.value })} />
          <div className="flex gap-2">
            <button type="submit" className="px-4 py-2 rounded-lg text-sm font-mono font-bold"
                    style={{ background: '#00d4ff20', border: '1px solid #00d4ff44', color: '#00d4ff' }}>
              {bearbeiteId ? 'ÄNDERUNGEN SPEICHERN' : 'ERGEBNIS SPEICHERN'}
            </button>
            <button type="button"
                    onClick={() => { setShowRaceForm(false); setBearbeiteId(null); setRaceForm(LEERES_RENNEN) }}
                    className="px-4 py-2 rounded-lg text-sm font-mono text-[var(--text-secondary)]"
                    style={{ border: '1px solid #1e2228' }}>
              ABBRECHEN
            </button>
          </div>
        </form>
      </Modal>

      {/* Achievements */}
      {!loading && (
        <div className="space-y-3">
          <div className="flex items-baseline gap-3">
            <h2 className="text-xl font-black tracking-tight text-[#e8eaf0]" style={DISPLAY}>ACHIEVEMENTS</h2>
            <span className="text-sm font-mono text-[var(--text-muted)]">
              {races.length} {races.length === 1 ? 'Rennen' : 'Rennen'}
            </span>
          </div>

          {races.length === 0 ? (
            <div className={`${CARD} p-8 text-center`}>
              <div className="text-4xl mb-2 opacity-40">🏅</div>
              <p className="text-sm font-mono text-[var(--text-muted)]">
                Noch keine Rennen erfasst. Trag dein erstes über „+ Ergebnis" ein.
              </p>
            </div>
          ) : (
            <div className="grid gap-3 md:grid-cols-2">
              {races.map(r => (
                <RaceCard key={r.id} race={r} onDelete={remove}
                          onEdit={bearbeiten} onImageChange={load} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Zonen aus Testeinheiten */}
      {!loading && (
        <div className={`${CARD} p-5`}>
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div>
              <div className={LABEL}>BENCHMARK</div>
              <p className="text-sm text-[var(--text-secondary)] mt-1">
                Zonen aus deinen Testeinheiten ableiten statt schätzen.
              </p>
              {/* Wann der nächste Test ansteht — sonst erfährt man erst beim
                  Anlegen, dass es noch zu früh ist, und hat die Woche
                  womöglich schon verplant. */}
              {testTermin?.vorwarnung ? (
                <p className="text-[11px] font-mono mt-2 leading-relaxed max-w-md"
                   style={{ color: '#f59e0b' }}>
                  {testTermin.vorwarnung}
                </p>
              ) : testTermin?.faellig_am ? (
                <p className="text-[11px] font-mono mt-2 text-[var(--text-muted)]">
                  Nächste Testwoche ab {testTermin.faellig_am}
                  {testTermin.tage_bis_faellig != null && ` · in ${testTermin.tage_bis_faellig} Tagen`}
                </p>
              ) : null}
            </div>
            <div className="flex gap-2 flex-wrap">
              <button onClick={planBenchmark} disabled={busy === 'plan'}
                      className="px-3 py-2 rounded-lg text-xs font-mono tracking-wide text-[var(--text-secondary)] disabled:opacity-40"
                      style={{ background: '#111318', border: '1px solid #1e2228' }}>
                {busy === 'plan' ? 'LEGT AN…' : 'TESTWOCHE PLANEN'}
              </button>
              <button onClick={checkZones} disabled={busy === 'derive'}
                      className="px-3 py-2 rounded-lg text-xs font-mono tracking-wide text-[#00d4ff] disabled:opacity-40"
                      style={{ background: '#00d4ff15', border: '1px solid #00d4ff33' }}>
                {busy === 'derive' ? 'RECHNET…' : 'WERTE BERECHNEN'}
              </button>
            </div>
          </div>

          {/* Angelegte Testwoche */}
          {benchmark && (
            <div className="mt-4 rounded-lg p-3" style={{ background: '#0d0f17', border: '1px solid #1e2228' }}>
              <div className="text-xs font-mono text-[#00d4ff] mb-2">
                {benchmark.message} · ab {benchmark.week_start}
              </div>
              <div className="space-y-0.5">
                {benchmark.days?.filter(d => d.session_type !== 'rest').map(d => (
                  <div key={d.day} className="text-[11px] font-mono text-[var(--text-secondary)]">
                    <span className="text-[var(--text-muted)]">{d.day.slice(0, 2)}</span>{' '}
                    {d.session_type} {d.duration_min}min — {(d.notes || '').split(':')[0]}
                  </div>
                ))}
              </div>
            </div>
          )}

          {zones && (
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              {(() => {
                const pace = (v) => v
                  ? `${Math.floor(v / 60)}:${String(Math.round(v % 60)).padStart(2, '0')}`
                  : null
                const jetzt = zones.current || {}
                return [
                  { label: 'FTP', neu: zones.ftp_watts, alt: jetzt.ftp_watts, einheit: 'W' },
                  { label: 'SCHWELLENPACE', neu: pace(zones.threshold_pace_s_per_km), alt: pace(jetzt.threshold_pace_s_per_km), einheit: '/km' },
                  { label: 'SCHWELLENPULS', neu: zones.threshold_hr, alt: jetzt.threshold_hr, einheit: 'bpm' },
                  { label: 'MAX. HF', neu: zones.max_hr, alt: jetzt.max_hr, einheit: 'bpm' },
                  { label: 'CSS', neu: pace(zones.css_pace_s_per_100m), alt: pace(jetzt.css_pace_s_per_100m), einheit: '/100m' },
                  { label: 'PULS SCHWIMMEN', neu: zones.swim_threshold_hr, alt: jetzt.swim_threshold_hr, einheit: 'bpm' },
                ]
              })().map(({ label, neu, alt, einheit }) => {
                const aendert = neu != null && String(neu) !== String(alt ?? '')
                return (
                  <div key={label} className="rounded-lg p-3"
                       style={{ background: '#0d0f17', border: `1px solid ${aendert ? '#f59e0b33' : '#1e2228'}` }}>
                    <div className={LABEL}>{label}</div>
                    {/* Alt gegen neu: Ohne den Vergleich übernimmt man Zahlen,
                        ohne zu sehen, was sie ersetzen. */}
                    <div className="flex items-baseline gap-2 mt-0.5 flex-wrap">
                      {alt != null && aendert && (
                        <span className="text-sm font-mono text-[var(--text-muted)] line-through">{alt}</span>
                      )}
                      <span className="text-xl font-black font-mono" style={{ ...DISPLAY, color: neu == null ? 'var(--text-muted)' : aendert ? '#f59e0b' : '#e8eaf0' }}>
                        {neu ?? (alt != null ? alt : '—')}
                      </span>
                      {(neu ?? alt) != null && (
                        <span className="text-[10px] font-mono text-[var(--text-secondary)]">{einheit}</span>
                      )}
                    </div>
                    {neu == null && alt != null && (
                      <div className="text-[9px] font-mono text-[var(--text-muted)] mt-1">bleibt unverändert</div>
                    )}
                  </div>
                )
              })}
              {/* Stufentest erkannt: Der Trainer hat die FTP schon ausgerechnet,
                  sie steht nur nicht in der App. Statt den Athleten ins Profil zu
                  schicken, kann er sie hier eintragen — an der Stelle, an der er
                  gerade nach ihr sucht. */}
              {zones.ftp_hinweis && (
                <div className="sm:col-span-3 rounded-lg p-3"
                     style={{ background: '#f59e0b0d', border: '1px solid #f59e0b33' }}>
                  <div className={LABEL} style={{ color: '#f59e0b' }}>FTP EINTRAGEN</div>
                  <p className="text-[11px] font-mono text-[var(--text-secondary)] mt-1 leading-relaxed">
                    {zones.ftp_hinweis}
                  </p>
                  <div className="flex gap-2 items-center mt-2 flex-wrap">
                    <input
                      type="number" inputMode="numeric"
                      className={FIELD} style={{ ...FIELD_STYLE, maxWidth: '140px' }}
                      placeholder="z. B. 264"
                      value={stufenFtp}
                      onChange={e => setStufenFtp(e.target.value)}
                    />
                    <span className="text-[11px] font-mono text-[var(--text-muted)]">Watt</span>
                    <button
                      disabled={!stufenFtp || busy === 'ftp'}
                      onClick={async () => {
                        setBusy('ftp'); setError(null)
                        try {
                          await updateProfile({ ftp_watts: Number(stufenFtp) })
                          setStufenFtp('')
                          await checkZones()
                        } catch (err) {
                          setError(err.response?.data?.detail || 'FTP konnte nicht gespeichert werden')
                        } finally { setBusy(null) }
                      }}
                      className="px-3 py-1.5 rounded-lg text-[11px] font-mono tracking-wide disabled:opacity-40"
                      style={{ background: '#f59e0b20', border: '1px solid #f59e0b44', color: '#f59e0b' }}>
                      {busy === 'ftp' ? 'SPEICHERT…' : 'FTP SPEICHERN'}
                    </button>
                  </div>
                  <p className="text-[10px] font-mono text-[var(--text-muted)] mt-2 leading-relaxed">
                    Die Wattzonen ergeben sich daraus von selbst — sie werden aus der
                    FTP gerechnet, nicht getrennt gespeichert.
                  </p>
                </div>
              )}

              <div className="sm:col-span-3 flex items-center gap-3 flex-wrap">
                {zones.justApplied ? (
                  <span className="text-[11px] font-mono" style={{ color: '#22c55e' }}>
                    ✓ Übernommen: {(zones.applied || []).join(', ')}
                  </span>
                ) : (
                  <button onClick={applyZones} disabled={busy === 'apply'}
                          className="px-3 py-1.5 rounded-lg text-[11px] font-mono tracking-wide disabled:opacity-40"
                          style={{ background: '#22c55e15', border: '1px solid #22c55e40', color: '#22c55e' }}>
                    {busy === 'apply' ? 'ÜBERNIMMT…' : 'INS PROFIL ÜBERNEHMEN'}
                  </button>
                )}
                <p className="text-[11px] font-mono text-[var(--text-muted)] leading-relaxed flex-1 min-w-[240px]">
                  Aussagekräftig erst nach einem echten Test — aus einer ruhigen Ausfahrt
                  errechnet sich zwangsläufig eine zu niedrige FTP. Orange markierte Werte
                  ersetzen beim Übernehmen den bisherigen Stand, auch von Hand eingetragene.
                  Danach lässt sich im Profil alles einzeln korrigieren.
                </p>
              </div>
            </div>
          )}
        </div>
      )}

      {!loading && <BenchmarkGuide />}
    </div>
  )
}
