import { useEffect, useState } from 'react'
import { updateProfile } from '../services/api'
import { HR_ZONE_COLOR } from '../utils/colors'

/** Die sieben Grenzen in der Reihenfolge, in der sie aufsteigen müssen. */
const GRENZEN = [
  'z1_hr_max', 'z2_hr_min', 'z2_hr_max',
  'z3_hr_min', 'z3_hr_max', 'z4_hr_min', 'z4_hr_max',
]

/** Die fünf Bereiche, einmal benannt für alle drei Spalten.
 *
 *  Zone 1 ist derselbe Bereich, ob er in Schlägen, Sekunden oder Watt
 *  ausgedrückt wird. Drei getrennte Listen mit denselben Namen hätten
 *  irgendwann auseinandergelegen.
 */
const STUFEN = [
  { label: 'Z1', name: 'Regeneration' },
  { label: 'Z2', name: 'Grundlage' },
  { label: 'Z3', name: 'Tempo' },
  { label: 'Z4', name: 'Schwelle' },
  { label: 'Z5', name: 'VO2max' },
]

const PULS_FELDER = [
  { von: null, bis: 'z1_hr_max' },
  { von: 'z2_hr_min', bis: 'z2_hr_max' },
  { von: 'z3_hr_min', bis: 'z3_hr_max' },
  { von: 'z4_hr_min', bis: 'z4_hr_max' },
  { von: 'z4_hr_max', bis: null },
]

/** Anteile der Schwellenpace und der FTP — dieselbe Einteilung wie im
 *  Coach-Prompt (`services/zones.py`).
 *
 *  Bewusst hier gespiegelt und nicht vom Server geholt: Es ist eine
 *  Darstellung, kein zweiter Rechenweg. Ändert sich die Einteilung, muss sie
 *  an beiden Stellen geändert werden — dafür steht sie in der Server-Datei
 *  ausdrücklich als Konvention markiert.
 */
const LAUF = [
  { unten: 1.29, oben: null },
  { unten: 1.14, oben: 1.29 },
  { unten: 1.06, oben: 1.13 },
  { unten: 1.00, oben: 1.05 },
  { unten: 0.94, oben: 0.99 },
]

const RAD = [
  { unten: 0.00, oben: 0.55 },
  { unten: 0.56, oben: 0.75 },
  { unten: 0.76, oben: 0.90 },
  { unten: 0.91, oben: 1.05 },
  { unten: 1.06, oben: 1.20 },
]

const mmss = (s) => `${Math.floor(Math.round(s) / 60)}:${String(Math.round(s) % 60).padStart(2, '0')}`

/** Kopfzeile einer Spalte — Titel, Einheit, Bezugswert.
 *
 *  Eigene Komponente, damit alle drei Spalten dieselbe Höhe bekommen: Als der
 *  Kopf teils hier und teils in der Spalte selbst entstand, standen die Zeilen
 *  der mittleren Spalte um eine Kopfhöhe zu hoch.
 */
function Kopf({ titel, einheit, children }) {
  return (
    <>
      <div className="text-[10px] font-mono tracking-widest text-[var(--text-secondary)] mb-0.5">
        {titel} <span className="text-[var(--text-muted)]">· {einheit}</span>
      </div>
      <div className="text-[10px] font-mono text-[var(--text-muted)] mb-3 h-4 flex items-center gap-2">
        {children}
      </div>
    </>
  )
}

/** Die fünf Bereiche einer Spalte.
 *
 *  Aufbau je Zeile: farbiger Balken — Name — Wert. Der Balken ersetzt die
 *  frühere graue Strecke zwischen Name und Zahl: Die war nur Abstand und hat
 *  das Auge über eine leere Fläche geschickt. Jetzt zeigt sie, wo die Zone
 *  liegt, und die Zahl steht am Zeilenende statt am anderen Ende des Blocks.
 *
 *  Die Einheit steht einmal in der Kopfzeile, nicht fünfmal an den Werten.
 */
function Zeilen({ daten }) {
  return (
    <div className="space-y-1.5">
      {daten.map(({ label, name, wert }, i) => {
        const farbe = HR_ZONE_COLOR[i]
        return (
          <div key={label} className="flex items-center gap-2.5">
            <span className="w-6 text-[10px] font-mono font-bold flex-shrink-0"
                  style={{ color: farbe }}>
              {label}
            </span>
            <span className="h-2.5 rounded-sm flex-shrink-0"
                  style={{ width: `${18 + (i / 4) * 22}px`, background: farbe, opacity: 0.8 }} />
            <span className="text-xs text-[var(--text-secondary)] flex-shrink-0">{name}</span>
            <span className="ml-auto font-mono text-xs text-[#e8eaf0] tabular-nums whitespace-nowrap">
              {wert}
            </span>
          </div>
        )
      })}
    </div>
  )
}

export default function ZoneEditor({ profile, onSaved }) {
  const [bearbeiten, setBearbeiten] = useState(false)
  const [werte, setWerte] = useState({})
  const [fehler, setFehler] = useState(null)
  const [speichert, setSpeichert] = useState(false)

  useEffect(() => {
    if (!profile) return
    setWerte(Object.fromEntries(GRENZEN.map(k => [k, profile[k] ?? ''])))
  }, [profile])

  if (!profile) return null

  const pace = profile.threshold_pace_s_per_km
  const ftp = profile.ftp_watts
  const speichern = async () => {
    setFehler(null)
    const zahlen = Object.fromEntries(GRENZEN.map(k => [k, Number(werte[k])]))
    if (Object.values(zahlen).some(v => !Number.isFinite(v) || v <= 0)) {
      setFehler('Bitte alle Grenzen als Zahl eintragen.')
      return
    }
    // Dieselbe Prüfung wie am Server, nur früher: Der Server bleibt die
    // verbindliche Instanz — hier geht es darum, den Fehler dort zu zeigen,
    // wo er entsteht, statt nach dem Absenden.
    const folge = GRENZEN.map(k => zahlen[k])
    if (folge.some((v, i) => i > 0 && v <= folge[i - 1])) {
      setFehler('Die Grenzen müssen aufsteigen: Z1-Ende < Z2-Start < … < Z4-Ende.')
      return
    }
    if (zahlen.z4_hr_max > profile.max_hr) {
      setFehler(`Z4-Ende liegt über deinem Maximalpuls (${profile.max_hr} bpm).`)
      return
    }
    setSpeichert(true)
    try {
      await updateProfile(zahlen)
      setBearbeiten(false)
      onSaved?.()
    } catch (e) {
      setFehler(e?.response?.data?.detail || 'Speichern fehlgeschlagen.')
    } finally {
      setSpeichert(false)
    }
  }

  const abbrechen = () => {
    setWerte(Object.fromEntries(GRENZEN.map(k => [k, profile[k] ?? ''])))
    setFehler(null)
    setBearbeiten(false)
  }

  const pulsZeilen = STUFEN.map(({ label, name }, i) => {
    const { von, bis } = PULS_FELDER[i]
    const wert = von === null ? `≤ ${profile.z1_hr_max}`
      : bis === null ? `> ${profile[von]}`
      : `${profile[von]}–${profile[bis]}`
    return { label, name, wert, anteil: i / 4 }
  })

  const laufZeilen = pace ? STUFEN.map(({ label, name }, i) => {
    const { unten, oben } = LAUF[i]
    return {
      label, name, anteil: i / 4,
      wert: oben === null
        ? `> ${mmss(pace * unten)}`
        : `${mmss(pace * oben)}–${mmss(pace * unten)}`,
    }
  }) : null

  const radZeilen = ftp ? STUFEN.map(({ label, name }, i) => {
    const { unten, oben } = RAD[i]
    return {
      label, name, anteil: i / 4,
      wert: unten === 0
        ? `≤ ${Math.round(ftp * oben)}`
        : `${Math.round(ftp * unten)}–${Math.round(ftp * oben)}`,
    }
  }) : null

  return (
    <div className="rounded-xl border border-[#1e2228] bg-[#111318]">
      <div className="px-5 py-4 border-b border-[#1e2228] flex items-center justify-between gap-3">
        <span className="text-sm font-bold tracking-widest text-[var(--text-secondary)]"
              style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>
          TRAININGSBEREICHE
        </span>
        {!bearbeiten ? (
          <button onClick={() => setBearbeiten(true)}
                  className="text-[10px] font-mono tracking-widest text-[var(--text-secondary)] hover:text-[#00d4ff] transition-colors">
            PULSZONEN ANPASSEN
          </button>
        ) : (
          <div className="flex gap-3">
            <button onClick={abbrechen}
                    className="text-[10px] font-mono tracking-widest text-[var(--text-secondary)] hover:text-[#e8eaf0]">
              ABBRECHEN
            </button>
            <button onClick={speichern} disabled={speichert}
                    className="text-[10px] font-mono tracking-widest text-[#00d4ff] hover:text-[#7ee7ff] disabled:opacity-40">
              {speichert ? 'SPEICHERT…' : 'SPEICHERN'}
            </button>
          </div>
        )}
      </div>

      <div className="p-5 grid lg:grid-cols-3 gap-x-8 gap-y-7">
        {/* ── Puls ── */}
        <div>
          <Kopf titel="PULS" einheit="bpm">
            max {profile.max_hr}
            {profile.threshold_hr ? ` · Schwelle ${profile.threshold_hr}` : ''}
          </Kopf>

          {bearbeiten ? (
            <>
              <p className="text-xs text-[var(--text-secondary)] leading-relaxed mb-3">
                Wenn deine Uhr eigene Bereiche misst, trag sie hier ein — sie
                haben Vorrang vor der Berechnung aus dem Maximalpuls.
              </p>
              <div className="space-y-2">
                {STUFEN.map(({ label }, i) => {
                  const { von, bis } = PULS_FELDER[i]
                  const farbe = HR_ZONE_COLOR[i]
                  return (
                    <div key={label} className="flex items-center gap-2">
                      <span className="w-6 text-[10px] font-mono font-bold" style={{ color: farbe }}>
                        {label}
                      </span>
                      <input type="number" value={von ? (werte[von] ?? '') : ''}
                             onChange={von ? e => setWerte(w => ({ ...w, [von]: e.target.value })) : undefined}
                             disabled={!von || von === 'z4_hr_max'}
                             placeholder={von ? '' : '≤'}
                             className="w-16 rounded border px-1.5 py-1 text-right font-mono text-xs text-[#e8eaf0] outline-none focus:border-[#00d4ff55] disabled:opacity-40"
                             style={{ background: '#0d0f14', borderColor: '#1e2228' }} />
                      <span className="text-[var(--text-muted)]">–</span>
                      {bis ? (
                        <input type="number" value={werte[bis] ?? ''}
                               onChange={e => setWerte(w => ({ ...w, [bis]: e.target.value }))}
                               className="w-16 rounded border px-1.5 py-1 text-right font-mono text-xs text-[#e8eaf0] outline-none focus:border-[#00d4ff55]"
                               style={{ background: '#0d0f14', borderColor: '#1e2228' }} />
                      ) : (
                        <span className="w-16 text-right font-mono text-xs text-[var(--text-muted)]">max</span>
                      )}
                    </div>
                  )
                })}
              </div>
            </>
          ) : (
            <Zeilen daten={pulsZeilen} />
          )}

          {fehler && (
            <p className="text-xs mt-3 leading-relaxed" style={{ color: '#ef4444' }}>{fehler}</p>
          )}
        </div>

        {/* ── Laufpace ── */}
        <div>
          <Kopf titel="LAUFPACE" einheit="/km">
            {pace ? `Schwelle ${mmss(pace)}` : 'keine Schwellenpace'}
          </Kopf>
          {laufZeilen ? <Zeilen daten={laufZeilen} /> : (
            <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
              Noch keine Schwellenpace hinterlegt. Nach einem Schwellenlauf
              oder Benchmark-Test stehen hier die Bereiche.
            </p>
          )}
        </div>

        {/* ── Radleistung ── */}
        <div>
          <Kopf titel="RADLEISTUNG" einheit="Watt">
            {ftp ? `FTP ${ftp}` : 'keine FTP'}
          </Kopf>

          {radZeilen ? <Zeilen daten={radZeilen} /> : (
            <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
              Noch keine FTP hinterlegt.
            </p>
          )}
        </div>
      </div>

      {/* Der Hinweis gilt für alle drei Spalten und stand vorher unter der
          mittleren — dadurch las er sich wie eine Fußnote zur Pace allein,
          obwohl er das Verhältnis von Puls zu Pace **und** Watt beschreibt. */}
      <div className="px-5 pb-5">
        <p className="text-xs text-[var(--text-secondary)] leading-relaxed border-t border-[#1e2228] pt-4">
          <span className="text-[var(--text-primary)]">Pace und Watt sind die
          Vorgabe, der Puls ist die Kontrolle.</span>{' '}
          Was du steuerst, sind Tempo und Leistung; der Puls ist, was dein
          Körper daraus macht — er hinkt der Belastung nach und schwankt mit
          Hitze, Schlaf und Erholung. Für Intervalle unter etwa fünf Minuten
          taugt er als Steuergröße nicht, weil er erst ansteigt, wenn das
          Intervall vorbei ist. Nutze ihn für lange Grundlageneinheiten.
        </p>
      </div>
    </div>
  )
}
