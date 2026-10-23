import { useState } from 'react'
import {
  clearSwimTest, clearThresholds, setSwimTest, setThresholds, updateProfile,
} from '../services/api'
import SportIcon from './SportIcon'
import { DISCIPLINE_COLOR } from '../utils/colors'
import FtpHinweis from './FtpHinweis'
import { toenung } from './leisten/Kachel'

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
          <span className="text-xs font-mono tracking-[0.25em] text-[var(--text-muted)]">{titel}</span>
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
    // Getönt in der Sportfarbe, die Zahlen weiß — wie die Kacheln im
    // Dashboard. Vorher standen die Zahlen selbst in der Sportfarbe.
    <div className={`${CARD} p-5 flex flex-col`} style={toenung(farbe, 0.8)}>
      <div className="flex items-center justify-between gap-2 mb-4">
        <div className="flex items-center gap-2" style={{ color: farbe }}>
          <SportIcon discipline={disziplin} size={14} color={farbe} />
          <span className="text-xs font-mono tracking-[0.25em]">{titel}</span>
        </div>
        <div className="flex items-center gap-2">
          {gesetzt && onReset && (
            <button onClick={onReset} disabled={busy}
                    className="text-[10px] font-mono text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
                    title="Werte verwerfen — danach greift die Ableitung wieder">
              RESET
            </button>
          )}
          <button onClick={() => setOffen(o => !o)}
                  className="text-[10px] font-mono tracking-widest" style={{ color: farbe }}>
            {offen ? 'CLOSE' : gesetzt ? 'EDIT' : 'ENTER'}
          </button>
        </div>
      </div>

      <div className="flex gap-7 flex-wrap">
        {werte.map(w => (
          <div key={w.label}>
            <div className="text-[9px] font-mono tracking-[0.2em] text-[var(--text-muted)]">{w.label}</div>
            <div className="font-black leading-none mt-1.5"
                 style={{ ...DISPLAY, color: w.wert ? '#f2f4f8' : 'var(--text-muted)', fontSize: 'clamp(2.8rem, 6.5vw, 4.2rem)', textShadow: w.wert ? '0 0 28px #ffffff14' : 'none' }}>
              {w.wert || '—'}
              {w.wert && w.einheit && (
                <span className="text-xs font-mono font-normal text-[var(--text-muted)] ml-1">{w.einheit}</span>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="text-[9px] font-mono tracking-widest text-[var(--text-muted)] mt-2.5 uppercase">
        {gesetzt ? (quelle === 'manual' ? 'set by you' : quelle === 'auto' ? 'derived from test sessions' : hinweis) : hinweis}
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

export default function Thresholds({ profile, ftpBefund, onChanged, sport }) {
  const [busy, setBusy] = useState(false)
  const [fehler, setFehler] = useState(null)
  const [rad, setRad] = useState({ ftp: '' })
  const [lauf, setLauf] = useState({ hr: '', pace: '' })
  // Streckenpaare des CSS-Tests. 400/200 bleibt die Vorgabe — je länger die
  // Strecken, desto kleiner der Anteil der anaeroben Startreserve am
  // Ergebnis. Die kürzeren Paare sind für alle, die 400 m nicht am Stück
  // maximal schwimmen können: Dort entsteht sonst keine Messung, sondern
  // eine Einbruchskurve.
  const CSS_PAARE = [
    { lang: 400, kurz: 200, label: '400 / 200', platzhalter: ['6:40', '3:10'] },
    { lang: 200, kurz: 100, label: '200 / 100', platzhalter: ['3:10', '1:28'] },
    { lang: 100, kurz: 50,  label: '100 / 50',  platzhalter: ['1:28', '0:40'] },
  ]
  // Gültigkeitsbereich des Modells, gespiegelt aus services/swim_css.py.
  // Bewertet werden die Zeiten, nicht die Strecken — für einen langsamen
  // Schwimmer sind 100/50 m einwandfrei, für einen schnellen nicht.
  const MIN_LANG_S = 120
  const MIN_KURZ_S = 60
  const [schwimm, setSchwimm] = useState({ t400: '', t200: '', hr: '', paar: 0 })
  const paar = CSS_PAARE[schwimm.paar]

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
          disziplin="bike" titel="CYCLING · FTP" busy={busy}
          relevant={zaehlt.includes('ftp')}
          werte={[{ label: 'FTP', wert: profile.ftp_watts, einheit: 'W' }]}
          /* Eigenes Herkunftsfeld statt `zones_source`: Das gilt für das
             ganze Profil, und eine von Hand eingetragene FTP stünde dort als
             gemessen, sobald irgendetwas anderes gemessen wurde. */
          quelle={profile.ftp_source === 'benchmark' ? 'auto' : profile.ftp_source === 'manual' ? 'manual' : null}
          hinweis="Basis of all power targets"
          kinder={
            <div className="space-y-3">
              <label className="block">
                <span className={LABEL}>FTP (WATT)</span>
                <input className={FIELD} style={FIELD_STYLE} type="number" placeholder={String(profile.ftp_watts)}
                       value={rad.ftp} onChange={e => setRad({ ftp: e.target.value })} />
              </label>
              <p className="text-[10px] font-mono text-[var(--text-muted)] leading-relaxed">
                Aus dem 20-Minuten-Test × 0,95 — oder direkt aus dem Ergebnis eines
                Stufentests, der die FTP selbst ausgibt.
              </p>
              <FtpHinweis befund={ftpBefund} kompakt />
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
          disziplin="run" titel="RUNNING · THRESHOLD" busy={busy}
          relevant={zaehlt.includes('run_threshold')}
          werte={[
            { label: 'HR', wert: profile.threshold_hr, einheit: 'bpm' },
            { label: 'PACE', wert: alsZeit(profile.threshold_pace_s_per_km), einheit: '/km' },
          ]}
          quelle={profile.threshold_source}
          hinweis="Basis of heart-rate load"
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
          disziplin="swim" titel="SWIMMING · CSS" busy={busy}
          relevant={zaehlt.includes('css')}
          werte={[
            { label: 'HR', wert: profile.swim_threshold_hr, einheit: 'bpm' },
            { label: 'CSS', wert: alsZeit(profile.css_pace_s_per_100m), einheit: '/100m' },
          ]}
          quelle={profile.css_source}
          hinweis={profile.css_dist_lang_m
            ? `From ${profile.css_dist_lang_m} m and ${profile.css_dist_kurz_m} m, each all-out`
            : 'From two distances, each all-out'}
          warnung={profile.css_source === 'auto'
            ? 'Aus den Runden abgeleitet. Welche Bahn der Test war, kann die App nur raten — prüfe die Zeiten und korrigiere sie, wenn sie nicht stimmen.'
            : null}
          onReset={() => tun(clearSwimTest)}
          kinder={
            <div className="space-y-3">
              <div>
                <span className={`${LABEL} block mb-1`}>STRECKEN</span>
                <div className="grid gap-1 grid-cols-3">
                  {CSS_PAARE.map((p, i) => (
                    <button
                      key={p.label} type="button"
                      onClick={() => setSchwimm(f => ({ ...f, paar: i, t400: '', t200: '' }))}
                      className="px-2 py-1.5 rounded-lg text-[11px] font-mono transition-all"
                      style={{
                        background: schwimm.paar === i ? '#38bdf814' : '#0d0f17',
                        border: `1px solid ${schwimm.paar === i ? '#38bdf844' : '#1e2228'}`,
                        color: schwimm.paar === i ? '#38bdf8' : 'var(--text-secondary)',
                      }}
                    >
                      {p.label} m
                    </button>
                  ))}
                </div>
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                <label className="block">
                  <span className={LABEL}>{paar.lang} M</span>
                  <input className={FIELD} style={FIELD_STYLE} placeholder={paar.platzhalter[0]}
                         value={schwimm.t400} onChange={e => setSchwimm(f => ({ ...f, t400: e.target.value }))} />
                </label>
                <label className="block">
                  <span className={LABEL}>{paar.kurz} M</span>
                  <input className={FIELD} style={FIELD_STYLE} placeholder={paar.platzhalter[1]}
                         value={schwimm.t200} onChange={e => setSchwimm(f => ({ ...f, t200: e.target.value }))} />
                </label>
                <label className="block">
                  <span className={LABEL}>PULS (OPT.)</span>
                  <input className={FIELD} style={FIELD_STYLE} type="number" placeholder="160"
                         value={schwimm.hr} onChange={e => setSchwimm(f => ({ ...f, hr: e.target.value }))} />
                </label>
              </div>
              <p className="text-[10px] font-mono text-[var(--text-muted)] leading-relaxed">
                CSS = ({paar.lang} m − {paar.kurz} m) ÷ {(paar.lang - paar.kurz) / 100}.
                Der Puls im Wasser liegt rund zehn Schläge unter dem an Land —
                deshalb ein eigener Wert.
              </p>
              {(() => {
                const tl = zuSekunden(schwimm.t400)
                const tk = zuSekunden(schwimm.t200)
                if (!tl || !tk || (tl >= MIN_LANG_S && tk >= MIN_KURZ_S)) return null
                return (
                  <p className="text-[10px] font-mono leading-relaxed" style={{ color: '#f59e0b' }}>
                    Diese Zeiten sind kurz. Die Rechnung setzt Belastungen ab etwa
                    zwei Minuten voraus — darunter schlägt die Startreserve durch und
                    der Wert fällt zu schnell aus. Nimm die nächstlängeren Strecken.
                  </p>
                )
              })()}
              <button onClick={() => tun(() => setSwimTest({
                        t400_s: zuSekunden(schwimm.t400),
                        t200_s: zuSekunden(schwimm.t200),
                        d_lang_m: paar.lang,
                        d_kurz_m: paar.kurz,
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
