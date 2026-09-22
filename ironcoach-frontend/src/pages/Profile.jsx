import { useCallback, useEffect, useState } from 'react'
import { getProfile, updateProfile, getStravaStatus, getStravaAuthUrl, getActiveGoal, getFtpCheck } from '../services/api'
import PasswordChange from '../components/PasswordChange'
import AccountSection from '../components/AccountSection'
import Thresholds from '../components/Thresholds'
import { daysUntil } from '../utils/dates'
import { HR_ZONE_COLOR } from '../utils/colors'
import HrvRange from '../components/HrvRange'
import ZoneEditor from '../components/ZoneEditor'
import ApiBudget from '../components/ApiBudget'

const CARD = 'bg-[#111318] border border-[#1e2228] rounded-xl'
const LABEL = 'text-xs font-mono tracking-widest text-[var(--text-secondary)]'

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
      setForm({ ftp_watts: p.data.ftp_watts, max_hr: p.data.max_hr, name: p.data.name, race_goal: p.data.race_goal })
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
      <div className="text-sm font-mono tracking-widest">LOADING...</div>
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
              style={{ fontFamily: 'Barlow Condensed, sans-serif', borderColor: '#00d4ff66', width: '10ch' }}
            />
            <button type="submit" disabled={saving}
                    className="text-[10px] font-mono px-2 py-1 rounded disabled:opacity-40"
                    style={{ background: '#00d4ff20', border: '1px solid #00d4ff44', color: '#00d4ff' }}>
              {saving ? '…' : 'OK'}
            </button>
            <button type="button" onClick={() => setEditing(false)}
                    className="text-[10px] font-mono text-[var(--text-muted)] hover:text-[var(--text-secondary)]">
              ABBRECHEN
            </button>
          </form>
        ) : (
          <button
            onClick={() => setEditing(true)}
            className="group flex items-baseline gap-2"
            title="Namen ändern"
          >
            <h1 className="text-3xl font-black tracking-tight text-[#e8eaf0] group-hover:text-[#00d4ff] transition-colors"
                style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>
              {(profile.name || 'NAME SETZEN').toUpperCase()}
            </h1>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
                 className="opacity-0 group-hover:opacity-100 transition-opacity self-center"
                 stroke="#00d4ff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 20h9" />
              <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" />
            </svg>
          </button>
        )}
        </div>

        {/* Saisonstand rechts in der Kopfzeile — er gehört nicht zwischen
            die Messwerte, und als eigene Kachel ließ er eine Lücke. */}
        <div className="text-right">
          {daysLeft === null ? (
            <>
              <div className="text-[10px] font-mono tracking-widest text-[var(--text-secondary)]">NÄCHSTES RENNEN</div>
              <div className="text-lg font-mono text-[var(--text-muted)]">kein Ziel gesetzt</div>
            </>
          ) : daysLeft > 0 ? (
            <>
              <div className="text-[10px] font-mono tracking-widest text-[var(--text-secondary)]">BIS ZUM RENNEN</div>
              <div className="text-2xl font-black leading-none mt-0.5"
                   style={{ fontFamily: 'Barlow Condensed, sans-serif',
                            color: daysLeft < 30 ? '#ef4444' : daysLeft < 90 ? '#f59e0b' : '#00d4ff' }}>
                {daysLeft}<span className="text-sm font-normal text-[var(--text-secondary)] ml-1">
                  {daysLeft === 1 ? 'Tag' : 'Tage'}</span>
              </div>
              <div className="text-[10px] font-mono text-[var(--text-muted)]">{profile.race_date}</div>
            </>
          ) : daysLeft === 0 ? (
            <>
              <div className="text-[10px] font-mono tracking-widest text-[var(--text-secondary)]">RENNTAG</div>
              <div className="text-2xl font-black leading-none mt-0.5"
                   style={{ fontFamily: 'Barlow Condensed, sans-serif', color: '#00d4ff' }}>HEUTE</div>
              <div className="text-[10px] font-mono text-[var(--text-muted)]">{profile.race_date}</div>
            </>
          ) : (
            <>
              <div className="text-[10px] font-mono tracking-widest text-[var(--text-secondary)]">SEIT DEM LETZTEN RENNEN</div>
              <div className="text-2xl font-black leading-none mt-0.5"
                   style={{ fontFamily: 'Barlow Condensed, sans-serif', color: 'var(--text-secondary)' }}>
                {Math.abs(daysLeft)}<span className="text-sm font-normal text-[var(--text-secondary)] ml-1">
                  {Math.abs(daysLeft) === 1 ? 'Tag' : 'Tage'}</span>
              </div>
              <div className="text-[10px] font-mono text-[var(--text-muted)]">{profile.race_date} · Off Season</div>
            </>
          )}
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
          <div
            className="rounded-xl p-7 relative overflow-hidden"
            style={{ background: '#111318', border: '1px solid #1e2228' }}
          >
            {/* Diagonal light beam */}
            <div
              className="absolute pointer-events-none"
              style={{
                top: '-40px', right: '-40px',
                width: '200px', height: '200px',
                background: 'conic-gradient(from 200deg, transparent 0deg, #00d4ff08 30deg, transparent 60deg)',
                animation: 'ftpShimmer 4s ease-in-out infinite',
              }}
            />
            {/* Shimmer line at bottom */}
            <div
              className="absolute bottom-0 left-0 right-0 h-px"
              style={{ background: 'linear-gradient(90deg, transparent 0%, #00d4ff55 40%, #00d4ff88 50%, #00d4ff55 60%, transparent 100%)', animation: 'shimmerSweep 3s ease-in-out infinite' }}
            />

            <div className="flex items-center justify-between gap-2 mb-3">
              <div className={LABEL}>MAXIMALPULS</div>
              <button onClick={() => setPulsEdit(v => !v)}
                      className="text-[10px] font-mono text-[var(--text-muted)] hover:text-[#00d4ff] transition-colors">
                {pulsEdit ? 'SCHLIESSEN' : 'ÄNDERN'}
              </button>
            </div>
            {pulsEdit ? (
              <form onSubmit={e => { e.preventDefault(); save(); setPulsEdit(false) }}
                    className="flex items-center gap-2">
                <input
                  autoFocus type="number" value={form.max_hr || ''}
                  onChange={e => setForm(f => ({ ...f, max_hr: Number(e.target.value) }))}
                  className="font-black leading-none text-[#e8eaf0] bg-transparent outline-none border-b w-32"
                  style={{ fontFamily: 'Barlow Condensed, sans-serif', fontSize: 'clamp(2.8rem, 6vw, 4rem)', borderColor: '#00d4ff66' }}
                />
                <button type="submit" disabled={saving}
                        className="text-[10px] font-mono px-2 py-1 rounded disabled:opacity-40"
                        style={{ background: '#00d4ff20', border: '1px solid #00d4ff44', color: '#00d4ff' }}>
                  {saving ? '…' : 'OK'}
                </button>
              </form>
            ) : (
              <div
                className="font-black leading-none text-[#e8eaf0]"
                style={{ fontFamily: 'Barlow Condensed, sans-serif', fontSize: 'clamp(2.8rem, 6vw, 4rem)', lineHeight: 1 }}
              >
                {profile.max_hr}
                <span className="text-xl font-normal text-[var(--text-muted)] ml-2">bpm</span>
              </div>
            )}
            <div className="mt-3 text-[10px] font-mono text-[var(--text-muted)] leading-relaxed">
              Grundlage aller Zonengrenzen. Der höchste tatsächlich gemessene Wert —
              aus dem Alter geschätzt wäre er für die meisten Menschen falsch.
            </div>

            {profile.current_week != null && (
              <div className="mt-4 text-xs font-mono text-[var(--text-muted)] tracking-widest">
                {daysLeft !== null && daysLeft < 0
                  ? 'OFF SEASON'
                  /* Vor dem Aufbaustart zählt keine Vorbereitungswoche. */
                  : profile.plan_start_date && new Date(profile.plan_start_date) > new Date()
                  ? 'GRUNDLAGE'
                  : `WEEK ${profile.current_week}${profile.total_weeks ? ` / ${profile.total_weeks}` : ''}`}
              </div>
            )}
          </div>

        <HrvRange />
      </div>

      <ApiBudget />

      {/* Strava */}
      <div className={CARD}>
        <div className="px-5 py-4 border-b border-[#1e2228]">
          <span className="text-sm font-bold tracking-widest text-[var(--text-secondary)]" style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>
            STRAVA
          </span>
        </div>
        <div className="p-5">
          {strava?.connected ? (
            <div className="flex items-center gap-3">
              <div className="w-2.5 h-2.5 rounded-full" style={{ background: '#22c55e', boxShadow: '0 0 8px #22c55e88' }} />
              <span className="text-sm font-mono text-[#e8eaf0]">Connected</span>
              <span className="text-xs font-mono text-[var(--text-muted)]">· Athlete ID: {strava.athlete_id}</span>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-sm font-mono text-[var(--text-secondary)]">Connect Strava for automatic activity import via webhook.</p>
              <button
                onClick={connectStrava}
                className="px-4 py-2 rounded-lg text-sm font-mono font-bold tracking-wide transition-all"
                style={{ background: '#fc4c0220', border: '1px solid #fc4c0244', color: '#fc4c02' }}
                onMouseEnter={e => { e.currentTarget.style.background = '#fc4c0230' }}
                onMouseLeave={e => { e.currentTarget.style.background = '#fc4c0220' }}
              >
                CONNECT STRAVA
              </button>
            </div>
          )}
        </div>
      </div>

      <PasswordChange />

      {/* Nach dem Löschen oder Überall-Abmelden ist die Sitzung weg — ein
          harter Neuaufbau ist hier ehrlicher als ein Zustand, in dem die
          Oberfläche noch Daten eines Kontos zeigt, das es nicht mehr gibt. */}
      <AccountSection onLoggedOut={() => window.location.replace('/')} />

      <style>{`
        @keyframes ftpShimmer {
          0%, 100% { opacity: 0.5; transform: rotate(0deg); }
          50%       { opacity: 1;   transform: rotate(15deg); }
        }
        @keyframes shimmerSweep {
          0%   { opacity: 0.3; transform: scaleX(0.5); }
          50%  { opacity: 1;   transform: scaleX(1); }
          100% { opacity: 0.3; transform: scaleX(0.5); }
        }
      `}</style>
    </div>
  )
}
