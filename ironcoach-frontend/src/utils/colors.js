/** Die Farbfamilien der Anwendung — eine Quelle für alle Ansichten.
 *
 *  Vorher lag dieselbe Zuordnung in fünf Dateien nebeneinander und driftete
 *  auseinander. Wichtiger als die Dopplung ist aber die Trennung dahinter:
 *
 *  **Ampelfarben bedeuten eine Bewertung.** Grün, Gelb, Orange und Rot sagen
 *  „gut / achtung / schlecht" — Gesundheitszustand, HRV, Herzfrequenzzonen,
 *  Form. Sie sind für Aussagen reserviert.
 *
 *  **Disziplinen bewerten nichts.** Laufen ist nicht schlechter als Radfahren.
 *  Deshalb liegen die Sportarten in einer eigenen Familie aus Blau, Violett
 *  und Pink. Vorher war Laufen rot wie „krank", Schwimmen gelb wie eine HRV-
 *  Warnung und Kraft grün wie „gesund" — dieselbe Farbe hieß je nach Kachel
 *  etwas anderes.
 */

// --- Disziplinen: keine Wertung, nur Unterscheidung ---------------------------
export const DISCIPLINE_COLOR = {
  swim: '#38bdf8',        // Himmelblau — Wasser
  bike: '#a855f7',        // Violett
  run: '#ec4899',         // Pink
  brick: '#d946ef',       // Fuchsia — liegt zwischen Rad und Lauf, wie die Einheit selbst
  gym: '#94a3b8',         // Schiefer — unterstützend, nicht im Wettkampf
  hike: '#a1a1aa',        // Zink
  rest: '#3a3f4a',        // neutral
  transition: '#64748b',  // Wechselzone
  other: '#64748b',       // alles, was die App nicht plant
}

export const DISCIPLINE_LABEL = {
  swim: 'Swimming',
  bike: 'Cycling',
  run: 'Running',
  brick: 'Brick',
  gym: 'Gym',
  hike: 'Hiking',
  rest: 'Rest',
  other: 'Sonstiges',
}

export function disciplineColor(discipline) {
  return DISCIPLINE_COLOR[(discipline || '').toLowerCase()] || DISCIPLINE_COLOR.other
}

/** Anzeigename einer Einheit.
 *
 *  Für Sportarten außerhalb der geplanten Disziplinen steht die
 *  Originalbezeichnung in `sport_type` — „StairStepper" statt „Sonstiges".
 *  Sie kommt von Strava in CamelCase und wird hier lesbar gemacht.
 */
export function disciplineLabel(discipline, sportType) {
  const key = (discipline || '').toLowerCase()
  if (key !== 'other' && DISCIPLINE_LABEL[key]) return DISCIPLINE_LABEL[key]
  if (sportType) {
    return sportType
      .replace(/[_-]+/g, ' ')
      .replace(/([a-z])([A-Z])/g, '$1 $2')
      .replace(/\b\w/g, c => c.toUpperCase())
      .trim()
  }
  return DISCIPLINE_LABEL[key] || discipline || 'Sonstiges'
}

// --- Bewertung: Ampel --------------------------------------------------------
export const STATUS_COLOR = {
  green: '#22c55e',
  yellow: '#eab308',
  red: '#ef4444',
}

export const HEALTH_COLOR = {
  healthy: '#22c55e',
  sick: '#ef4444',
  injured: '#f59e0b',
  returning: '#f59e0b',
}

/** Herzfrequenzzonen Z1–Z5. Eigene Skala, weil sie eine Intensität abbildet
 *  und keine Sportart — Z1 bleibt blau, damit „locker" nicht grün wie
 *  „gesund" aussieht. */
export const HR_ZONE_COLOR = ['#3b82f6', '#22c55e', '#eab308', '#f97316', '#ef4444']
export const HR_ZONE_LABEL = ['Z1', 'Z2', 'Z3', 'Z4', 'Z5']

export const ACCENT = '#00d4ff'
