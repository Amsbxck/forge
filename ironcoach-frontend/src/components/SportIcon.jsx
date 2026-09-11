/** Disziplinsymbole als Strichzeichnung.
 *
 *  Vorher standen hier Emojis. Die sehen auf jedem Betriebssystem anders aus,
 *  bringen ihre eigene Farbe mit — 🚴 ist blau, egal welche Farbe die Kachel
 *  hat — und lassen sich nicht in der Größe kontrollieren. Selbst gezeichnet
 *  folgen sie der Disziplinfarbe und passen zum übrigen Strichstil.
 *
 *  Bewusst reduziert: bei 14 px zählt die Silhouette, nicht das Detail.
 */

const STROKE = {
  fill: 'none',
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
}

const PATHS = {
  swim: (
    <>
      {/* Kopf, Arm im Zug, zwei Wasserlinien */}
      <circle cx="8" cy="6.5" r="2" />
      <path d="M4.5 12.5 13 10.5 17.5 5.5" />
      <path d="M2 16.5c1.8-1.4 3.6-1.4 5.5 0s3.7 1.4 5.5 0 3.7-1.4 5.5 0" />
      <path d="M2 20.5c1.8-1.4 3.6-1.4 5.5 0s3.7 1.4 5.5 0 3.7-1.4 5.5 0" />
    </>
  ),
  bike: (
    <>
      <circle cx="5.5" cy="17" r="3.8" />
      <circle cx="18.5" cy="17" r="3.8" />
      <path d="M5.5 17 10 8.5h6" />
      <path d="M10 8.5 18.5 17" />
      <path d="M14.5 6h3" />
    </>
  ),
  run: (
    <>
      <circle cx="14.5" cy="4.5" r="2" />
      {/* Rumpf mit Vorlage, angehobenes Vorderbein, gestrecktes Standbein */}
      <path d="M13 8 10 13" />
      <path d="M10 13 14 14.5 13.5 19.5" />
      <path d="M10 13 6.5 15.5 4.5 19.5" />
      <path d="M13 8 16.5 10.5 15.5 13.5" />
      <path d="M13 8 9.5 9.5" />
    </>
  ),
  gym: (
    <>
      {/* Hantel: Stange, zwei Scheiben, zwei Kappen */}
      <path d="M8.5 12h7" />
      <rect x="5" y="8.5" width="3.5" height="7" rx="1.2" />
      <rect x="15.5" y="8.5" width="3.5" height="7" rx="1.2" />
      <path d="M3 10.5v3M21 10.5v3" />
    </>
  ),
  brick: (
    <>
      {/* Rad, dann weiter zu Fuß — der Pfeil ist die Kopplung */}
      <circle cx="5.5" cy="15" r="3.5" />
      <path d="M11 15h7" />
      <path d="M15.5 11.5 19 15l-3.5 3.5" />
    </>
  ),
  hike: <path d="M2 19.5 9 7.5l3.5 6 2.5-3.5 7 9.5z" />,
  // Auffangsymbol für alles, was die App nicht plant: eine Pulslinie.
  // Ohne es wäre eine StairMaster-Einheit in der Liste symbollos und
  // dadurch schwerer zu erfassen als jede andere.
  other: <path d="M2 12h4l2.5-6 4 12L15 12h7" />,
  rest: <path d="M20.5 14.8A8.5 8.5 0 1 1 9.2 3.5a6.6 6.6 0 0 0 11.3 11.3z" />,
}

export default function SportIcon({ discipline, size = 16, color = 'currentColor', className = '' }) {
  const key = (discipline || '').toLowerCase()
  const pfad = PATHS[key] || PATHS.other

  // Bei größeren Symbolen wirkt eine gleich dicke Linie schwer — deshalb
  // wächst die Stärke unterproportional mit.
  const staerke = size >= 28 ? 1.5 : size >= 20 ? 1.7 : 1.9

  return (
    <svg
      width={size} height={size} viewBox="0 0 24 24"
      className={className}
      style={{ ...STROKE, stroke: color, flexShrink: 0 }}
      strokeWidth={staerke}
      aria-hidden="true"
    >
      {pfad}
    </svg>
  )
}
