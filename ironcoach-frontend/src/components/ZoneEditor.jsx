import { useEffect, useState } from 'react'
import { getProfileZones, updateProfile } from '../services/api'
import { ZONE_COLOR } from '../utils/colors'
import { fehlerText } from '../utils/fehler'

/** Die sieben Grenzen in der Reihenfolge, in der sie aufsteigen müssen. */
const GRENZEN = [
  'z1_hr_max', 'z2_hr_min', 'z2_hr_max',
  'z3_hr_min', 'z3_hr_max', 'z4_hr_min', 'z4_hr_max',
]

/** Die fünf Pulsbereiche — nur für die Pulsspalte.
 *
 *  Pace und Watt kommen nicht mehr von hier, sondern vom Server
 *  (`GET /api/profile/zones`). Sie standen vorher als Kopie in dieser Datei,
 *  „bewusst gespiegelt", und sind davon abgedriftet: Beim Rad stand die
 *  Z3/Z4-Grenze noch bei 90/91 %, die das Backend längst auf Coggans 94/95 %
 *  korrigiert hatte, und beim Laufen fehlten vVO2max und Steigerungen. Der
 *  Athlet sah andere Bereiche als die, nach denen geplant wurde.
 *
 *  Der Puls bleibt hier, weil er keine abgeleitete Größe ist: Die Grenzen
 *  stehen als Felder im Profil und werden in dieser Spalte bearbeitet.
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
 *  Aufbau je Zeile: Farbpunkt — Name — Wert. Vorher stand dort ein kleiner
 *  Balken, dessen Breite die Zonen**nummer** zeigte, nicht ihre Spanne — er
 *  sah aus wie eine Größe und war keine. Wie breit eine Zone wirklich ist,
 *  zeigt beim Puls jetzt die durchgehende Leiste darüber (`PulsLeiste`).
 *
 *  Die Einheit steht einmal in der Kopfzeile, nicht fünfmal an den Werten.
 */
function Zeilen({ daten }) {
  return (
    <div className="space-y-1.5">
      {daten.map(({ label, zone, name, wert }) => {
        // Nach Zonennummer, nicht nach Zeilenposition: Beim Laufen ist Z2 in
        // zwei Zeilen geteilt, und die Balkenbreite steht in allen drei Spalten
        // auf derselben Skala Z1–Z7 — dieselbe Zone, derselbe Balken.
        const farbe = ZONE_COLOR[zone] ?? ZONE_COLOR[1]
        return (
          <div key={`${label}-${name}`} className="flex items-center gap-2.5">
            <span className="w-6 text-[10px] font-mono font-bold flex-shrink-0"
                  style={{ color: farbe }}>
              {label}
            </span>
            <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: farbe }} />
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

/** Die Pulszonen als eine Leiste — jede Zone so breit wie ihre bpm-Spanne.
 *
 *  Die Tabelle sagte „Z2 139–173", aber nicht, dass Z2 mit 35 Schlägen fast
 *  so breit ist wie Z3 und Z4 zusammen. Das sieht man erst an Breiten. Die
 *  Schwelle steht als Marke darauf; sie liegt bei sauber gesetzten Zonen an
 *  der Z4-Grenze, und eine Abweichung fällt so sofort auf.
 *
 *  Unten beginnt die Leiste bei der Hälfte des Maximalpulses: Z1 hat keine
 *  untere Grenze, und eine Leiste ab 0 bestünde zur Hälfte aus Z1.
 */
function PulsLeiste({ profile }) {
  const max = profile.max_hr
  const grenzen = [profile.z1_hr_max, profile.z2_hr_max, profile.z3_hr_max, profile.z4_hr_max]
  if (!max || grenzen.some(g => !g) || grenzen.some((g, i) => i > 0 && g <= grenzen[i - 1]) || grenzen[3] >= max) {
    return null
  }
  const start = Math.min(Math.round(max * 0.5), grenzen[0] - 10)
  const pos = v => ((v - start) / (max - start)) * 100
  const kanten = [start, ...grenzen, max]
  const schwelle = profile.threshold_hr

  return (
    <div className="mb-4">
      {/* Die Marke liegt außerhalb des abgerundeten Rahmens, sonst schneidet
          `overflow-hidden` sie oben und unten ab. */}
      <div className="relative">
        <div className="h-4 rounded-full overflow-hidden flex gap-[2px]">
          {STUFEN.map(({ label }, i) => (
            <div
              key={label}
              className="h-full"
              title={`${label}: ${i === 0 ? `≤ ${kanten[1]}` : `${kanten[i] + 1}–${kanten[i + 1]}`} bpm`}
              style={{ width: `${pos(kanten[i + 1]) - pos(kanten[i])}%`, background: ZONE_COLOR[i + 1], opacity: 0.85 }}
            />
          ))}
        </div>
        {schwelle > start && schwelle < max && (
          <div
            className="absolute -translate-x-1/2 rounded-full pointer-events-none"
            style={{ left: `${pos(schwelle)}%`, top: -5, bottom: -5, width: 3, background: '#e8eaf0', boxShadow: '0 0 8px #e8eaf0aa' }}
            title={`Threshold ${schwelle} bpm`}
          />
        )}
      </div>
      <div className="relative h-4 mt-1.5">
        {grenzen.map(g => (
          <span
            key={g}
            className="absolute -translate-x-1/2 text-[10px] font-mono tabular-nums text-[var(--text-muted)]"
            style={{ left: `${pos(g)}%` }}
          >
            {g}
          </span>
        ))}
        <span className="absolute right-0 text-[10px] font-mono tabular-nums text-[var(--text-muted)]">{max}</span>
      </div>
    </div>
  )
}

export default function ZoneEditor({ profile, onSaved }) {
  const [bearbeiten, setBearbeiten] = useState(false)
  const [werte, setWerte] = useState({})
  const [fehler, setFehler] = useState(null)
  const [speichert, setSpeichert] = useState(false)
  const [zonen, setZonen] = useState(null)

  useEffect(() => {
    if (!profile) return
    setWerte(Object.fromEntries(GRENZEN.map(k => [k, profile[k] ?? ''])))
  }, [profile])

  // Neu laden, wenn sich eine Bezugsgröße ändert — nach einem Test oder einer
  // Eingabe stehen sonst die Bereiche des alten Werts da.
  useEffect(() => {
    if (!profile) return
    let abgebrochen = false
    getProfileZones()
      .then(({ data }) => { if (!abgebrochen) setZonen(data) })
      .catch(() => { if (!abgebrochen) setZonen({ lauf: [], rad: [], schwimm: [] }) })
    return () => { abgebrochen = true }
  }, [profile?.threshold_pace_s_per_km, profile?.ftp_watts, profile?.css_pace_s_per_100m])

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
      setFehler(fehlerText(e, 'Speichern fehlgeschlagen.'))
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
    return { label, zone: i + 1, name, wert }
  })

  // Vom Server, aus derselben Tabelle wie der Prompt. Leer, solange er
  // antwortet — dann lieber nichts als eine Kopie, die abweichen kann.
  const laufZeilen = pace && zonen?.lauf?.length ? zonen.lauf : null
  const radZeilen = ftp && zonen?.rad?.length ? zonen.rad : null

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
        {/* ── Puls ── Als Spalte, die die Höhe der Zeile ausfüllt: Die Leiste
            nimmt den freien Platz, die Zeilen stehen unten. So endet Z5 auf
            der Höhe der letzten Laufzeile (Steigerungen) — vorher hingen die
            Pulszeilen in der Mitte der Spalte und alles wirkte versetzt. */}
        <div className="flex flex-col">
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
                  const farbe = ZONE_COLOR[i + 1]
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
            <>
              <div className="flex-1 flex flex-col justify-center">
                <PulsLeiste profile={profile} />
              </div>
              <Zeilen daten={pulsZeilen} />
            </>
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
          {laufZeilen ? <Zeilen daten={laufZeilen} /> : pace ? (
            <p className="text-xs text-[var(--text-muted)]">Bereiche werden geladen…</p>
          ) : (
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

          {radZeilen ? (
            <>
              <Zeilen daten={radZeilen} />
              {/* Sweet Spot ist keine eigene Zone, sondern das obere Ende von
                  Z3 — und die Brot-und-Butter-Einheit im Aufbau. Ohne diese
                  Zeile müsste man ihn aus der Z3-Spanne selbst herausrechnen. */}
              {zonen?.sweet_spot && (
                <p className="text-[11px] text-[var(--text-secondary)] mt-2.5 font-mono tabular-nums">
                  Sweet Spot {zonen.sweet_spot} · oberes Z3
                </p>
              )}
            </>
          ) : ftp ? (
            <p className="text-xs text-[var(--text-muted)]">Bereiche werden geladen…</p>
          ) : (
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
