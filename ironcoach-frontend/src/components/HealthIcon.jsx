/** Zustandssymbole: Herz, Totenkopf, gebrochenes Herz.
 *
 *  Selbst gezeichnet statt aus einer Icon-Bibliothek: drei Symbole
 *  rechtfertigen kein weiteres Paket, und so lässt sich der Herzschlag
 *  direkt ins SVG legen.
 *
 *  `hole` ist die Farbe der Aussparungen (Augen, Nase, Riss). Sie muss der
 *  Kartenfarbe entsprechen, sonst wirken die Löcher wie Flecken.
 *
 *  ## Warum die Zeichenfläche viel größer ist als die Form
 *
 *  `drop-shadow` wird am Rand der Zeichenfläche abgeschnitten — sichtbar als
 *  eckiger Kasten hinter dem Symbol statt eines Scheins, der der Silhouette
 *  folgt. Weder `overflow: visible` noch der Filter am umgebenden Element
 *  ändern daran etwas; beschnitten wird trotzdem.
 *
 *  Deshalb steht die 24er-Form in einer 42er-Fläche. Damit das Layout davon
 *  nichts merkt, wird das Element entsprechend größer gezeichnet und der
 *  Überstand per negativem Rand herausgerechnet: die Form ist genau `size`
 *  groß, der Schein darf darüber hinausreichen.
 */

const PAD = 9                    // Einheiten Rand rings um die Form
const BOX = 24 + 2 * PAD         // Kantenlänge der Zeichenfläche
const VIEW = `${-PAD} ${-PAD} ${BOX} ${BOX}`

function svgProps(size, color, extra = {}) {
  const gezeichnet = (size * BOX) / 24
  const ueberstand = (gezeichnet - size) / 2
  return {
    width: gezeichnet,
    height: gezeichnet,
    viewBox: VIEW,
    fill: 'none',
    style: {
      margin: `-${ueberstand}px`,
      filter: `drop-shadow(0 0 4px ${color}aa) drop-shadow(0 0 9px ${color}55)`,
      ...extra,
    },
  }
}

const HERZ_PFAD =
  'M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09' +
  'C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z'

function Heart({ size, color, beat }) {
  return (
    <svg {...svgProps(size, color, beat ? { animation: 'herzschlag 1.6s ease-in-out infinite' } : {})}>
      <path d={HERZ_PFAD} fill={color} />
    </svg>
  )
}

function HeartCrack({ size, color, hole }) {
  return (
    <svg {...svgProps(size, color)}>
      <path d={HERZ_PFAD} fill={color} />
      {/* Der Riss läuft in Kartenfarbe durch das Herz — dadurch sieht es
          gebrochen aus, ohne zwei Hälften positionieren zu müssen. */}
      <path
        d="M12 4.8 10.2 9.2l3 2.2-2.6 3.6 2 2.4"
        stroke={hole} strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round"
        fill="none"
      />
    </svg>
  )
}

function Skull({ size, color, hole }) {
  return (
    <svg {...svgProps(size, color)}>
      {/* Schädel und Kiefer als zwei Formen — zusammen ergibt das die
          typische Silhouette, ohne einen fehleranfälligen Pfad. */}
      <circle cx="12" cy="10" r="8" fill={color} />
      <rect x="8.2" y="15.5" width="7.6" height="6" rx="1.6" fill={color} />
      <circle cx="8.8" cy="10.2" r="2.6" fill={hole} />
      <circle cx="15.2" cy="10.2" r="2.6" fill={hole} />
      <path d="M12 13.2l1.5 2.4h-3z" fill={hole} />
      {/* Zähne */}
      <path d="M10.2 18v3.4M12 18v3.4M13.8 18v3.4"
            stroke={hole} strokeWidth="1" strokeLinecap="round" />
    </svg>
  )
}

export default function HealthIcon({ status, kind, size = 28, color, hole = '#111318' }) {
  // Eine Verletzung ist kein Infekt: dafür das gebrochene Herz, auch
  // während des Wiedereinstiegs.
  if (kind === 'injury' && status !== 'healthy') {
    return <HeartCrack size={size} color={color} hole={hole} />
  }
  if (status === 'sick') return <Skull size={size} color={color} hole={hole} />
  return <Heart size={size} color={color} beat={status === 'healthy'} />
}
