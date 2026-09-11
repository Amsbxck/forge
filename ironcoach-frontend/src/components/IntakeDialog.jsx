import { useState } from 'react'
import Modal from './Modal'
import { submitIntake } from '../services/api'

/** „5:13" → 313 Sekunden. Leere oder unlesbare Eingabe → null. */
function paceZuSekunden(text) {
  const t = (text || '').trim()
  if (!t) return null
  const m = t.match(/^(\d{1,2}):([0-5]\d)$/)
  if (!m) return NaN
  return Number(m[1]) * 60 + Number(m[2])
}

const FELD = 'w-full rounded-lg border px-3.5 py-2.5 text-base text-[#e8eaf0] outline-none focus:border-[#00d4ff55] placeholder:text-[var(--text-muted)]'
const FELD_STIL = { background: '#0d0f14', borderColor: '#1e2228' }
const LABEL = 'block text-[11px] font-mono tracking-widest text-[var(--text-secondary)] mb-2'

const ZONEN = [
  { von: null, bis: 'z1_hr_max', label: 'Z1' },
  { von: 'z2_hr_min', bis: 'z2_hr_max', label: 'Z2' },
  { von: 'z3_hr_min', bis: 'z3_hr_max', label: 'Z3' },
  { von: 'z4_hr_min', bis: 'z4_hr_max', label: 'Z4' },
]

const ZONEN_FELDER = ['z1_hr_max', 'z2_hr_min', 'z2_hr_max',
                      'z3_hr_min', 'z3_hr_max', 'z4_hr_min', 'z4_hr_max']

export default function IntakeDialog({ open, name, onFertig }) {
  const [f, setF] = useState({})
  const [zonenAuf, setZonenAuf] = useState(false)
  const [fehler, setFehler] = useState(null)
  const [busy, setBusy] = useState(null)

  const setz = (k) => (e) => setF(v => ({ ...v, [k]: e.target.value }))
  const zahl = (k) => {
    const v = f[k]
    if (v === undefined || v === '') return undefined
    const n = Number(v)
    return Number.isFinite(n) && n > 0 ? n : NaN
  }

  const senden = async (mitWerten) => {
    setFehler(null)
    let nutzlast = {}

    if (mitWerten) {
      for (const k of ['max_hr', 'threshold_hr', 'ftp_watts', 'swim_threshold_hr']) {
        const n = zahl(k)
        if (Number.isNaN(n)) return setFehler('Bitte nur positive Zahlen eintragen.')
        if (n !== undefined) nutzlast[k] = n
      }

      for (const [feld, schluessel] of [['pace', 'threshold_pace_s_per_km'], ['css', 'css_pace_s_per_100m']]) {
        const s = paceZuSekunden(f[feld])
        if (Number.isNaN(s)) return setFehler('Pace bitte als m:ss eintragen, zum Beispiel 5:13.')
        if (s !== null) nutzlast[schluessel] = s
      }

      // Zonen nur mitschicken, wenn alle sieben Grenzen da sind — der Server
      // weist Teilangaben ohnehin ab, aber der Hinweis soll hier entstehen.
      const gesetzt = ZONEN_FELDER.filter(k => f[k] !== undefined && f[k] !== '')
      if (gesetzt.length) {
        if (gesetzt.length !== ZONEN_FELDER.length) {
          return setFehler('Pulszonen bitte vollständig ausfüllen — oder ganz weglassen.')
        }
        for (const k of ZONEN_FELDER) {
          const n = zahl(k)
          if (Number.isNaN(n)) return setFehler('Zonengrenzen bitte als Zahl eintragen.')
          nutzlast[k] = n
        }
      }

      if (!Object.keys(nutzlast).length) {
        return setFehler('Noch nichts eingetragen. Nutze „Überspringen", wenn du deine Werte nicht kennst.')
      }
    }

    setBusy(mitWerten ? 'werte' : 'skip')
    try {
      await submitIntake(nutzlast)
      onFertig?.()
    } catch (e) {
      setFehler(e?.response?.data?.detail || 'Speichern fehlgeschlagen.')
      setBusy(null)
    }
  }

  return (
    <Modal
      open={open}
      /* Bewusst nicht schließbar per Klick daneben oder Escape: Es gibt genau
         zwei Wege hier heraus, und beide sind eine Entscheidung. Ein
         versehentliches Wegklicken sähe aus wie „übersprungen", ohne es zu
         sein. */
      onClose={() => {}}
      dismissible={false}
      title={name ? `Willkommen, ${name}!` : 'Willkommen!'}
      subtitle="Schön, dass du da bist."
      width="max-w-3xl"
      align="upper"
    >
      <div className="space-y-6">
        <p className="text-sm text-[#e8eaf0] leading-relaxed">
          Bevor es losgeht, eine Frage: <span className="text-[#00d4ff]">Kennst du
          deine Trainingswerte schon?</span>
        </p>
        <p className="text-sm text-[var(--text-secondary)] leading-relaxed">
          Wenn du mit einer Uhr trainierst, stehen die meisten dieser Zahlen
          bereits in Garmin Connect oder Strava. Je mehr davon hier steht, desto
          genauer plant der Coach deine erste Woche — statt mit Schätzwerten für
          jemanden, den er noch nicht kennt.
        </p>
        <p className="text-sm text-[var(--text-secondary)] leading-relaxed">
          <span className="text-[#e8eaf0]">Alles ist freiwillig und einzeln.</span> Trag
          ein, was du weißt, und lass den Rest leer — ein einzelner Wert hilft
          schon. Kennst du gar nichts davon, ist das völlig in Ordnung: dann
          klick unten auf Überspringen.
        </p>

        {/* ── Puls ── */}
        <section>
          <div className="text-[11px] font-mono tracking-widest text-[#00d4ff] mb-2.5">PULS</div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={LABEL}>MAXIMALPULS</label>
              <input className={FELD} style={FELD_STIL} inputMode="numeric"
                     value={f.max_hr ?? ''} onChange={setz('max_hr')} placeholder="z. B. 195" />
            </div>
            <div>
              <label className={LABEL}>SCHWELLENPULS LAUFEN</label>
              <input className={FELD} style={FELD_STIL} inputMode="numeric"
                     value={f.threshold_hr ?? ''} onChange={setz('threshold_hr')} placeholder="z. B. 178" />
            </div>
          </div>

          <button type="button" onClick={() => setZonenAuf(v => !v)}
                  className="text-[10px] font-mono tracking-widest text-[var(--text-secondary)] hover:text-[#00d4ff] mt-3">
            {zonenAuf ? '− PULSZONEN AUSBLENDEN' : '+ EIGENE PULSZONEN EINTRAGEN'}
          </button>

          {zonenAuf && (
            <div className="mt-3 space-y-2">
              <p className="text-sm text-[var(--text-secondary)] leading-relaxed">
                Nur nötig, wenn deine Uhr eigene Bereiche misst. Ohne Angabe
                werden sie aus dem Maximalpuls berechnet.
              </p>
              {ZONEN.map(({ von, bis, label }) => (
                <div key={label} className="flex items-center gap-2">
                  <span className="w-7 text-[11px] font-mono text-[var(--text-secondary)]">{label}</span>
                  <input className={`${FELD} font-mono`} style={FELD_STIL} inputMode="numeric"
                         placeholder={von ? 'von' : '≤'} disabled={!von}
                         value={von ? (f[von] ?? '') : ''} onChange={von ? setz(von) : undefined} />
                  <span className="text-[var(--text-muted)]">–</span>
                  <input className={`${FELD} font-mono`} style={FELD_STIL} inputMode="numeric"
                         placeholder="bis" value={f[bis] ?? ''} onChange={setz(bis)} />
                </div>
              ))}
            </div>
          )}
        </section>

        {/* ── Tempo und Leistung ── */}
        <section>
          <div className="text-[11px] font-mono tracking-widest text-[#00d4ff] mb-2.5">TEMPO UND LEISTUNG</div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className={LABEL}>SCHWELLENPACE /KM</label>
              <input className={`${FELD} font-mono`} style={FELD_STIL}
                     value={f.pace ?? ''} onChange={setz('pace')} placeholder="5:13" />
            </div>
            <div>
              <label className={LABEL}>FTP RAD (W)</label>
              <input className={FELD} style={FELD_STIL} inputMode="numeric"
                     value={f.ftp_watts ?? ''} onChange={setz('ftp_watts')} placeholder="z. B. 240" />
            </div>
            <div>
              <label className={LABEL}>CSS /100 M</label>
              <input className={`${FELD} font-mono`} style={FELD_STIL}
                     value={f.css ?? ''} onChange={setz('css')} placeholder="1:45" />
            </div>
          </div>
        </section>

        <div className="rounded-lg border px-3 py-2.5"
             style={{ borderColor: '#00d4ff33', background: '#00d4ff0d' }}>
          <p className="text-sm text-[var(--text-secondary)] leading-relaxed">
            <span className="text-[#00d4ff] font-mono text-[10px] tracking-widest">WICHTIG · </span>
            Die Testwoche findet in jedem Fall statt — auch wenn du hier alles
            einträgst. Eingetragene Werte stammen aus einem anderen Zeitraum und
            altern; der Test misst sie unter den Bedingungen, unter denen du
            danach trainierst. Bis dahin plant der Coach mit deinen Angaben statt
            mit Schätzwerten.
          </p>
        </div>

        {fehler && (
          <p className="text-xs leading-relaxed" style={{ color: '#ef4444' }}>{fehler}</p>
        )}

        <div className="flex items-center justify-between gap-3 pt-1">
          <button
            onClick={() => senden(false)}
            disabled={!!busy}
            className="px-5 py-3 rounded-lg text-sm font-mono tracking-widest border transition-colors disabled:opacity-40"
            style={{ borderColor: '#1e2228', background: '#16181e', color: 'var(--text-secondary)' }}
          >
            {busy === 'skip' ? 'MOMENT…' : 'ÜBERSPRINGEN'}
          </button>
          <button
            onClick={() => senden(true)}
            disabled={!!busy}
            className="px-6 py-3 rounded-lg text-sm font-mono font-bold tracking-widest border transition-colors disabled:opacity-40"
            style={{ borderColor: '#00d4ff44', background: '#00d4ff20', color: '#00d4ff' }}
          >
            {busy === 'werte' ? 'SPEICHERT…' : 'WERTE ÜBERNEHMEN'}
          </button>
        </div>
      </div>
    </Modal>
  )
}
