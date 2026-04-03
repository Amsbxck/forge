import { useEffect, useState } from 'react'
import { getProfile, updateProfile, getStravaStatus, getStravaAuthUrl } from '../services/api'

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
      } catch (e) {
        console.error(e)
      }
    }
    load()
  }, [])

  const save = async () => {
    setSaving(true)
    try {
      const resp = await updateProfile(form)
      setProfile(resp.data)
      setEditing(false)
    } catch (e) {
      console.error(e)
    } finally {
      setSaving(false)
    }
  }

  const connectStrava = async () => {
    const resp = await getStravaAuthUrl()
    window.location.href = resp.data.auth_url
  }

  if (!profile) return <div className="text-gray-400">Lade Profil...</div>

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Athletenprofil</h1>

      <div className="bg-[#111318] border border-[#1e2228] rounded-xl p-6 space-y-4">
        <div className="flex justify-between items-center">
          <h2 className="font-semibold">Leistungsdaten</h2>
          {!editing && (
            <button onClick={() => setEditing(true)} className="text-sm text-brand-500 hover:text-brand-400">Bearbeiten</button>
          )}
        </div>

        {editing ? (
          <div className="space-y-3">
            {[
              { key: 'name', label: 'Name', type: 'text' },
              { key: 'ftp_watts', label: 'FTP (Watt)', type: 'number' },
              { key: 'max_hr', label: 'Max HR (bpm)', type: 'number' },
              { key: 'race_goal', label: 'Rennziel', type: 'text' },
            ].map(({ key, label, type }) => (
              <div key={key} className="flex items-center gap-4">
                <label className="text-gray-400 text-sm w-32">{label}</label>
                <input
                  type={type}
                  value={form[key] || ''}
                  onChange={e => setForm(f => ({ ...f, [key]: type === 'number' ? Number(e.target.value) : e.target.value }))}
                  className="bg-gray-800 rounded-lg px-3 py-1.5 text-sm border border-gray-700 flex-1"
                />
              </div>
            ))}
            <div className="flex gap-2 pt-2">
              <button onClick={save} disabled={saving} className="bg-brand-600 hover:bg-brand-700 text-white px-4 py-1.5 rounded-lg text-sm">
                {saving ? 'Speichern...' : 'Speichern'}
              </button>
              <button onClick={() => setEditing(false)} className="text-gray-400 hover:text-gray-100 px-4 py-1.5 text-sm">Abbrechen</button>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3 text-sm">
            {[
              ['Name', profile.name],
              ['FTP', `${profile.ftp_watts}W`],
              ['Max HR', `${profile.max_hr} bpm`],
              ['Renntag', profile.race_date],
              ['Ziel', profile.race_goal],
              ['Aktuelle Woche', profile.current_week ? `${profile.current_week}/33` : '–'],
              ['HR Z1', `≤ ${profile.z1_hr_max} bpm`],
              ['HR Z2', `${profile.z2_hr_min}–${profile.z2_hr_max} bpm`],
              ['HR Z3', `${profile.z3_hr_min}–${profile.z3_hr_max} bpm`],
              ['HR Z4', `${profile.z4_hr_min}–${profile.z4_hr_max} bpm`],
            ].map(([label, val]) => (
              <div key={label}>
                <span className="text-gray-500">{label}: </span>
                <span className="text-gray-100">{val}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Strava */}
      <div className="bg-[#111318] border border-[#1e2228] rounded-xl p-6">
        <h2 className="font-semibold mb-3">Strava</h2>
        {strava?.connected ? (
          <div className="flex items-center gap-2 text-green-400">
            <div className="w-2 h-2 rounded-full bg-green-400" />
            <span className="text-sm">Verbunden (Athlete ID: {strava.athlete_id})</span>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-gray-400 text-sm">Verbinde Strava für automatischen Aktivitätsimport via Webhook.</p>
            <button onClick={connectStrava} className="bg-orange-600 hover:bg-orange-700 text-white px-4 py-2 rounded-lg text-sm font-medium">
              Mit Strava verbinden
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
