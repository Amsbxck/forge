import { useEffect, useState, useMemo } from 'react'
import {
  getSessions, getSessionsSeit, getHistoryPlans, getSaison,
  softDeleteSession, hardDeleteSession, restoreSession, setSessionCommute
} from '../services/api'
import SessionDetail from '../components/SessionDetail'
import SegmentLeiste from '../components/leisten/SegmentLeiste'
import WochenVolumen from '../components/leisten/WochenVolumen'
import TrainingsJahr from '../components/leisten/TrainingsJahr'
import { blockName } from '../components/leisten/SaisonStrahl'

import { ACCENT, DISCIPLINE_COLOR, DISCIPLINE_LABEL, INTENSITY_META, STATUS_COLOR, phaseColor } from '../utils/colors'
import SportIcon from '../components/SportIcon'
import { isoTag, paceText, parseTag } from '../utils/dates'
import { SPORTEN, montagVon, sportVon, stunden, veraenderung, wochenSummen, zeitraum } from '../utils/einheiten'
import { phaseFamilie } from '../utils/phasen'
import { fehlerText } from '../utils/fehler'
import { disciplineLabel } from '../utils/colors'

// ─── Constants ────────────────────────────────────────────────────────────────

const DISC_CONFIG = Object.fromEntries(
  ['bike', 'run', 'swim', 'gym', 'brick', 'hike', 'other'].map(k => [
    k,
    {
      key: k, label: DISCIPLINE_LABEL[k],
      color: DISCIPLINE_COLOR[k], borderColor: DISCIPLINE_COLOR[k],
    },
  ])
)

const MONTH_NAMES = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

function formatMonth(ym) {
  const [y, m] = ym.split('-')
  return `${MONTH_NAMES[parseInt(m) - 1]} ${y}`
}

function formatDuration(min) {
  if (!min) return null
  const h = Math.floor(min / 60)
  const m = min % 60
  return h > 0 ? `${h}h ${m > 0 ? `${m}m` : ''}`.trim() : `${m}m`
}

function formatPace(val, disc) {
  if (!val) return null
  return paceText(val, disc)
}

// ─── Progress Tab ─────────────────────────────────────────────────────────────
//
// Vorher: ein Stufendiagramm, das nur innerhalb eines Monats aufsummierte,
// Summen über alles seit jeher und vier Sportart-Karten. Jetzt in der Optik
// der Anzeige-Leisten (englisch beschriftet wie sie): Zeitraum mit Vergleich,
// Wochenvolumen mit Phasenband, Trainingsjahr, Bestwerte.

const CARD = 'bg-[#111318] border border-[#1e2228] rounded-xl p-5'
const KOPF = 'text-[9px] font-mono tracking-[0.2em] text-[var(--text-muted)]'
const DISPLAY = { fontFamily: 'Barlow Condensed, sans-serif' }

const ZEITRAEUME = [
  { tage: 28, label: '4W' },
  { tage: 84, label: '12W' },
  { tage: 364, label: 'YEAR' },
]

const kurzTag = tag =>
  parseTag(tag).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: '2-digit' }).toUpperCase()

function Schalter({ optionen, wert, onWahl }) {
  return (
    <div className="flex rounded-lg p-0.5" style={{ background: '#0d0f14', border: '1px solid #1e2228' }}>
      {optionen.map(o => (
        <button
          key={o.wert}
          onClick={() => onWahl(o.wert)}
          className="px-2.5 py-1 rounded-md text-[10px] font-mono tracking-widest transition-colors"
          style={{
            color: wert === o.wert ? ACCENT : '#8a909e',
            background: wert === o.wert ? `${ACCENT}1f` : 'transparent',
            boxShadow: wert === o.wert ? `inset 0 0 0 1px ${ACCENT}44` : 'none',
          }}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

/** Summen eines Zeitraums, mit der Veränderung zum Zeitraum davor.
 *
 *  Grün nach oben, Gelb erst ab −15 %: Weniger ist nicht automatisch
 *  schlecht — eine Deload- oder Taperwoche soll weniger haben.
 */
function Zeitraum({ sessions }) {
  const [tage, setTage] = useState(28)
  const { jetzt, davor } = useMemo(() => zeitraum(sessions, tage), [sessions, tage])
  const felder = [
    { name: 'TIME', wert: stunden(jetzt.min), delta: veraenderung(jetzt.min, davor.min) },
    { name: 'SESSIONS', wert: jetzt.n, delta: veraenderung(jetzt.n, davor.n) },
    { name: 'DISTANCE', wert: Math.round(jetzt.km), einheit: 'km', delta: veraenderung(jetzt.km, davor.km) },
    { name: 'TSS', wert: Math.round(jetzt.tss), delta: veraenderung(jetzt.tss, davor.tss) },
  ]
  const segmente = SPORTEN.filter(sp => jetzt.jeSport[sp]).map(sp => ({
    key: sp,
    name: (DISCIPLINE_LABEL[sp] || sp).toUpperCase(),
    wert: jetzt.jeSport[sp],
    farbe: DISCIPLINE_COLOR[sp] || DISCIPLINE_COLOR.other,
    textFarbe: DISCIPLINE_COLOR[sp] || DISCIPLINE_COLOR.other,
  }))

  return (
    <div className={CARD}>
      <div className="flex items-end justify-between gap-x-4 gap-y-3 flex-wrap mb-5">
        <div className="grid grid-cols-2 sm:flex gap-y-3">
          {felder.map((f, i) => (
            <div key={f.name} className={`pr-5 ${i % 2 ? 'pl-5 border-l border-[#1e2228]' : ''} sm:pl-5 sm:first:pl-0 ${i ? 'sm:border-l sm:border-[#1e2228]' : 'sm:border-l-0'}`}>
              <div className={KOPF}>{f.name}</div>
              <div className="flex items-baseline gap-1 mt-1.5">
                <span className="text-3xl font-black leading-none tabular-nums text-[#e8eaf0]" style={DISPLAY}>{f.wert}</span>
                {f.einheit && <span className="text-[10px] font-mono text-[var(--text-muted)]">{f.einheit}</span>}
              </div>
              <div
                className="mt-1 text-[10px] font-mono tabular-nums h-3.5"
                style={{
                  color: f.delta == null ? 'var(--text-muted)'
                    : f.delta > 0.5 ? STATUS_COLOR.green : f.delta < -15 ? STATUS_COLOR.yellow : '#a7aebd',
                }}
              >
                {f.delta == null ? '—' : `${f.delta > 0 ? '+' : f.delta < 0 ? '−' : '±'}${Math.abs(Math.round(f.delta))} %`}
              </div>
            </div>
          ))}
        </div>
        <Schalter
          optionen={ZEITRAEUME.map(z => ({ wert: z.tage, label: z.label }))}
          wert={tage}
          onWahl={setTage}
        />
      </div>
      {segmente.length > 0 ? (
        <SegmentLeiste kopf="TIME BY SPORT" mindestens={1} segmente={segmente} />
      ) : (
        <div className="text-[10px] font-mono text-[var(--text-muted)]">No sessions in this period.</div>
      )}
    </div>
  )
}

/** Längste, weiteste und stärkste Einheit je Sportart.
 *
 *  Über den geladenen Zeitraum (zwei Jahre) — und so beschriftet, damit
 *  niemand einen Rekord für ewig hält, der nur der beste der letzten zwei
 *  Jahre ist. Distanz nicht beim Kraftraining, dort gibt es keine.
 */
function Rekorde({ sessions, onOeffnen }) {
  const zeilen = useMemo(() => {
    const aktiv = sessions.filter(s => !s.deleted_at)
    return SPORTEN.map(sp => {
      const eigene = aktiv.filter(s => sportVon(s) === sp)
      if (!eigene.length) return null
      const bester = feld => eigene.reduce((a, b) => ((b[feld] || 0) > (a?.[feld] || 0) ? b : a), null)
      return {
        sport: sp,
        werte: [
          { name: 'LONGEST', s: bester('duration_min'), text: x => formatDuration(x.duration_min) },
          sp !== 'gym' && { name: 'FARTHEST', s: bester('distance_km'), text: x => `${x.distance_km.toFixed(1)} km` },
          { name: 'HIGHEST TSS', s: bester('tss'), text: x => `${Math.round(x.tss)}` },
        ].filter(w => w && w.s && w.s[{ LONGEST: 'duration_min', FARTHEST: 'distance_km', 'HIGHEST TSS': 'tss' }[w.name]]),
      }
    }).filter(z => z && z.werte.length)
  }, [sessions])

  if (!zeilen.length) return null
  return (
    <div className={CARD}>
      <div className={`${KOPF} mb-3`}>RECORDS · LAST 2 YEARS</div>
      <div className="divide-y divide-[#1e2228]">
        {zeilen.map(z => {
          const farbe = DISCIPLINE_COLOR[z.sport] || DISCIPLINE_COLOR.other
          return (
            <div key={z.sport} className="grid grid-cols-[5.5rem_1fr] sm:grid-cols-[7rem_1fr] gap-3 py-2.5 items-center">
              <span className="flex items-center gap-2 text-sm font-bold tracking-wide" style={{ ...DISPLAY, color: farbe }}>
                <SportIcon discipline={z.sport} size={15} color={farbe} />
                {(DISCIPLINE_LABEL[z.sport] || z.sport).toUpperCase()}
              </span>
              <div className="grid grid-cols-3 gap-3">
                {z.werte.map(w => (
                  <button
                    key={w.name}
                    onClick={() => onOeffnen(w.s)}
                    className="text-left rounded-md px-2 py-1 -mx-2 hover:bg-[#0d0f17] transition-colors min-w-0"
                    title="Open session"
                  >
                    <div className="text-[8px] font-mono tracking-[0.18em] text-[var(--text-muted)] truncate">{w.name}</div>
                    <div className="text-lg font-black leading-tight tabular-nums text-[#e8eaf0] truncate" style={DISPLAY}>{w.text(w.s)}</div>
                    <div className="text-[9px] font-mono text-[var(--text-muted)] truncate">{kurzTag(w.s.session_date)}</div>
                  </button>
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function ProgressTab({ sessions, volle, plaene, saison }) {
  const [offen, setOffen] = useState(null)
  const active = useMemo(() => sessions.filter(s => !s.deleted_at), [sessions])

  if (!active.length) {
    return <div className="text-center py-8 text-[var(--text-secondary)] text-sm">No sessions yet.</div>
  }

  // Für das Modal die volle Einheit (mit Zeitreihen), wenn sie geladen ist —
  // die zwei Jahre fürs Diagramm kommen ohne.
  const oeffnen = s => setOffen(volle.find(v => v.id === s.id) || s)

  return (
    <div className="space-y-4">
      {offen && <SessionDetail session={offen} onClose={() => setOffen(null)} />}
      <Zeitraum sessions={active} />
      <div className={CARD}>
        <WochenVolumen sessions={active} plaene={plaene} saison={saison} />
      </div>
      <div className={CARD}>
        <TrainingsJahr sessions={active} />
      </div>
      <Rekorde sessions={active} onOeffnen={oeffnen} />
    </div>
  )
}

// ─── Sessions Timeline ─────────────────────────────────────────────────────────

function SessionRow({ session: s, onDelete, onHardDelete, onRestore, onCommute, onClick }) {
  const disc = s.discipline?.toLowerCase()
  const cfg = DISC_CONFIG[disc] || { key: disc, color: 'var(--text-secondary)' }
  const intensity = INTENSITY_META[s.intensity]
  // "Ungeplantes Training" ist keine Abweichung im engeren Sinn — das wäre
  // bei ungeplanten Wochen sonst ein Warndreieck in jeder zweiten Zeile.
  const deviation = s.deviation_note && !s.deviation_note.startsWith('Keine geplante')
    ? s.deviation_note
    : null
  const unplanned = Boolean(s.deviation_note?.startsWith('Keine geplante'))

  return (
    <div
      className={`flex items-center gap-3 px-4 py-3 border-l-2 hover:bg-[#111318] transition-colors cursor-pointer group ${s.deleted_at ? 'opacity-40' : ''}`}
      style={{ borderLeftColor: cfg.color }}
      onClick={onClick}
    >
      <div className="flex-shrink-0 w-6 flex justify-center">
        <SportIcon discipline={cfg.key} size={16} color={cfg.color} />
      </div>
      <div className="w-14 flex-shrink-0 font-mono text-xs text-[var(--text-secondary)]">{s.session_date?.slice(5)}</div>
      <div className="w-18 flex-shrink-0 text-xs text-[#e8eaf0] hidden sm:block">{cfg.label}</div>

      {/* Klassifizierung: Intensitätsstufe und erkannter Trainingstyp */}
      <div className="flex items-center gap-1.5 flex-shrink-0">
        {intensity && (
          <span
            className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded leading-none whitespace-nowrap"
            style={{ color: intensity.color, background: `${intensity.color}1e`, border: `1px solid ${intensity.color}44` }}
            title={`Intensität ${intensity.short} (${intensity.zone})`}
          >
            {intensity.short}
          </span>
        )}
        {s.is_commute && (
          <span
            className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded leading-none whitespace-nowrap"
            style={{ color: '#7b8496', background: '#7b849618', border: '1px solid #7b849644' }}
            title="Arbeitsweg — zählt in die Formkurve, gilt aber nicht als geplante Einheit"
          >
            WEG
          </span>
        )}
        {s.actual_type && (
          <span className="text-[10px] font-mono text-[var(--text-secondary)] hidden lg:inline whitespace-nowrap">
            {s.actual_type.replace(/_/g, ' ')}
          </span>
        )}
      </div>

      <div className="flex gap-3 flex-1 min-w-0 flex-wrap">
        {s.duration_min && <span className="text-xs font-mono text-[var(--text-secondary)]">{formatDuration(s.duration_min)}</span>}
        {s.distance_km && <span className="text-xs font-mono text-[var(--text-secondary)]">{s.distance_km} km</span>}
        {s.avg_watts && <span className="text-xs font-mono text-[var(--text-secondary)]">{s.avg_watts}W</span>}
        {s.avg_pace_min_km && <span className="text-xs font-mono text-[var(--text-secondary)]">{formatPace(s.avg_pace_min_km, disc)}</span>}
        {s.tss && <span className="text-xs font-mono font-semibold" style={{ color: cfg.color }}>{s.tss.toFixed(0)} TSS</span>}
        {s.avg_hr && <span className="text-xs font-mono text-[var(--text-secondary)]">{s.avg_hr} bpm</span>}
      </div>

      {/* Soll/Ist — nur wenn es wirklich abwich. Volltext im Tooltip. */}
      {(deviation || unplanned) && (
        <span
          className="text-[10px] font-mono flex-shrink-0 cursor-help leading-none"
          style={{ color: deviation ? '#f4a261' : 'var(--text-muted)' }}
          title={deviation || 'Ungeplantes Training — keine Einheit im Plan zugeordnet'}
        >
          {deviation ? '⚠' : '○'}
        </span>
      )}

      {s.hr_zones && (
        <div className="flex gap-0.5 items-end h-5 flex-shrink-0 hidden md:flex">
          {['z1','z2','z3','z4','z5'].map((z, i) => {
            const val = s.hr_zones[z] || 0
            const zoneColors = ['#3b82f6','#22c55e','#eab308','#f97316','#ef4444']
            return <div key={z} className="w-1.5 rounded-sm" style={{ height: `${Math.max(2, val * 0.18)}px`, background: zoneColors[i], opacity: val > 0 ? 0.8 : 0.2 }} />
          })}
        </div>
      )}

      <div
        className="flex gap-2 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
        onClick={e => e.stopPropagation()}
      >
        {/* Nur bei Fahrten mit Strecke. Eine Hallenfahrt auf dem Ergometer
            hat 0 km und kann kein Arbeitsweg sein — der Knopf dort anzubieten
            stiftet nur Verwirrung.

            Und mit Vorzeichen beschriftet, wie "+ ERSETZT" im Wochenkalender.
            Vorher stand dort bei einer nicht markierten Fahrt nur
            "ARBEITSWEG", in derselben grauen Monospace wie die Messwerte
            daneben — das liest sich als Etikett ("diese Fahrt ist ein
            Arbeitsweg") statt als Handlung. Genau so ist es passiert: Taminas
            Hallenfahrt galt als Arbeitsweg gemeldet, obwohl `is_commute`
            false war. */}
        {!s.deleted_at && s.discipline === 'bike' && (s.is_commute || s.distance_km > 0) && (
          <button
            onClick={onCommute}
            className="text-[10px] font-mono text-[var(--text-muted)] hover:text-[#e8eaf0] whitespace-nowrap"
            title={s.is_commute
              ? 'Markierung aufheben — die Einheit wird wieder dem Plan zugeordnet'
              : 'Als Arbeitsweg markieren — bleibt in der Formkurve, erfüllt aber keine Vorgabe'}
          >
            {s.is_commute ? '✕ ARBEITSWEG' : '+ ARBEITSWEG'}
          </button>
        )}
        {s.deleted_at ? (
          <>
            <button onClick={onRestore} className="text-xs text-green-500 hover:text-green-400 font-mono">↩</button>
            <button onClick={onHardDelete} className="text-xs text-red-500 hover:text-red-400 font-mono">✕</button>
          </>
        ) : (
          <button onClick={onDelete} className="text-xs text-[var(--text-muted)] hover:text-red-500 font-mono transition-colors">✕</button>
        )}
      </div>
    </div>
  )
}

function SessionsTab({ sessions, showDeleted, onToggleDeleted, onRefresh }) {
  const [filter, setFilter] = useState('all')
  const [openMonths, setOpenMonths] = useState(null)
  const [selectedSession, setSelectedSession] = useState(null)

  const filtered = useMemo(() => sessions.filter(s => {
    if (!showDeleted && s.deleted_at) return false
    if (filter !== 'all' && s.discipline?.toLowerCase() !== filter) return false
    return true
  }), [sessions, filter, showDeleted])

  const grouped = useMemo(() => {
    const map = {}
    filtered.forEach(s => {
      const key = s.session_date?.slice(0, 7) || 'unknown'
      if (!map[key]) map[key] = []
      map[key].push(s)
    })
    return Object.entries(map).sort(([a], [b]) => b.localeCompare(a))
  }, [filtered])

  const effectiveOpenMonths = useMemo(() => {
    if (openMonths !== null) return openMonths
    if (!grouped.length) return new Set()
    return new Set([grouped[0][0]])
  }, [openMonths, grouped])

  const toggleMonth = (ym) => {
    setOpenMonths(prev => {
      const base = prev ?? effectiveOpenMonths
      const next = new Set(base)
      next.has(ym) ? next.delete(ym) : next.add(ym)
      return next
    })
  }

  const [vaultHinweis, setVaultHinweis] = useState(null)

  const handleSoftDelete = async (id) => { await softDeleteSession(id); onRefresh() }
  const handleHardDelete = async (id) => {
    if (!confirm('Endgültig löschen? Auch die Notiz im Obsidian-Vault wird entfernt. Das ist nicht umkehrbar.')) return
    const { data } = await hardDeleteSession(id)
    // Was mit der Notiz passiert ist, gehört gesagt: Ist der Vault gerade
    // nicht erreichbar, bleibt sie dort liegen — und niemand sucht später
    // eine Notiz, von der er glaubt, sie sei gelöscht.
    const stand = data?.vault?.status
    if (stand === 'unavailable' || stand === 'error') {
      setVaultHinweis({
        ok: false,
        text: `Einheit gelöscht, aber die Notiz ${data.vault.path} liegt noch im Vault — er war nicht erreichbar. Bitte dort von Hand löschen.`,
      })
    } else if (stand === 'behalten_eigene_note') {
      setVaultHinweis({
        ok: true,
        text: `Einheit gelöscht. Die Notiz ${data.vault.path} bleibt stehen: du hast sie überarbeitet.`,
      })
    } else if (stand === 'gelöscht') {
      setVaultHinweis({ ok: true, text: 'Einheit und Notiz im Vault gelöscht.' })
    }
    onRefresh()
  }
  const handleRestore = async (id) => { await restoreSession(id); onRefresh() }
  const handleCommute = async (id, wert) => { await setSessionCommute(id, wert); onRefresh() }

  return (
    <div className="space-y-4">
      {selectedSession && <SessionDetail session={selectedSession} onClose={() => setSelectedSession(null)} />}

      {vaultHinweis && (
        <div className="rounded-xl px-4 py-3 font-mono text-[11px] flex items-start gap-3"
             style={{
               background: vaultHinweis.ok ? '#10b98112' : '#f59e0b14',
               border: `1px solid ${vaultHinweis.ok ? '#10b98133' : '#f59e0b40'}`,
               color: vaultHinweis.ok ? '#10b981' : '#f59e0b',
             }}>
          <span className="flex-1 break-all">{vaultHinweis.text}</span>
          <button onClick={() => setVaultHinweis(null)} className="opacity-60 hover:opacity-100">✕</button>
        </div>
      )}

      {/* Filter bar */}
      <div className="flex gap-2 flex-wrap items-center justify-between">
        <div className="flex gap-2 flex-wrap">
          {['all', 'bike', 'run', 'swim', 'gym', 'hike'].map(d => {
            const cfg = DISC_CONFIG[d]
            const isActive = filter === d
            return (
              <button
                key={d}
                onClick={() => setFilter(d)}
                className="px-3 py-1.5 rounded-lg text-xs font-mono transition-all border"
                style={{
                  borderColor: isActive ? (cfg?.color || '#00d4ff') : '#1e2228',
                  color: isActive ? (cfg?.color || '#00d4ff') : '#8a909e',
                  background: isActive ? `${cfg?.color || '#00d4ff'}15` : '#111318',
                }}
              >
                {d === 'all' ? 'All' : cfg?.label || d}
              </button>
            )
          })}
        </div>
        <button
          onClick={onToggleDeleted}
          className={`text-xs px-3 py-1.5 rounded-lg border font-mono transition-colors ${showDeleted ? 'border-red-500/40 text-red-400 bg-red-500/10' : 'border-[#1e2228] text-[var(--text-muted)] hover:text-[var(--text-secondary)]'}`}
        >
          {showDeleted ? 'Gelöschte ausblenden' : 'Gelöschte zeigen'}
        </button>
      </div>

      {grouped.length === 0 && <div className="text-center py-8 text-[var(--text-secondary)] text-sm">No sessions found.</div>}

      {grouped.map(([ym, monthSessions]) => {
        const isOpen = effectiveOpenMonths.has(ym)
        const sorted = [...monthSessions].sort((a, b) => b.session_date?.localeCompare(a.session_date))

        // Monatskopf als Leiste: Stunden groß, darunter die Stunden je
        // Sportart, rechts eine Säule je Kalenderwoche des Monats. Vorher
        // standen dort „12 sessions · 14.3h · 820 TSS" und Sportart-Chips —
        // dieselben Zahlen, aber ohne Verhältnis zueinander.
        const aktiveImMonat = monthSessions.filter(s => !s.deleted_at)
        const summeMin = aktiveImMonat.reduce((acc, s) => acc + (s.duration_min || 0), 0)
        const totalTSS = aktiveImMonat.reduce((acc, s) => acc + (s.tss || 0), 0)
        const jeSport = {}
        aktiveImMonat.forEach(s => {
          const sp = sportVon(s)
          jeSport[sp] = (jeSport[sp] || 0) + (s.duration_min || 0)
        })
        const jeWoche = wochenSummen(aktiveImMonat)
        const [jahr, monat] = ym.split('-').map(Number)
        const wochenDesMonats = []
        if (jahr && monat) {
          const letzter = new Date(jahr, monat, 0)
          for (let d = parseTag(montagVon(`${ym}-01`)); d <= letzter; d.setDate(d.getDate() + 7)) {
            wochenDesMonats.push(isoTag(d))
          }
        }
        const wochenMax = Math.max(1, ...wochenDesMonats.map(m => jeWoche[m]?.min || 0))
        const dieseWoche = montagVon(isoTag(new Date()))

        return (
          <div key={ym} className="bg-[#111318] border border-[#1e2228] rounded-xl overflow-hidden">
            <button
              onClick={() => toggleMonth(ym)}
              className="w-full flex items-center justify-between gap-4 px-4 py-3 hover:bg-[#0d0f17] transition-colors text-left"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-baseline gap-3 flex-wrap">
                  <span className="text-base font-bold text-[#e8eaf0] tracking-wide" style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>
                    {formatMonth(ym).toUpperCase()}
                  </span>
                  <span className="text-2xl font-black leading-none tabular-nums text-[#e8eaf0]" style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>
                    {stunden(summeMin)}
                  </span>
                  <span className="text-[10px] font-mono tracking-widest text-[var(--text-muted)]">
                    {aktiveImMonat.length} SESSIONS{totalTSS > 0 ? ` · ${Math.round(totalTSS)} TSS` : ''}
                  </span>
                </div>
                {summeMin > 0 && (
                  <div className="flex gap-[2px] h-1.5 mt-2 max-w-md rounded-full overflow-hidden">
                    {SPORTEN.filter(sp => jeSport[sp]).map(sp => (
                      <div key={sp} title={`${DISCIPLINE_LABEL[sp] || sp}: ${stunden(jeSport[sp])}`}
                           style={{ flexGrow: jeSport[sp], flexBasis: 0, background: DISCIPLINE_COLOR[sp] || DISCIPLINE_COLOR.other, opacity: 0.85 }} />
                    ))}
                  </div>
                )}
              </div>
              {wochenDesMonats.length > 0 && summeMin > 0 && (
                <div className="hidden sm:flex items-end gap-1 h-7 flex-shrink-0" aria-hidden="true">
                  {wochenDesMonats.map(m => (
                    <div key={m} className="w-2.5 h-full flex flex-col justify-end"
                         title={`Week of ${parseTag(m).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}: ${stunden(jeWoche[m]?.min)}`}>
                      <div className="w-full rounded-t-[2px]"
                           style={{
                             height: `${Math.max(6, ((jeWoche[m]?.min || 0) / wochenMax) * 100)}%`,
                             background: m === dieseWoche ? ACCENT : jeWoche[m]?.min ? '#5b6475' : '#1e2228',
                           }} />
                    </div>
                  ))}
                </div>
              )}
              <span className="text-[var(--text-secondary)] text-sm font-mono flex-shrink-0">{isOpen ? '▼' : '▶'}</span>
            </button>

            {isOpen && (
              <div className="border-t border-[#1e2228] divide-y divide-[#1e2228]/40 bg-[#0d0f17]">
                {sorted.map(s => (
                  <SessionRow
                    key={s.id}
                    session={s}
                    onClick={() => setSelectedSession(s)}
                    onDelete={() => handleSoftDelete(s.id)}
                    onHardDelete={() => handleHardDelete(s.id)}
                    onRestore={() => handleRestore(s.id)}
                    onCommute={() => handleCommute(s.id, !s.is_commute)}
                  />
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ─── Plans Tab ─────────────────────────────────────────────────────────────────
//
// Jede Woche als Sieben-Tage-Streifen in Sportfarben statt Text-Chips
// („Mo: bike"). Zwei Einträge am selben Tag teilen die Zelle — so sieht man
// den Doppeltag. Der Phasenstreifen links trägt die Farbe der Planphase.

const WOCHENTAGE = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']
const TAG_KURZ = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']
const SPORT_KURZ = { swim: 'SWIM', bike: 'BIKE', run: 'RUN', brick: 'BRICK', gym: 'GYM', hike: 'HIKE', rest: 'REST' }

function phasenName(phase) {
  if (!phase) return ''
  return phaseFamilie(phase) === 'off' ? 'OFF SEASON' : blockName(phase)
}

function PlanWoche({ plan: p }) {
  const [lang, setLang] = useState(false)
  const farbe = phaseColor(p.plan_phase)
  const tage = WOCHENTAGE.map((name, i) => ({
    kurz: TAG_KURZ[i],
    einheiten: (p.plan_content?.days || []).filter(d => d.day === name && (d.session_type || 'rest') !== 'rest'),
  }))
  const von = parseTag(p.week_start)
  const bis = parseTag(p.week_end)
  const zeitraumText = `${von.getDate()}${von.getMonth() !== bis.getMonth() ? ` ${von.toLocaleDateString('en-GB', { month: 'short' }).toUpperCase()}` : ''}–${bis.getDate()} ${bis.toLocaleDateString('en-GB', { month: 'short' }).toUpperCase()}`
  const kommentar = p.plan_content?.coaching_comment

  return (
    <div className="bg-[#111318] border border-[#1e2228] rounded-xl p-4 pl-5 relative overflow-hidden">
      <span className="absolute left-0 inset-y-0 w-[3px]" style={{ background: farbe }} />
      <div className="flex items-baseline justify-between gap-3 flex-wrap mb-3">
        <span className="text-[10px] font-mono tracking-widest text-[var(--text-secondary)]">
          {/* Negative Wochen liegen vor dem Aufbau — „Week -3" wäre dort
              eine Zahl ohne Bedeutung. */}
          <span className="text-[#e8eaf0]">{p.week_number < 1 ? 'PREP' : `WEEK ${p.week_number}`}</span>
          {p.plan_phase && <> · <span style={{ color: farbe }}>{phasenName(p.plan_phase)}</span></>}
        </span>
        <span className="text-[10px] font-mono tracking-widest text-[var(--text-muted)]">{zeitraumText}</span>
      </div>

      <div className="grid grid-cols-7 gap-1">
        {tage.map(t => (
          <div key={t.kurz} className="min-w-0">
            <div className="text-[8px] font-mono tracking-widest text-[var(--text-muted)] mb-1 text-center">{t.kurz}</div>
            <div className="h-11 flex flex-col gap-[2px]">
              {t.einheiten.length === 0 ? (
                <div className="flex-1 rounded-[3px] flex items-center justify-center text-[8px] font-mono text-[var(--text-muted)]"
                     style={{ background: '#0d0f14', border: '1px solid #1a1d24' }}>
                  —
                </div>
              ) : t.einheiten.map((e, i) => {
                const sport = (e.session_type || '').toLowerCase()
                const sf = DISCIPLINE_COLOR[sport] || DISCIPLINE_COLOR.other
                return (
                  <div key={i}
                       className="flex-1 rounded-[3px] flex flex-col items-center justify-center min-h-0 overflow-hidden"
                       style={{ background: `${sf}22`, boxShadow: `inset 0 0 0 1px ${sf}55` }}
                       title={`${DISCIPLINE_LABEL[sport] || sport}${e.duration_min ? ` · ${e.duration_min} min` : ''}`}>
                    <span className="text-[8px] sm:text-[9px] font-mono font-bold leading-none truncate max-w-full px-0.5" style={{ color: sf }}>
                      {SPORT_KURZ[sport] || sport.toUpperCase()}
                    </span>
                    {t.einheiten.length === 1 && e.duration_min > 0 && (
                      <span className="text-[8px] font-mono tabular-nums text-[var(--text-muted)] leading-none mt-1">{e.duration_min}′</span>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        ))}
      </div>

      {kommentar && (
        <div className="mt-3">
          <p className={`text-[var(--text-secondary)] text-xs leading-relaxed ${lang ? '' : 'line-clamp-2'}`}>{kommentar}</p>
          {kommentar.length > 160 && (
            <button onClick={() => setLang(v => !v)}
                    className="mt-1 text-[9px] font-mono tracking-widest text-[var(--text-muted)] hover:text-[#00d4ff]">
              {lang ? 'LESS' : 'MORE'}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

function PlansTab({ plans }) {
  if (!plans.length) return <p className="text-[var(--text-secondary)] text-sm py-4">Noch keine Wochenpläne erstellt.</p>
  return (
    <div className="space-y-3">
      {plans.map(p => <PlanWoche key={p.id} plan={p} />)}
    </div>
  )
}

// ─── Main ──────────────────────────────────────────────────────────────────────

const TABS = [
  { key: 'sessions',  label: 'Einheiten' },
  { key: 'progress',  label: 'Fortschritt' },
  { key: 'plans',     label: 'Wochenpläne' },
]

export default function History() {
  const [sessions, setSessions] = useState([])
  const [plans, setPlans] = useState([])
  const [tab, setTab] = useState('sessions')
  const [showDeleted, setShowDeleted] = useState(false)
  const [loading, setLoading] = useState(true)
  const [fehler, setFehler] = useState(null)
  // Seitenweise statt fest 50: Vorher endete der Verlauf still bei der 50.
  // Einheit, ohne Hinweis und ohne Weg weiter zurück.
  const SEITE = 100
  const [mehrDa, setMehrDa] = useState(false)
  // Fürs Fortschrittsdiagramm alle Einheiten der letzten zwei Jahre, ohne
  // Zeitreihen — die Monatsbalken brauchen nur Datum, Dauer und TSS.
  const [verlauf, setVerlauf] = useState([])
  // Für die Deload-Dreiecke im Wochenvolumen; still, sie sind Beiwerk.
  const [saison, setSaison] = useState(null)
  useEffect(() => { getSaison().then(({ data }) => setSaison(data)).catch(() => {}) }, [])

  const load = async () => {
    setLoading(true)
    setFehler(null)
    try {
      const [s, p] = await Promise.all([
        getSessions({ include_deleted: showDeleted, limit: SEITE }),
        getHistoryPlans(),
      ])
      setSessions(s.data)
      setMehrDa(s.data.length === SEITE)
      setPlans(p.data)
      const vor = new Date(); vor.setFullYear(vor.getFullYear() - 2)
      getSessionsSeit(isoTag(vor)).then(({ data }) => setVerlauf(data)).catch(() => setVerlauf([]))
    } catch (e) {
      setFehler(fehlerText(e, 'Verlauf konnte nicht geladen werden.'))
    } finally {
      setLoading(false)
    }
  }

  const mehrLaden = async () => {
    try {
      const { data } = await getSessions({ include_deleted: showDeleted, limit: SEITE, offset: sessions.length })
      setSessions(prev => [...prev, ...data])
      setMehrDa(data.length === SEITE)
    } catch (e) {
      setFehler(fehlerText(e, 'Weitere Einheiten konnten nicht geladen werden.'))
    }
  }

  useEffect(() => { load() }, [showDeleted])

  return (
    <div className="space-y-5 page-enter">
      <h1 className="text-3xl font-bold tracking-tight text-[#e8eaf0]" style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>
        VERLAUF
      </h1>
      {fehler && (
        <div className="rounded-lg px-3 py-2 font-mono text-xs"
             style={{ background: '#ef444415', border: '1px solid #ef444430', color: '#ef4444' }}>
          {fehler}
        </div>
      )}

      <div className="flex gap-1.5 border-b border-[#1e2228]">
        {TABS.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-mono transition-all border-b-2 -mb-px ${tab === t.key ? 'border-[#00d4ff] text-[#00d4ff]' : 'border-transparent text-[var(--text-secondary)] hover:text-[#e8eaf0]'}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="text-[var(--text-secondary)] font-mono text-sm py-6 text-center tracking-widest">LOADING...</div>
      ) : (
        <>
          {tab === 'sessions' && (
            <>
              <SessionsTab sessions={sessions} showDeleted={showDeleted} onToggleDeleted={() => setShowDeleted(v => !v)} onRefresh={load} />
              {mehrDa && (
                <div className="flex justify-center pt-2">
                  <button onClick={mehrLaden}
                          className="px-4 py-2 rounded-lg text-[11px] font-mono tracking-wide"
                          style={{ background: '#00d4ff15', border: '1px solid #00d4ff33', color: '#00d4ff' }}>
                    ÄLTERE EINHEITEN LADEN
                  </button>
                </div>
              )}
            </>
          )}
          {tab === 'progress' && (
            <ProgressTab sessions={verlauf.length ? verlauf : sessions} volle={sessions} plaene={plans} saison={saison} />
          )}
          {tab === 'plans' && <PlansTab plans={plans} />}
        </>
      )}
    </div>
  )
}
