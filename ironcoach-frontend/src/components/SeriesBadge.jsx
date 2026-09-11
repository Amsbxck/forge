import { useState } from 'react'
import { detectSeries } from '../utils/raceSeries'

/** Serienkennzeichen auf der Rennkarte.
 *
 *  Standardmäßig als Schriftzug im Stil der App. Liegt unter
 *  `public/series/<key>.svg` eine echte Logodatei, wird die stattdessen
 *  genommen — so lässt sich das nachrüsten, ohne den Code anzufassen.
 *
 *  Warum nicht gleich die echten Logos mitliefern: Ironman und Challenge sind
 *  eingetragene Marken. In der eigenen Installation ist das unkritisch, im
 *  öffentlich verteilten Repository wäre es fremdes Material.
 */
export default function SeriesBadge({ race, className = '' }) {
  const series = detectSeries(race)
  const [logoFehlt, setLogoFehlt] = useState(false)

  if (!series) return null

  const logo = series.key && !logoFehlt ? `/series/${series.key}.svg` : null

  if (logo) {
    return (
      <img
        src={logo}
        alt={series.label}
        onError={() => setLogoFehlt(true)}
        className={`h-5 w-auto object-contain ${className}`}
        style={{ maxWidth: '110px' }}
      />
    )
  }

  return (
    <span
      className={`inline-flex items-baseline gap-1 px-1.5 py-0.5 rounded font-mono font-bold text-[9px] tracking-widest ${className}`}
      style={{
        color: series.color,
        background: `${series.color}14`,
        border: `1px solid ${series.color}3a`,
      }}
    >
      {series.label}
      {series.sub && <span className="text-[8px] opacity-70">{series.sub}</span>}
    </span>
  )
}
