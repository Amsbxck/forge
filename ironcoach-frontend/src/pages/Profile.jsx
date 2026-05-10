import { useEffect, useState } from 'react'
import { getProfile, updateProfile, getStravaStatus, getStravaAuthUrl } from '../services/api'

const CARD = 'bg-[#111318] border border-[#1e2228] rounded-xl'
const LABEL = 'text-xs font-mono tracking-widest text-[#8a909e]'

const HR_ZONES = [
  { key: 'z1', label: 'Z1', color: '#2d6a4f', range: (p) => `≤ ${p.z1_hr_max} bpm` },
  { key: 'z2', label: 'Z2', color: '#40916c', range: (p) => `${p.z2_hr_min}–${p.z2_hr_max} bpm` },
  { key: 'z3', label: 'Z3', color: '#f4a261', range: (p) => `${p.z3_hr_min}–${p.z3_hr_max} bpm` },
  { key: 'z4', label: 'Z4', color: '#e76f51', range: (p) => `${p.z4_hr_min}–${p.z4_hr_max} bpm` },
  { key: 'z5', label: 'Z5', color: '#e63946', range: (p) => `> ${p.z4_hr_max} bpm` },
]

function daysUntil(dateStr) {
  if (!dateStr) return null
  const d = new Date(dateStr)
  const now = new Date()
  now.setHours(0, 0, 0, 0)
  return Math.max(0, Math.round((d - now) / 86400000))
}

export default function Profile() {
  const [profile, setProfile] = useState(null)
  const [strava, setStrava] = useState(null)
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({})
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    const load = async () => {
      try {
        const [p, s] = await Promise.all([getProfile(), getStravaStatus()])
        setProfile(p.data)
        setForm({ ftp_watts: p.data.ftp_watts, max_hr: p.data.max_hr, name: p.data.name, race_goal: p.data.race_goal })
        setStrava(s.data)
      } catch (e) { console.error(e) }
    }
    load()
  }, [])

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
    <div className="flex items-center justify-center py-20 text-[#8a909e]">
      <div className="text-sm font-mono tracking-widest">LOADING...</div>
    </div>
  )

  const daysLeft = daysUntil(profile.race_date)

  return (
    <div className="space-y-5 page-enter">

      {/* Header */}
      <div className="flex items-baseline gap-3">
        <h1 className="text-3xl font-black tracking-tight text-[#e8eaf0]" style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>
          ATHLETE
        </h1>
        {profile.name && <span className="text-lg font-mono text-[#3a3f4a]">{profile.name}</span>}
      </div>

      {/* ── Hero FTP card (dominant) + secondary stats ── */}
      <div className="grid grid-cols-3 gap-4 items-start">

        {/* FTP — oversize, col-span-2, visual anchor */}
        <div
          className="col-span-2 rounded-xl p-7 relative overflow-hidden"
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

          <div className={`${LABEL} mb-3`}>FUNCTIONAL THRESHOLD POWER</div>
          <div
            className="font-black leading-none text-[#e8eaf0]"
            style={{ fontFamily: 'Barlow Condensed, sans-serif', fontSize: 'clamp(5rem, 12vw, 8rem)', lineHeight: 1 }}
          >
            {profile.ftp_watts}
            <span className="text-3xl font-normal text-[#3a3f4a] ml-3">W</span>
          </div>

          {profile.current_week && (
            <div className="mt-4 text-xs font-mono text-[#3a3f4a] tracking-widest">
              WEEK {profile.current_week} / 33
            </div>
          )}
        </div>

        {/* Secondary column: Max HR + Race countdown stacked */}
        <div className="flex flex-col gap-4">
          <div className={`${CARD} p-5`}>
            <div className={`${LABEL} mb-2`}>MAX HEART RATE</div>
            <div className="text-4xl font-black leading-none text-[#e8eaf0]" style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>
              {profile.max_hr}
              <span className="text-base font-normal text-[#8a909e] ml-1">bpm</span>
            </div>
          </div>

          <div className={`${CARD} p-5`}>
            <div className={`${LABEL} mb-2`}>RACE COUNTDOWN</div>
            {daysLeft !== null ? (
              <>
                <div
                  className="text-4xl font-black leading-none"
                  style={{
                    fontFamily: 'Barlow Condensed, sans-serif',
                    color: daysLeft < 30 ? '#e63946' : daysLeft < 90 ? '#f4a261' : '#00d4ff',
                  }}
                >
                  {daysLeft}
                  <span className="text-base font-normal text-[#8a909e] ml-1">days</span>
                </div>
                <div className="text-xs font-mono text-[#3a3f4a] mt-1">{profile.race_date}</div>
              </>
            ) : (
              <div className="text-xl font-mono text-[#3a3f4a]">—</div>
            )}
          </div>
        </div>
      </div>

      {/* Performance data card */}
      <div className={CARD}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#1e2228]">
          <span className="text-sm font-bold tracking-widest text-[#8a909e]" style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>
            PERFORMANCE DATA
          </span>
          {!editing && (
            <button
              onClick={() => setEditing(true)}
              className="text-xs font-mono text-[#00d4ff] transition-colors px-3 py-1 rounded-lg"
              style={{ border: '1px solid #00d4ff33', background: '#00d4ff10' }}
            >
              EDIT
            </button>
          )}
        </div>

        <div className="p-5">
          {editing ? (
            <div className="space-y-3">
              {[
                { key: 'name', label: 'NAME', type: 'text' },
                { key: 'ftp_watts', label: 'FTP (WATT)', type: 'number' },
                { key: 'max_hr', label: 'MAX HR (bpm)', type: 'number' },
                { key: 'race_goal', label: 'RACE GOAL', type: 'text' },
              ].map(({ key, label, type }) => (
                <div key={key} className="flex items-center gap-4">
                  <label className="text-xs font-mono text-[#8a909e] tracking-widest w-36 flex-shrink-0">{label}</label>
                  <input
                    type={type}
                    value={form[key] || ''}
                    onChange={e => setForm(f => ({ ...f, [key]: type === 'number' ? Number(e.target.value) : e.target.value }))}
                    className="flex-1 rounded-lg px-3 py-1.5 text-sm font-mono text-[#e8eaf0] outline-none transition-colors"
                    style={{ background: '#0d0f17', border: '1px solid #1e2228' }}
                    onFocus={e => { e.target.style.borderColor = '#00d4ff44' }}
                    onBlur={e => { e.target.style.borderColor = '#1e2228' }}
                  />
                </div>
              ))}
              <div className="flex gap-2 pt-3">
                <button
                  onClick={save} disabled={saving}
                  className="px-4 py-1.5 rounded-lg text-sm font-mono font-bold transition-all disabled:opacity-40"
                  style={{ background: '#00d4ff20', border: '1px solid #00d4ff44', color: '#00d4ff' }}
                >
                  {saving ? 'SAVING...' : 'SAVE'}
                </button>
                <button
                  onClick={() => setEditing(false)}
                  className="px-4 py-1.5 rounded-lg text-sm font-mono text-[#8a909e] hover:text-[#e8eaf0] transition-colors"
                  style={{ border: '1px solid #1e2228' }}
                >
                  CANCEL
                </button>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3">
              {[
                ['GOAL', profile.race_goal],
                ['NAME', profile.name],
                ['RACE DATE', profile.race_date],
                ['CURRENT WEEK', profile.current_week ? `${profile.current_week} / 33` : '—'],
              ].map(([label, val]) => (
                <div key={label} className="rounded-lg px-3 py-2.5" style={{ background: '#0d0f17', border: '1px solid #1e2228' }}>
                  <div className="text-xs font-mono text-[#3a3f4a] tracking-widest mb-1">{label}</div>
                  <div className="text-sm text-[#e8eaf0]">{val || '—'}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* HR Zones */}
      <div className={CARD}>
        <div className="px-5 py-4 border-b border-[#1e2228]">
          <span className="text-sm font-bold tracking-widest text-[#8a909e]" style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>
            HEART RATE ZONES
          </span>
        </div>
        <div className="p-5 space-y-2">
          {HR_ZONES.map(({ key, label, color, range }, idx) => (
            <div key={key} className="flex items-center gap-4">
              <div
                className="w-8 text-center text-xs font-mono font-bold rounded flex-shrink-0"
                style={{ color, background: `${color}20`, padding: '2px 0', border: `1px solid ${color}40` }}
              >
                {label}
              </div>
              <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: '#1e2228' }}>
                <div
                  className="h-full rounded-full"
                  style={{ width: `${20 * (idx + 1)}%`, background: color, opacity: 0.7 }}
                />
              </div>
              <div className="text-xs font-mono text-[#8a909e] w-36 text-right flex-shrink-0">{range(profile)}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Strava */}
      <div className={CARD}>
        <div className="px-5 py-4 border-b border-[#1e2228]">
          <span className="text-sm font-bold tracking-widest text-[#8a909e]" style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>
            STRAVA
          </span>
        </div>
        <div className="p-5">
          {strava?.connected ? (
            <div className="flex items-center gap-3">
              <div className="w-2.5 h-2.5 rounded-full" style={{ background: '#22c55e', boxShadow: '0 0 8px #22c55e88' }} />
              <span className="text-sm font-mono text-[#e8eaf0]">Connected</span>
              <span className="text-xs font-mono text-[#3a3f4a]">· Athlete ID: {strava.athlete_id}</span>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-sm font-mono text-[#8a909e]">Connect Strava for automatic activity import via webhook.</p>
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
