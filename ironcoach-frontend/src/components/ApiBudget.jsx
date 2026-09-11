import { useCallback, useEffect, useState } from 'react'
import { getBudget, getBudgetUsage } from '../services/api'

const CARD = 'bg-[#111318] border border-[#1e2228] rounded-xl'
const DISPLAY = { fontFamily: 'Barlow Condensed, sans-serif' }

const ART = { plan: 'Wochenplan', chat: 'Coach-Chat' }

/** Guthaben für die Plangenerierung.
 *
 *  Alle Athleten laufen über einen gemeinsamen API-Schlüssel, aber jeder
 *  verbraucht sein eigenes Guthaben. Ohne sichtbaren Stand bemerkt man das
 *  Ende erst, wenn ein Plan nicht mehr erstellt wird — deshalb steht hier,
 *  was übrig ist und wofür es verbraucht wurde.
 */
export default function ApiBudget() {
  const [stand, setStand] = useState(null)
  const [verlauf, setVerlauf] = useState([])
  const [offen, setOffen] = useState(false)

  const laden = useCallback(async () => {
    try {
      const [b, v] = await Promise.all([getBudget(), getBudgetUsage()])
      setStand(b.data)
      setVerlauf(v.data || [])
    } catch { /* still */ }
  }, [])
  useEffect(() => { laden() }, [laden])

  if (!stand) return null

  const anteil = stand.guthaben_eur > 0
    ? Math.min(1, stand.verbraucht_eur / stand.guthaben_eur)
    : 1
  const farbe = stand.aufgebraucht ? '#ef4444' : anteil > 0.8 ? '#f59e0b' : '#00d4ff'

  return (
    <div className={`${CARD} p-5`}>
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="text-sm font-bold tracking-widest" style={{ ...DISPLAY, color: farbe }}>
            GUTHABEN · COACH
          </div>
          <div className="font-black leading-none mt-2"
               style={{ ...DISPLAY, color: farbe, fontSize: 'clamp(2.4rem, 5vw, 3.2rem)' }}>
            {stand.rest_eur.toFixed(2).replace('.', ',')}
            <span className="text-lg font-normal text-[var(--text-secondary)] ml-1">€ übrig</span>
          </div>
          <div className="text-[10px] font-mono text-[var(--text-muted)] mt-1.5">
            {stand.verbraucht_eur.toFixed(2).replace('.', ',')} € von{' '}
            {stand.guthaben_eur.toFixed(2).replace('.', ',')} € verbraucht · {stand.aufrufe} Aufrufe
          </div>
        </div>
        {verlauf.length > 0 && (
          <button onClick={() => setOffen(o => !o)}
                  className="text-[10px] font-mono text-[var(--text-muted)] hover:text-[#00d4ff]">
            {offen ? 'SCHLIESSEN' : 'VERBRAUCH ANSEHEN'}
          </button>
        )}
      </div>

      {/* Balken: der Rest ist wichtiger als die Zahl, weil er zeigt, wie
          lange es noch reicht. */}
      <div className="h-1.5 rounded-full overflow-hidden mt-4" style={{ background: '#0d0f17' }}>
        <div className="h-full rounded-full transition-all"
             style={{ width: `${anteil * 100}%`, background: farbe }} />
      </div>

      {stand.aufgebraucht && (
        <div className="mt-4 rounded-lg px-3 py-2.5 text-xs leading-relaxed"
             style={{ background: '#ef444412', border: '1px solid #ef444433', color: '#ef4444' }}>
          Guthaben aufgebraucht. Neue Wochenpläne und Chat-Antworten sind erst nach
          dem Aufladen wieder möglich. Alles andere — Einheiten, Auswertung, Reflexionen —
          läuft weiter.
        </div>
      )}

      {offen && (
        <div className="mt-4 pt-4 border-t border-[#1e2228] space-y-1">
          {verlauf.map((z, i) => (
            <div key={i} className="flex items-center gap-3 text-[11px] font-mono">
              <span className="text-[var(--text-muted)] w-24 flex-shrink-0">
                {z.datum ? z.datum.slice(0, 10) : '—'}
              </span>
              <span className="text-[var(--text-secondary)] flex-1">{ART[z.art] || z.art}</span>
              <span className="text-[var(--text-muted)] tabular-nums hidden sm:block">
                {z.token_ein.toLocaleString('de-DE')} ein / {z.token_aus.toLocaleString('de-DE')} aus
              </span>
              <span className="text-[#e8eaf0] tabular-nums w-16 text-right">
                {z.kosten_eur.toFixed(3).replace('.', ',')} €
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
