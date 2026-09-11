import { useState } from 'react'
import {
  clearSwimTest, clearThresholds, setSwimTest, setThresholds, updateProfile,
} from '../services/api'
import SportIcon from './SportIcon'
import { DISCIPLINE_COLOR } from '../utils/colors'

const CARD = 'bg-[#111318] border border-[#1e2228] rounded-xl'
const LABEL = 'text-[10px] font-mono tracking-widest text-[var(--text-secondary)] block mb-1'
const FIELD = 'rounded-lg px-3 py-2 text-sm font-mono text-[#e8eaf0] placeholder-[var(--text-muted)] outline-none w-full'
const FIELD_STYLE = { background: '#0d0f17', border: '1px solid #1e2228' }
const DISPLAY = { fontFamily: 'Barlow Condensed, sans-serif' }

/** "5:13" oder "313" → Sekunden. */
function zuSekunden(text) {
  const t = (text || '').trim()
  if (!t) return null
  if (t.includes(':')) {
    const [m, s] = t.split(':')
    const min = Number(m), sek = Number(s)
    return Number.isNaN(min) || Number.isNaN(sek) ? null : min * 60 + sek
  }
  const n = Number(t)
  return Number.isNaN(n) ? null : n
}

function alsZeit(sekunden) {
  if (!sekunden) return null
  const m = Math.floor(sekunden / 60)
  const s = Math.round(sekunden % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

function fehlerText(err, fallback) {
  const d = err?.response?.data?.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d)) return d[0]?.msg || fallback
  return fallback
}

/** Eine Sportart mit ihren Schwellenwerten.
 *
 *  Alle drei gleich groß und gleich gebaut: Vorher stand die FTP riesig da
 *  und Pace, Puls und CSS klein in einer Nebenzeile — dabei sind es dieselbe
 *  Art von Wert, nur für eine andere Disziplin.
 */
function SportKarte({ disziplin, titel, werte, quelle, hinweis, warnung, kinder, onReset, busy, relevant = true }) {
  const [offen, setOffen] = useState(false)
  const farbe = DISCIPLINE_COLOR[disziplin]
  const gesetzt = werte.some(w => w.wert)

  // Für das Saisonziel belanglos: Die Karte bleibt stehen, damit die Reihe
  // vollständig ist — aber ohne Eingabeaufforderung. Ein Läufer soll nicht
  // zum Eintragen einer FTP aufgefordert werden, die in keine Vorgabe eingeht.
  if (!relevant) {
    return (
      <div className={`${CARD} p-5 flex flex-col`} style={{ opacity: .45 }}>
        <div className="flex items-center gap-2 mb-3">
          <SportIcon discipline={disziplin} size={16} color="var(--text-muted)" />
          <span className="text-sm font-bold tracking-widest"
                style={{ ...DISPLAY, color: 'var(--text-muted)' }}>
            {titel}
          </span>
        </div>
        <div className="font-black leading-none text-[var(--text-muted)]"
             style={{ ...DISPLAY, fontSize: 'clamp(2rem, 4vw, 2.6rem)' }}>—</div>
        <div className="mt-auto pt-3 text-[10px] font-mono text-[var(--text-muted)]">
          für dein Saisonziel nicht nötig
        </div>
      </div>
    )
  }

  return (
    <div className={`${CARD} p-5 flex flex-col`}>
      <div className="flex items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          <SportIcon discipline={disziplin} size={16} color={farbe} />
          <span className="text-sm font-bold tracking-widest"
                style={{ ...DISPLAY, color: farbe }}>
            {titel}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {gesetzt && onReset && (
            <button onClick={onReset} disabled={busy}
                    className="text-[10px] font-mono text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
                    title="Werte verwerfen — danach greift die Ableitung wieder">
              ZURÜCKSETZEN
            </button>
          )}
          <button onClick={() => setOffen(o => !o)}
                  className="text-[10px] font-mono" style={{ color: farbe }}>
            {offen ? 'SCHLIESSEN' : gesetzt ? 'ÄNDERN' : 'EINTRAGEN'}
          </button>
        </div>
      </div>

      <div className="flex gap-7 flex-wrap">
        {werte.map(w => (
          <div key={w.label}>
            <div className="text-[11px] font-mono font-bold tracking-widest text-[var(--text-secondary)]">{w.label}</div>
            <div className="font-black leading-none mt-1"
                 style={{ ...DISPLAY, color: w.wert ? farbe : 'var(--text-muted)', fontSize: 'clamp(2.8rem, 6.5vw, 4.2rem)' }}>
              {w.wert || '—'}
              {w.wert && w.einheit && (
                <span className="text-lg font-normal text-[var(--text-secondary)] ml-1">{w.einheit}</span>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="text-[10px] font-mono text-[var(--text-muted)] mt-2">
        {gesetzt ? (quelle === 'manual' ? 'von dir eingetragen' : quelle === 'auto' ? 'aus den Testeinheiten abgeleitet' : hinweis) : hinweis}
      </div>

      {warnung && (
        <div className="mt-3 rounded-lg px-3 py-2 text-[11px] leading-relaxed"
             style={{ background: '#f59e0b12', border: '1px solid #f59e0b33', color: '#f59e0b' }}>
          {warnung}
        </div>
      )}

      {offen && <div className="mt-4 pt-4 border-t border-[#1e2228]">{kinder}</div>}
    </div>
  )
}

/** Welche Werte für welche Sportart zählen — dieselbe Einteilung wie im
 *  Backend (`core/race_types.SPORT_WERTE`). */
const WERTE_JE_SPORT = {
  triathlon: ['ftp', 'run_threshold', 'css'],
  running: ['run_threshold'],
  cycling: ['ftp'],
}

export default function Thresholds({ profile, onChanged, sport }) {
  const [busy, setBusy] = useState(false)
  const [fehler, setFehler] = useState(null)
  const [rad, setRad] = useState({ ftp: '' })
  const [lauf, setLauf] = useState({ hr: '', pace: '' })
  const [schwimm, setSchwimm] = useState({ t400: '', t200: '', hr: '' })

  if (!profile) return null

  // Ohne Saisonziel gilt Triathlon: Dann ist noch offen, worauf trainiert
  // wird, und alles auszublenden wäre die schlechtere Annahme.
  const zaehlt = WERTE_JE_SPORT[sport] || WERTE_JE_SPORT.triathlon

  const tun = async (fn) => {
    setBusy(true); setFehler(null)
    try { await fn(); onChanged?.() }
    catch (err) { setFehler(fehlerText(err, 'Speichern fehlgeschlagen')) }
    finally { setBusy(false) }
  }

  return (
    <div className="space-y-3">
      <div className="grid gap-4 lg:grid-cols-3">
        {/* ── Rad ── */}
        <SportKarte
          disziplin="bike" titel="RAD · FTP" busy={busy}
          relevant={zaehlt.includes('ftp')}
          werte={[{ label: 'FTP', wert: profile.ftp_watts, einheit: 'W' }]}
          quelle={profile.zones_source === 'manual' ? 'manual' : profile.zones_source === 'benchmark' ? 'auto' : null}
          hinweis="Bezugsgröße aller Wattvorgaben"
          kinder={
            <div className="space-y-3">
              <label className="block">
                <span className={LABEL}>FTP (WATT)</span>
                <input className={FIELD} style={FIELD_STYLE} type="number" placeholder={String(profile.ftp_watts)}
                       value={rad.ftp} onChange={e => setRad({ ftp: e.target.value })} />
              </label>
              <p className="text-[10px] font-mono text-[var(--text-muted)] leading-relaxed">
                Aus dem 20-Minuten-Test × 0,95 — oder direkt aus dem Ergebnis eines
                Zwift-Ramp-Tests, der die FTP selbst ausgibt.
              </p>
              <button onClick={() => tun(() => updateProfile({ ftp_watts: Number(rad.ftp) }))}
                      disabled={busy || !rad.ftp}
                      className="px-4 py-2 rounded-lg text-[11px] font-mono font-bold tracking-wide disabled:opacity-30"
                      style={{ background: '#a855f720', border: '1px solid #a855f744', color: '#a855f7' }}>
                ÜBERNEHMEN
              </button>
            </div>
          }
        />

        {/* ── Laufen ── */}
        <SportKarte
          disziplin="run" titel="LAUFEN · SCHWELLE" busy={busy}
          relevant={zaehlt.includes('run_threshold')}
          werte={[
            { label: 'PULS', wert: profile.threshold_hr, einheit: 'bpm' },
            { label: 'PACE', wert: alsZeit(profile.threshold_pace_s_per_km), einheit: '/km' },
          ]}
          quelle={profile.threshold_source}
          hinweis="Bezugsgröße der pulsbasierten Belastung"
          warnung={!profile.threshold_hr
            ? 'Ohne Schwellenpuls wird gegen die Obergrenze von Zone 2 gerechnet. Die liegt tiefer als die echte Schwelle, wodurch jede Einheit belastender aussieht, als sie war.'
            : null}
          onReset={() => tun(clearThresholds)}
          kinder={
            <div className="space-y-3">
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="block">
                  <span className={LABEL}>SCHWELLENPULS (BPM)</span>
                  <input className={FIELD} style={FIELD_STYLE} type="number" placeholder="188"
                         value={lauf.hr} onChange={e => setLauf(f => ({ ...f, hr: e.target.value }))} />
                </label>
                <label className="block">
                  <span className={LABEL}>SCHWELLENPACE (MM:SS)</span>
                  <input className={FIELD} style={FIELD_STYLE} placeholder="5:13"
                         value={lauf.pace} onChange={e => setLauf(f => ({ ...f, pace: e.target.value }))} />
                </label>
              </div>
              <button onClick={() => tun(() => setThresholds({
                        threshold_hr: lauf.hr ? Number(lauf.hr) : null,
                        threshold_pace: lauf.pace || null,
                      }))}
                      disabled={busy || (!lauf.hr && !lauf.pace)}
                      className="px-4 py-2 rounded-lg text-[11px] font-mono font-bold tracking-wide disabled:opacity-30"
                      style={{ background: '#ec489920', border: '1px solid #ec489944', color: '#ec4899' }}>
                ÜBERNEHMEN
              </button>
            </div>
          }
        />

        {/* ── Schwimmen ── */}
        <SportKarte
          disziplin="swim" titel="SCHWIMMEN · CSS" busy={busy}
          relevant={zaehlt.includes('css')}
          werte={[
            { label: 'PULS', wert: profile.swim_threshold_hr, einheit: 'bpm' },
            { label: 'CSS', wert: alsZeit(profile.css_pace_s_per_100m), einheit: '/100m' },
          ]}
          quelle={profile.css_source}
          hinweis="Aus 400 m und 200 m je maximal"
          warnung={profile.css_source === 'auto'
            ? 'Aus den Runden abgeleitet. Welche Bahn der Test war, kann die App nur raten — prüfe die Zeiten und korrigiere sie, wenn sie nicht stimmen.'
            : null}
          onReset={() => tun(clearSwimTest)}
          kinder={
            <div className="space-y-3">
              <div className="grid gap-3 sm:grid-cols-3">
                <label className="block">
                  <span className={LABEL}>400 M</span>
                  <input className={FIELD} style={FIELD_STYLE} placeholder="6:40"
                         value={schwimm.t400} onChange={e => setSchwimm(f => ({ ...f, t400: e.target.value }))} />
                </label>
                <label className="block">
                  <span className={LABEL}>200 M</span>
                  <input className={FIELD} style={FIELD_STYLE} placeholder="3:10"
                         value={schwimm.t200} onChange={e => setSchwimm(f => ({ ...f, t200: e.target.value }))} />
                </label>
                <label className="block">
                  <span className={LABEL}>PULS (OPT.)</span>
                  <input className={FIELD} style={FIELD_STYLE} type="number" placeholder="160"
                         value={schwimm.hr} onChange={e => setSchwimm(f => ({ ...f, hr: e.target.value }))} />
                </label>
              </div>
              <p className="text-[10px] font-mono text-[var(--text-muted)] leading-relaxed">
                CSS = (400 m − 200 m) ÷ 2. Der Puls im Wasser liegt rund zehn Schläge
                unter dem an Land — deshalb ein eigener Wert.
              </p>
              <button onClick={() => tun(() => setSwimTest({
                        t400_s: zuSekunden(schwimm.t400),
                        t200_s: zuSekunden(schwimm.t200),
                        swim_threshold_hr: schwimm.hr ? Number(schwimm.hr) : null,
                      }))}
                      disabled={busy || !schwimm.t400 || !schwimm.t200}
                      className="px-4 py-2 rounded-lg text-[11px] font-mono font-bold tracking-wide disabled:opacity-30"
                      style={{ background: '#38bdf820', border: '1px solid #38bdf844', color: '#38bdf8' }}>
                ÜBERNEHMEN
              </button>
            </div>
          }
        />
      </div>

      {fehler && <div className="text-[11px] font-mono text-[#ef4444]">{fehler}</div>}
    </div>
  )
}
