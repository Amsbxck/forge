import { useEffect, useState } from 'react'

/** Anteile als eine Leiste — jedes Segment so breit wie sein Wert.
 *
 *  Zuerst die Urne der Doppeltag-Ziehung (`DoppeltagZiehung`): Kugeln nach
 *  Gewicht, die gezogene leuchtet, eine Marke darüber. Amir mochte diese
 *  Leiste ausdrücklich; dieselbe Form trägt jetzt die HF-Zonen der Woche und
 *  den Budgetverbrauch nach Art. Eine Optik für „wie verteilt sich das".
 *
 *  `segmente`: `[{key, name, wert, farbe, schraffiert}]`. Segmente mit Wert 0
 *  fallen weg — eine Breite von null wäre eine Beschriftung ohne Fläche.
 *  `treffer`: der Schlüssel, der hervorgehoben wird (Marke, Schein, Glanz),
 *  oder `null`.
 *  `einheit`: Anhängsel für den Wert unter dem Namen; ohne sie stehen Prozent.
 *  `markenZeile`: die Zeile für die Marke auch ohne Treffer freihalten — die
 *  Urne schaltet ihn mit „× OHNE" aus, und die Leiste soll dabei nicht springen.
 */
export default function SegmentLeiste({
  segmente, treffer = null, kopf, kopfRechts, einheit, mindestens = 2,
  markenZeile = treffer != null,
}) {
  // Einlaufen beim ersten Zeichnen: Die Segmente wachsen von null auf ihren
  // Wert. Einmal, nicht bei jedem Neuzeichnen — sonst zuckt die Leiste bei
  // jedem Tastendruck in einem Feld daneben.
  const [da, setDa] = useState(false)
  useEffect(() => {
    const t = requestAnimationFrame(() => setDa(true))
    return () => cancelAnimationFrame(t)
  }, [])

  const sichtbar = (segmente || []).filter(s => (s.wert || 0) > 0)
  if (sichtbar.length < mindestens) return null
  const summe = sichtbar.reduce((a, s) => a + s.wert, 0)
  const anteil = s => Math.round((s.wert / summe) * 100)

  return (
    <div>
      {(kopf || kopfRechts) && (
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-[9px] font-mono tracking-[0.2em] text-[var(--text-muted)]">{kopf}</span>
          <span className="text-[9px] font-mono text-[var(--text-muted)]">{kopfRechts}</span>
        </div>
      )}

      {/* Die Marke über dem Treffer — eine eigene Zeile mit denselben
          Breiten, damit sie genau über ihrem Segment steht. */}
      {markenZeile && (
        <div className="flex gap-[3px] h-2">
          {sichtbar.map(s => (
            <div key={s.key} className="flex justify-center" style={{ flexGrow: s.wert, flexBasis: 0 }}>
              {s.key === treffer && (
                <span
                  className="block w-0 h-0"
                  style={{
                    borderLeft: '4px solid transparent',
                    borderRight: '4px solid transparent',
                    borderTop: `5px solid ${s.farbe}`,
                    filter: `drop-shadow(0 0 4px ${s.farbe})`,
                  }}
                />
              )}
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-[3px] h-2.5 mt-0.5">
        {sichtbar.map(s => {
          const an = s.key === treffer
          return (
            <div
              key={s.key}
              title={`${s.name}: ${einheit ? `${s.wert} ${einheit}` : `${anteil(s)} %`}`}
              className="relative h-full rounded-[3px] overflow-hidden transition-[flex-grow] duration-700 ease-out"
              style={{
                flexGrow: da ? s.wert : 0.0001,
                flexBasis: 0,
                background: an ? `linear-gradient(90deg, ${s.farbe}aa, ${s.farbe})` : s.farbe,
                boxShadow: an ? `0 0 12px ${s.farbe}88, inset 0 0 0 1px ${s.farbe}` : 'inset 0 0 0 1px #ffffff08',
                backgroundImage: s.schraffiert && !an
                  ? 'repeating-linear-gradient(135deg, transparent 0 3px, #0a0c0f 3px 5px)'
                  : undefined,
              }}
            >
              {an && (
                <span
                  className="absolute inset-y-0 w-1/2"
                  style={{
                    background: 'linear-gradient(90deg, transparent, #ffffff66, transparent)',
                    animation: 'leiste-glanz 2.8s ease-in-out infinite',
                  }}
                />
              )}
            </div>
          )
        })}
      </div>

      <div className="flex gap-[3px] mt-1.5">
        {sichtbar.map(s => {
          const an = s.key === treffer
          return (
            <div key={s.key} className="min-w-0" style={{ flexGrow: s.wert, flexBasis: 0 }}>
              <div
                className="text-[9px] font-mono truncate"
                style={{ color: an ? s.farbe : s.textFarbe || 'var(--text-secondary)' }}
              >
                {s.name}
              </div>
              <div
                className="text-[9px] font-mono tabular-nums truncate"
                style={{ color: an ? `${s.farbe}bb` : 'var(--text-muted)' }}
              >
                {einheit ? `${s.wert} ${einheit}` : `${anteil(s)}%`}
              </div>
            </div>
          )
        })}
      </div>

      <style>{`
        @keyframes leiste-glanz {
          0% { left: -50%; }
          60%, 100% { left: 110%; }
        }
      `}</style>
    </div>
  )
}
