import { useCallback, useEffect, useState } from 'react'
import { getProfile, updateProfile, getStravaStatus, getStravaAuthUrl, getActiveGoal, getFtpCheck } from '../services/api'
import PasswordChange from '../components/PasswordChange'
import AccountSection from '../components/AccountSection'
import Thresholds from '../components/Thresholds'
import { daysUntil, parseTag } from '../utils/dates'
import { HR_ZONE_COLOR } from '../utils/colors'
import HrvRange from '../components/HrvRange'
import ZoneEditor from '../components/ZoneEditor'
import ApiBudget from '../components/ApiBudget'
import { Link } from 'react-router-dom'
import { KOPF, Stand, TITEL, knopfStil, toenung } from '../components/leisten/Kachel'

const CARD = 'bg-[#111318] border border-[#1e2228] rounded-xl'

// Dieselben Farben wie die Zonenbalken im Dashboard. Vorher hatte das Profil
// eine eigene Skala, obwohl dieselben Zonen gemeint sind.
const HR_ZONES = [
  { key: 'z1', label: 'Z1', color: HR_ZONE_COLOR[0], range: (p) => `≤ ${p.z1_hr_max} bpm` },
  { key: 'z2', label: 'Z2', color: HR_ZONE_COLOR[1], range: (p) => `${p.z2_hr_min}–${p.z2_hr_max} bpm` },
  { key: 'z3', label: 'Z3', color: HR_ZONE_COLOR[2], range: (p) => `${p.z3_hr_min}–${p.z3_hr_max} bpm` },
  { key: 'z4', label: 'Z4', color: HR_ZONE_COLOR[3], range: (p) => `${p.z4_hr_min}–${p.z4_hr_max} bpm` },
  { key: 'z5', label: 'Z5', color: HR_ZONE_COLOR[4], range: (p) => `> ${p.z4_hr_max} bpm` },
]

export default function Profile() {
  const [profile, setProfile] = useState(null)
  const [strava, setStrava] = useState(null)
  const [editing, setEditing] = useState(false)
  const [pulsEdit, setPulsEdit] = useState(false)
  const [form, setForm] = useState({})
  const [saving, setSaving] = useState(false)
  // Sportart des Saisonziels — entscheidet, welche Schwellenwerte überhaupt
  // gebraucht werden. Ohne Ziel bleibt sie leer und es wird nichts ausgeblendet.
  const [zielSport, setZielSport] = useState(null)
  const [ftpBefund, setFtpBefund] = useState(null)

  const load = useCallback(async () => {
    try {
      const [p, s, z] = await Promise.all([
        getProfile(),
        getStravaStatus(),
        getActiveGoal().catch(() => ({ data: null })),
      ])
      setProfile(p.data)
      setZielSport(z.data?.sport || null)
      setForm({ ftp_watts: p.data.ftp_watts, max_hr: p.data.max_hr, name: p.data.name })
      setStrava(s.data)
      // Nach den übrigen Daten und mit eigenem Fehlerfang: Die Prüfung liest
      // Leistungsdaten mehrerer Fahrten und darf die Seite nicht aufhalten.
      getFtpCheck().then(({ data }) => setFtpBefund(data?.befund || null)).catch(() => setFtpBefund(null))
    } catch (e) { console.error(e) }
  }, [])

  useEffect(() => { load() }, [load])

  const save = async () => {
    setSaving(true)
    try {
      const resp = await updateProfile(form)
      setProfile(resp.data)
      setEditing(false)
    } catch (e) { console.error(e) }
    finally { setSaving(false) }
  }

  const connectStrava = async () => {
    const resp = await getStravaAuthUrl()
    window.location.href = resp.data.auth_url
  }

  if (!profile) return (
    <div className="flex items-center justify-center py-20 text-[var(--text-secondary)]">
      <div className="text-[10px] font-mono tracking-[0.25em] text-[var(--text-muted)]">LOADING…</div>
    </div>
  )

  const daysLeft = daysUntil(profile.race_date)

  return (
    <div className="space-y-5 page-enter">

      {/* Header — der Saisonstand gehört hierher, nicht in eine eigene
          Kachel zwischen die Messwerte. */}
      <div className="flex items-end justify-between gap-4 flex-wrap">
      <div className="flex items-baseline gap-3 flex-wrap">
        <h1 className="text-3xl font-black tracking-tight text-[#e8eaf0]" style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>
          ATHLETE
        </h1>
        <span className="text-3xl font-black text-[var(--text-muted)]" style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>·</span>

        {/* Der Name wird dort geändert, wo er steht. Eine eigene Karte nur
            für dieses eine Feld war ein Umweg. */}
        {editing ? (
          <form
            onSubmit={e => { e.preventDefault(); save() }}
            className="flex items-center gap-2"
          >
            <input
              autoFocus
              value={form.name || ''}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              onKeyDown={e => { if (e.key === 'Escape') setEditing(false) }}
              className="text-3xl font-black tracking-tight text-[#e8eaf0] bg-transparent outline-none border-b"
              style={{ fontFamily: 'Barlow Condensed, sans-serif', borderColor: '#ffffff40', width: '10ch' }}
            />
            <button type="submit" disabled={saving}
                    className="text-[10px] font-mono px-2 py-1 rounded disabled:opacity-40"
                    style={{ background: '#00d4ff20', border: '1px solid #00d4ff44', color: '#00d4ff' }}>
              {saving ? '…' : 'OK'}
            </button>
            <button type="button" onClick={() => setEditing(false)}
                    className="text-[10px] font-mono tracking-widest text-[var(--text-muted)] hover:text-[var(--text-secondary)]">
              CANCEL
            </button>
          </form>
        ) : (
          <button
            onClick={() => setEditing(true)}
            className="group flex items-baseline gap-2"
            title="Namen ändern"
          >
            <h1 className="text-3xl font-black tracking-tight text-[#e8eaf0] group-hover:text-white transition-colors"
                style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>
              {(profile.name || 'SET NAME').toUpperCase()}
            </h1>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
                 className="opacity-0 group-hover:opacity-100 transition-opacity self-center"
                 stroke="#a7aebd" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 20h9" />
              <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" />
            </svg>
          </button>
        )}
        </div>

        {/* Saisonstand rechts in der Kopfzeile — er gehört nicht zwischen
            die Messwerte, und als eigene Kachel ließ er eine Lücke. */}
        {/* Wie die Zahlen im Dashboard: Unterzeile, große weiße Zahl,
            Einheit klein. Vorher Cyan, das bei weniger als 90 Tagen nach
            Bernstein und Rot wechselte — als wäre die Nähe zum Rennen eine
            Warnung. */}
        <div className="text-right">
          <div className={KOPF}>
            {daysLeft === null ? 'NEXT RACE' : daysLeft > 0 ? 'DAYS TO RACE' : daysLeft === 0 ? 'RACE DAY' : 'SINCE LAST RACE'}
          </div>
          <div className="flex items-baseline justify-end gap-1 mt-1.5">
            <span className="text-3xl font-black leading-none tabular-nums"
                  style={{ fontFamily: 'Barlow Condensed, sans-serif', color: daysLeft === null ? 'var(--text-muted)' : '#f2f4f8' }}>
              {daysLeft === null ? '—' : daysLeft === 0 ? 'TODAY' : Math.abs(daysLeft)}
            </span>
            {daysLeft !== null && daysLeft !== 0 && (
              <span className="text-xs font-mono text-[var(--text-muted)]">{Math.abs(daysLeft) === 1 ? 'day' : 'days'}</span>
            )}
          </div>
          <div className="text-[9px] font-mono tracking-widest text-[var(--text-muted)] mt-1.5">
            {daysLeft === null ? 'NO GOAL SET' : `${profile.race_date}${daysLeft < 0 ? ' · OFF SEASON' : ''}`}
          </div>
        </div>
      </div>

      {/* ── Schwellenwerte zuerst: das ist, wofür man das Profil öffnet ── */}
      <Thresholds profile={profile} ftpBefund={ftpBefund} onChanged={load} sport={zielSport} />

      <ZoneEditor profile={profile} onSaved={load} />

      {/* ── Maximalpuls und HRV-Spanne nebeneinander ──
           Beide sind Bezugsgrößen für die Bewertung, keine Vorgaben. Die
           Maximalpuls-Kachel stand vorher allein über die volle Breite und
           ließ zwei Drittel der Fläche leer. */}
      {/* Ohne items-start: Rasterzellen dehnen sich standardmäßig auf gleiche
          Höhe. Mit items-start endete jede Kachel dort, wo ihr Inhalt aufhört —
          und die beiden Unterkanten standen sichtbar versetzt. */}
      <div className="grid lg:grid-cols-2 gap-4">
          {/* Wie die übrigen Kacheln: Kopf, große Zahl, Unterzeile. Vorher
              mit Lichtkegel und laufendem Schimmer am unteren Rand — den
              gab es sonst nirgends. */}
          <div className={`${CARD} p-5 relative overflow-hidden`}>
            <div className="flex items-center justify-between gap-2 mb-4">
              <div className={TITEL}>MAX HEART RATE</div>
              <button onClick={() => setPulsEdit(v => !v)}
                      className="text-[10px] font-mono tracking-widest text-[var(--text-muted)] hover:text-[#e8eaf0] transition-colors">
                {pulsEdit ? 'CLOSE' : 'EDIT'}
              </button>
            </div>
            {pulsEdit ? (
              <form onSubmit={e => { e.preventDefault(); save(); setPulsEdit(false) }}
                    className="flex items-center gap-2">
                <input
                  autoFocus type="number" value={form.max_hr || ''}
                  onChange={e => setForm(f => ({ ...f, max_hr: Number(e.target.value) }))}
                  className="font-black leading-none text-[#e8eaf0] bg-transparent outline-none border-b w-32"
                  style={{ fontFamily: 'Barlow Condensed, sans-serif', fontSize: 'clamp(2.8rem, 6vw, 4rem)', borderColor: '#ffffff40' }}
                />
                <button type="submit" disabled={saving}
                        className="px-3 py-1.5 rounded-lg text-[10px] font-mono font-semibold tracking-widest disabled:opacity-40"
                        style={knopfStil('haupt')}>
                  {saving ? '…' : 'OK'}
                </button>
              </form>
            ) : (
              <div className="flex items-baseline gap-1">
                <span className="font-black leading-none tabular-nums text-[#f2f4f8]"
                      style={{ fontFamily: 'Barlow Condensed, sans-serif', fontSize: 'clamp(2.8rem, 6vw, 4rem)', textShadow: '0 0 28px #ffffff14' }}>
                  {profile.max_hr}
                </span>
                <span className="text-xs font-mono text-[var(--text-muted)]">bpm</span>
              </div>
            )}
            <div className="mt-3 text-xs text-[var(--text-secondary)] leading-relaxed">
              Grundlage aller Zonengrenzen. Der höchste tatsächlich gemessene Wert —
              aus dem Alter geschätzt wäre er für die meisten Menschen falsch.
            </div>

            {profile.current_week != null && (
              <div className="mt-4 text-[9px] font-mono text-[var(--text-muted)] tracking-[0.2em]">
                {daysLeft !== null && daysLeft < 0
                  ? 'OFF SEASON'
                  /* Vor dem Aufbaustart zählt keine Vorbereitungswoche. */
                  : profile.plan_start_date && parseTag(profile.plan_start_date) > new Date()
                  ? 'BASE PERIOD'
                  : `WEEK ${profile.current_week}${profile.total_weeks ? ` / ${profile.total_weeks}` : ''}`}
              </div>
            )}
          </div>

        <HrvRange />
      </div>

      <ApiBudget />

      {/* Strava kurz, verwaltet wird auf „Anbindungen". Vorher stand hier
          ein zweiter, englischer Verbinden-Knopf in eigenem Aussehen. */}
      <div className={`${CARD} p-5 flex items-center justify-between gap-4 flex-wrap`}
           style={toenung(strava?.connected ? '#fc4c02' : null, 0.6)}>
        <div className="space-y-2">
          <div className={TITEL}>STRAVA</div>
          {strava?.connected
            ? <Stand>CONNECTED · ATHLETE {strava.athlete_id}</Stand>
            : <Stand farbe="#5b6475">NOT CONNECTED</Stand>}
        </div>
        {strava?.connected ? (
          <Link to="/connect" className="text-[10px] font-mono tracking-widest text-[var(--text-muted)] hover:text-[#e8eaf0]">
            MANAGE ▸
          </Link>
        ) : (
          <button onClick={connectStrava}
                  className="px-3 py-1.5 rounded-lg text-[10px] font-mono font-semibold tracking-widest hover:brightness-125"
                  style={knopfStil('haupt', '#fc4c02')}>
            CONNECT STRAVA
          </button>
        )}
      </div>

      <PasswordChange />

      {/* Nach dem Löschen oder Überall-Abmelden ist die Sitzung weg — ein
          harter Neuaufbau ist hier ehrlicher als ein Zustand, in dem die
          Oberfläche noch Daten eines Kontos zeigt, das es nicht mehr gibt. */}
      <AccountSection onLoggedOut={() => window.location.replace('/')} />

    </div>
  )
}
