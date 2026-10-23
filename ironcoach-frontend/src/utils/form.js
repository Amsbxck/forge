/** Formzonen (TSB) — eine Quelle für Kachel, Diagramm und Form-Band.
 *
 *  Die Schwellen standen bisher zweimal in `PerformanceChart.jsx`: einmal in
 *  `formLabel`, einmal in `formColor`, mit verschiedenen Stufen. Das neue
 *  Form-Band zeichnet die Zonen als Streifen und brauchte sie ein drittes
 *  Mal. Hier stehen sie einmal; Text und Farbe werden daraus abgeleitet.
 *
 *  `de` für die Kachel im Dashboard (bleibt wie sie war), `en` für die
 *  Anzeige-Leisten, die englisch beschriftet sind.
 */

// Von oben nach unten: Eine Form gehört zur ersten Zone, deren `ab` sie
// erreicht. „Frisch" und „Optimal" sind beide grün — frisch zu sein ist kein
// Warnzeichen, nur kein Training gerade.
export const FORM_ZONEN = [
  { ab: 5, de: 'Frisch', en: 'FRESH', farbe: '#22c55e' },
  { ab: -10, de: 'Optimal', en: 'OPTIMAL', farbe: '#22c55e' },
  { ab: -20, de: 'Ermüdet', en: 'TIRED', farbe: '#eab308' },
  { ab: -Infinity, de: 'Überlastet', en: 'OVERREACHED', farbe: '#ef4444' },
]

export function formZone(tsb) {
  if (tsb == null || Number.isNaN(tsb)) return null
  return FORM_ZONEN.find(z => tsb >= z.ab)
}

/** Wie die Form zu lesen ist. Positiv heißt frisch, stark negativ heißt, dass
 *  die Ermüdung die Fitness überholt hat. */
export function formLabel(tsb) {
  return formZone(tsb)?.de ?? '—'
}

export function formColor(tsb) {
  return formZone(tsb)?.farbe ?? '#8a909e'
}
