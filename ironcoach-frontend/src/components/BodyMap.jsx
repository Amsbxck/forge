import { useState } from 'react'

/** Körperstelle durch Anklicken wählen.
 *
 *  Statt einer Auswahlliste mit dreizehn Begriffen: Man zeigt auf die Stelle,
 *  die weh tut. Das ist die Bewegung, die man ohnehin macht, wenn jemand
 *  fragt "wo?" — und sie verlangt kein Vokabular. "Tibiakante" muss niemand
 *  kennen, um auf sein Schienbein zu zeigen.
 *
 *  Die Schlüssel müssen mit `KOERPERSTELLEN` im Backend übereinstimmen
 *  (services/health.py). Eine unbekannte Stelle weist der Endpunkt ab, statt
 *  sie stillschweigend zu verwerfen — sonst bestätigte die Oberfläche eine
 *  Meldung, die im Plan nichts ändert.
 *
 *  Zwei Ansichten, eine Silhouette: Von vorn und von hinten sieht ein
 *  symmetrischer Umriss gleich aus, nur die Stellen darauf unterscheiden sich.
 *  Nötig ist die Rückansicht, weil Rücken, Wade und Achillessehne von vorn
 *  nicht anklickbar wären — und genau das sind häufige Laufbeschwerden.
 */

// Silhouette, aus einfachen Formen zusammengesetzt statt aus einer langen
// Pfadangabe: So lässt sich eine Proportion ändern, ohne Koordinaten zu raten.
const KOERPER = (
  <g>
    <circle cx="50" cy="24" r="15" />
    <rect x="44" y="37" width="12" height="9" rx="3" />
    {/* Rumpf */}
    <path d="M28 48 Q50 42 72 48 L68 118 Q50 123 32 118 Z" />
    {/* Becken */}
    <path d="M32 116 L68 116 L65 146 Q50 152 35 146 Z" />
    {/* Arme */}
    <path d="M28 50 L20 56 L15 122 L23 125 L30 62 Z" />
    <path d="M72 50 L80 56 L85 122 L77 125 L70 62 Z" />
    {/* Beine */}
    <path d="M35 144 L48 144 L45 246 L37 246 Z" />
    <path d="M52 144 L65 144 L63 246 L55 246 Z" />
    {/* Füße */}
    <path d="M37 246 L45 246 L46 262 L34 262 Z" />
    <path d="M55 246 L63 246 L66 262 L54 262 Z" />
  </g>
)

// x-Koordinate 50 = Mitte. Paare stehen für links und rechts; beide zeigen auf
// dieselbe Stelle — welche Seite betroffen ist, gehört in die Notiz, nicht in
// die Trainingsvorgabe. Für den Plan ändert es nichts.
const VORNE = [
  { key: 'kopf', label: 'Kopf', punkte: [[50, 22]] },
  { key: 'schulter', label: 'Schulter', punkte: [[29, 52], [71, 52]] },
  { key: 'brust', label: 'Brust / Rippen', punkte: [[50, 70]] },
  { key: 'arm', label: 'Arm / Ellbogen', punkte: [[19, 98], [81, 98]] },
  { key: 'huefte', label: 'Hüfte', punkte: [[50, 132]] },
  { key: 'oberschenkel', label: 'Oberschenkel', punkte: [[42, 170], [58, 170]] },
  { key: 'knie', label: 'Knie', punkte: [[43, 200], [57, 200]] },
  { key: 'schienbein', label: 'Schienbein', punkte: [[42, 226], [58, 226]] },
  { key: 'fuss', label: 'Fuß', punkte: [[40, 256], [60, 256]] },
]

const HINTEN = [
  { key: 'kopf', label: 'Kopf', punkte: [[50, 22]] },
  { key: 'nacken', label: 'Nacken', punkte: [[50, 43]] },
  { key: 'schulter', label: 'Schulter', punkte: [[29, 52], [71, 52]] },
  { key: 'ruecken', label: 'Rücken', punkte: [[50, 95]] },
  { key: 'arm', label: 'Arm / Ellbogen', punkte: [[19, 98], [81, 98]] },
  { key: 'huefte', label: 'Hüfte', punkte: [[50, 132]] },
  { key: 'oberschenkel', label: 'Oberschenkel (hinten)', punkte: [[42, 170], [58, 170]] },
  { key: 'knie', label: 'Knie', punkte: [[43, 200], [57, 200]] },
  { key: 'wade', label: 'Wade', punkte: [[42, 222], [58, 222]] },
  { key: 'achillessehne', label: 'Achillessehne', punkte: [[41, 243], [59, 243]] },
  { key: 'fuss', label: 'Fuß', punkte: [[40, 258], [60, 258]] },
]

const AKZENT = '#00d4ff'
const WARN = '#f59e0b'

export default function BodyMap({ value, onChange }) {
  const [ansicht, setAnsicht] = useState('vorne')
  const [hover, setHover] = useState(null)

  const stellen = ansicht === 'vorne' ? VORNE : HINTEN
  // Die gewählte Stelle kann auf der anderen Ansicht liegen — dann steht ihr
  // Name trotzdem unten, sonst sieht die Auswahl aus wie verloren.
  const gewaehlt = [...VORNE, ...HINTEN].find(s => s.key === value)
  const angezeigt = hover ? stellen.find(s => s.key === hover) : gewaehlt

  return (
    <div>
      <div className="flex gap-1 mb-2">
        {[['vorne', 'VORNE'], ['hinten', 'HINTEN']].map(([key, text]) => (
          <button
            key={key}
            type="button"
            onClick={() => setAnsicht(key)}
            className="px-2.5 py-1 rounded text-[10px] font-mono tracking-widest transition-colors"
            style={{
              background: ansicht === key ? `${AKZENT}1a` : 'transparent',
              border: `1px solid ${ansicht === key ? `${AKZENT}44` : '#1e2228'}`,
              color: ansicht === key ? AKZENT : 'var(--text-muted)',
            }}
          >
            {text}
          </button>
        ))}
      </div>

      <div className="flex items-start gap-4">
        <svg viewBox="0 0 100 275" width="118" height="325" role="group"
             aria-label="Körperstelle wählen" style={{ flexShrink: 0 }}>
          <g fill="#1e2430" stroke="#2b3342" strokeWidth="1">{KOERPER}</g>

          {stellen.map(stelle => {
            const aktiv = value === stelle.key
            const drueber = hover === stelle.key
            return stelle.punkte.map(([cx, cy], i) => (
              <circle
                key={`${stelle.key}-${i}`}
                cx={cx} cy={cy} r="11"
                role="button"
                tabIndex={0}
                aria-label={stelle.label}
                aria-pressed={aktiv}
                onClick={() => onChange(aktiv ? null : stelle.key)}
                onKeyDown={e => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    onChange(aktiv ? null : stelle.key)
                  }
                }}
                onMouseEnter={() => setHover(stelle.key)}
                onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(stelle.key)}
                onBlur={() => setHover(null)}
                style={{ cursor: 'pointer', outline: 'none', transition: 'all .12s' }}
                fill={aktiv ? `${WARN}55` : (drueber ? `${AKZENT}33` : 'transparent')}
                stroke={aktiv ? WARN : (drueber ? AKZENT : '#3a4354')}
                strokeWidth={aktiv || drueber ? 1.6 : 0.8}
                strokeDasharray={aktiv || drueber ? 'none' : '2 2'}
              />
            ))
          })}
        </svg>

        <div className="pt-1 min-w-0">
          <p className="text-[10px] font-mono tracking-widest text-[var(--text-secondary)] mb-1">
            BETROFFENE STELLE
          </p>
          <p className="font-bold text-sm" style={{
            fontFamily: 'Barlow Condensed, sans-serif',
            color: value ? WARN : 'var(--text-muted)',
            letterSpacing: '.02em',
          }}>
            {angezeigt ? angezeigt.label.toUpperCase() : 'NICHTS GEWÄHLT'}
          </p>
          {value && (
            <button type="button" onClick={() => onChange(null)}
                    className="mt-2 text-[10px] font-mono text-[var(--text-muted)] hover:text-[#e8eaf0]">
              Auswahl aufheben
            </button>
          )}
          <p className="mt-3 text-[11px] font-mono leading-relaxed text-[var(--text-muted)]">
            Auf die Stelle klicken. Danach schont der Plan die betroffene
            Disziplin und legt den Umfang auf die anderen um — ein Schienbein
            ändert das Laufen, nicht das Radfahren.
          </p>
          {value === 'kopf' && (
            <p className="mt-2 text-[11px] font-mono leading-relaxed" style={{ color: '#ef4444' }}>
              Bei Kopfverletzungen wird das Training vollständig ausgesetzt, bis
              du Beschwerdefreiheit meldest — im Wasser besteht zusätzlich
              Ertrinkungsgefahr.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
