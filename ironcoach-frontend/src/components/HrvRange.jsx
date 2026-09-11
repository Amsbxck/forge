import { useCallback, useEffect, useState } from 'react'
import { clearHrvRange, getHrvRange, setHrvRange } from '../services/api'

const CARD = 'bg-[#111318] border border-[#1e2228] rounded-xl'
const LABEL = 'text-[11px] font-mono font-bold tracking-widest text-[var(--text-secondary)] block mb-1'
const FIELD = 'rounded-lg px-3 py-2 text-sm font-mono text-[#e8eaf0] placeholder-[var(--text-muted)] outline-none w-full'
const FIELD_STYLE = { background: '#0d0f17', border: '1px solid #1e2228' }
const DISPLAY = { fontFamily: 'Barlow Condensed, sans-serif' }

/** Die persönliche HRV-Spanne.
 *
 *  rMSSD ist zwischen Menschen extrem verschieden — 35 und 120 sind beide
 *  normal. Eine feste Schwelle für alle stünde bei vielen dauerhaft auf Rot,
 *  und weil der Zustand in die Planung eingeht, striche der Coach dauerhaft
 *  Intensität. Deshalb zählt die eigene Streuung, oder ein eingetragener Wert.
 */
export default function HrvRange() {
  const [daten, setDaten] = useState(null)
  const [offen, setOffen] = useState(false)
  const [form, setForm] = useState({ von: '', bis: '' })
  const [busy, setBusy] = useState(false)
  const [fehler, setFehler] = useState(null)
  const [hinweis, setHinweis] = useState(null)

  const laden = useCallback(async () => {
    try { setDaten((await getHrvRange()).data) } catch { /* still */ }
  }, [])
  useEffect(() => { laden() }, [laden])

  if (!daten) return null

  const { grenzen, baseline, min_messungen: mindestens } = daten
  const eigen = grenzen?.quelle === 'manual'

  const speichern = async () => {
    setBusy(true); setFehler(null)
    try {
      const { data } = await setHrvRange({
        band_low: Number(form.von), band_high: Number(form.bis),
      })
      setHinweis(
        `Übernommen: grün ab ${data.gruen_ab}, rot unter ${data.rot_unter}. `
        + `${data.neu_bewertet} Messungen neu bewertet.`
      )
      setOffen(false); setForm({ von: '', bis: '' })
      laden()
    } catch (err) {
      setFehler(err.response?.data?.detail || 'Speichern fehlgeschlagen')
    } finally { setBusy(false) }
  }

  const zuruecksetzen = async () => {
    setBusy(true)
    try { const { data } = await clearHrvRange()
      setHinweis(`Zurückgesetzt. ${data.neu_bewertet} Messungen neu bewertet.`)
      laden()
    } finally { setBusy(false) }
  }

  return (
    <div className={`${CARD} p-5`}>
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full" style={{ background: '#22c55e' }} />
          <span className="text-sm font-bold tracking-widest" style={{ ...DISPLAY, color: '#22c55e' }}>
            HRV · NORMALSPANNE
          </span>
        </div>
        <div className="flex gap-2">
          {eigen && (
            <button onClick={zuruecksetzen} disabled={busy}
                    className="text-[10px] font-mono text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
                    title="Zurück zur berechneten Spanne">
              ZURÜCKSETZEN
            </button>
          )}
          <button onClick={() => { setOffen(o => !o); setFehler(null) }}
                  className="text-[10px] font-mono" style={{ color: '#22c55e' }}>
            {offen ? 'SCHLIESSEN' : grenzen ? 'ÄNDERN' : 'EINTRAGEN'}
          </button>
        </div>
      </div>

      {grenzen ? (
        <>
          <div className="flex gap-7 flex-wrap mt-3">
            <div>
              <div className={LABEL}>GRÜNER BEREICH</div>
              <div className="font-black leading-none" style={{ ...DISPLAY, color: '#22c55e', fontSize: 'clamp(2.4rem, 5vw, 3.4rem)' }}>
                {grenzen.gruen_bis
                  ? <>{grenzen.gruen_ab}<span className="text-2xl mx-1 text-[var(--text-muted)]">–</span>{grenzen.gruen_bis}</>
                  : <>ab {grenzen.gruen_ab}</>}
                <span className="text-lg font-normal text-[var(--text-secondary)] ml-1">ms</span>
              </div>
            </div>
            <div>
              <div className={LABEL}>ROT UNTER</div>
              <div className="font-black leading-none" style={{ ...DISPLAY, color: '#ef4444', fontSize: 'clamp(2.4rem, 5vw, 3.4rem)' }}>
                {grenzen.rot_unter}<span className="text-lg font-normal text-[var(--text-secondary)] ml-1">ms</span>
              </div>
            </div>
          </div>
          <div className="text-[10px] font-mono text-[var(--text-muted)] mt-2">
            {eigen
              ? 'von dir eingetragen'
              : `berechnet aus deinen letzten ${baseline?.messungen} Messungen · Ø ${baseline?.mean} ms, Streuung ${baseline?.sd} ms`}
          </div>
        </>
      ) : (
        <div className="mt-3 rounded-lg px-3 py-2.5 text-xs leading-relaxed"
             style={{ background: '#f59e0b12', border: '1px solid #f59e0b33', color: '#f59e0b' }}>
          Noch keine Ampel: {baseline?.messungen ?? 0} von {mindestens} nötigen Messungen.
          Solange die Grundlinie entsteht, wird nichts bewertet — eine geratene
          Schwelle wäre schlechter als keine, weil der Zustand in die Planung eingeht.
          Wer seine Spanne kennt, etwa aus Garmin Connect, kann sie hier eintragen.
        </div>
      )}

      {offen && (
        <div className="mt-4 pt-4 border-t border-[#1e2228] space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className={LABEL}>GRÜNER BEREICH VON (MS)</span>
              <input className={FIELD} style={FIELD_STYLE} type="number" step="0.1" placeholder="65"
                     value={form.von} onChange={e => setForm(f => ({ ...f, von: e.target.value }))} />
            </label>
            <label className="block">
              <span className={LABEL}>BIS (MS)</span>
              <input className={FIELD} style={FIELD_STYLE} type="number" step="0.1" placeholder="110"
                     value={form.bis} onChange={e => setForm(f => ({ ...f, bis: e.target.value }))} />
            </label>
          </div>
          <p className="text-[10px] font-mono text-[var(--text-muted)] leading-relaxed">
            Genau der grüne Bereich, den Garmin unter HRV-Status anzeigt — beide
            Enden abtippen. Die rote Grenze wird daraus abgeleitet: ein Viertel
            der Bandbreite darunter, sodass der gelbe Bereich mit deiner eigenen
            Streuung skaliert. Eingetragene Werte werden nicht überschrieben, und
            alle bisherigen Messungen werden damit neu bewertet.
          </p>
          {fehler && <div className="text-[11px] font-mono text-[#ef4444]">{fehler}</div>}
          <button onClick={speichern} disabled={busy || !form.von || !form.bis}
                  className="px-4 py-2 rounded-lg text-[11px] font-mono font-bold tracking-wide disabled:opacity-30"
                  style={{ background: '#22c55e20', border: '1px solid #22c55e44', color: '#22c55e' }}>
            {busy ? '…' : 'ÜBERNEHMEN'}
          </button>
        </div>
      )}

      {hinweis && <div className="text-[10px] font-mono text-[#00d4ff] mt-3">{hinweis}</div>}
    </div>
  )
}
