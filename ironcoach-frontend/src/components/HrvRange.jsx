import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getHrvRange } from '../services/api'

const CARD = 'bg-[#111318] border border-[#1e2228] rounded-xl'
const LABEL = 'text-[11px] font-mono font-bold tracking-widest text-[var(--text-secondary)] block mb-1'
const DISPLAY = { fontFamily: 'Barlow Condensed, sans-serif' }

/** Die persönliche HRV-Spanne.
 *
 *  rMSSD ist zwischen Menschen extrem verschieden — 35 und 120 sind beide
 *  normal. Eine feste Schwelle für alle stünde bei vielen dauerhaft auf Rot,
 *  und weil der Zustand in die Planung eingeht, striche der Coach dauerhaft
 *  Intensität. Deshalb zählt die eigene Streuung, oder Garmins Baseline.
 *
 *  Nur noch Anzeige: Die Spanne kommt aus Garmin Connect (sonntags
 *  aktualisiert, siehe Anbindungen) und ist nicht mehr von Hand änderbar.
 *  Vorher wurde Garmins grüner Bereich hier abgetippt. Eine früher
 *  eingetragene Spanne gilt weiter und wird als solche benannt.
 */
export default function HrvRange() {
  const [daten, setDaten] = useState(null)

  const laden = useCallback(async () => {
    try { setDaten((await getHrvRange()).data) } catch { /* still */ }
  }, [])
  useEffect(() => { laden() }, [laden])

  if (!daten) return null

  const { grenzen, baseline, min_messungen: mindestens, garmin_verbunden: garminVerbunden } = daten
  // Nach dem Trennen bleibt Garmins letzte Spanne bewusst stehen (die Ampel
  // soll nicht still umspringen). Dann darf hier aber nicht mehr „wird
  // aktualisiert" stehen.
  const herkunft = grenzen?.quelle === 'garmin'
    ? (garminVerbunden
        ? 'aus Garmin Connect · wird jeden Sonntag aktualisiert'
        : 'aus Garmin Connect · nicht mehr verbunden, wird nicht aktualisiert')
    : grenzen?.quelle === 'manual'
      ? 'von dir eingetragen'
      : `berechnet aus deinen letzten ${baseline?.messungen} Messungen · Ø ${baseline?.mean} ms, Streuung ${baseline?.sd} ms`

  return (
    <div className={`${CARD} p-5`}>
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full" style={{ background: '#22c55e' }} />
          <span className="text-sm font-bold tracking-widest" style={{ ...DISPLAY, color: '#22c55e' }}>
            HRV · NORMALSPANNE
          </span>
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
            {herkunft}
          </div>
        </>
      ) : (
        <div className="mt-3 rounded-lg px-3 py-2.5 text-xs leading-relaxed"
             style={{ background: '#f59e0b12', border: '1px solid #f59e0b33', color: '#f59e0b' }}>
          Noch keine Ampel: {baseline?.messungen ?? 0} von {mindestens} nötigen Messungen.
          Solange die Grundlinie entsteht, wird nichts bewertet — eine geratene
          Schwelle wäre schlechter als keine, weil der Zustand in die Planung eingeht.
          {/* Mit Garmin wäre der Verweis auf die Kachel sinnlos: Dann fehlt
              nur noch Garmins Baseline, die in den ersten Wochen entsteht. */}
          {garminVerbunden ? (
            <> Garmin lernt deine Spanne noch (die ersten etwa drei Wochen). Die Ampel
              kommt, sobald Garmins Spanne oder genug eigene Messungen da sind.</>
          ) : (
            <> Mit Garmin geht es schneller: Verbinde Garmin Connect unter{' '}
              <Link to="/connect" className="underline">Anbindungen</Link>, dann kommt
              deine Spanne direkt aus der Uhr, sobald Garmin sie gelernt hat.</>
          )}
        </div>
      )}
    </div>
  )
}
