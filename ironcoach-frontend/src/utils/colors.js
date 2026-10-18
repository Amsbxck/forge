import { phaseFamilie } from './phasen'
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

/** Trainingsbereiche nach **Zonennummer**, 1 bis 7.
 *
 *  Z1–Z5 sind die Pulsskala oben. Z6 (vVO2max) und Z7 (Steigerungen) gibt es
 *  nur beim Laufen und setzen die Rampe nach oben fort: dunkler werdendes
 *  Rot. Nicht Fuchsia, Violett oder Pink — die tragen schon Brick, Rad und
 *  Lauf, und eine Zone in Sportartfarbe läse sich als Sportart.
 *
 *  Eigene Tabelle statt `HR_ZONE_COLOR` zu verlängern: `HRZoneChart`
 *  zeichnet über dessen Länge, und zwei angehängte Einträge erschienen dort
 *  als Pulszonen, die es nicht gibt.
 *
 *  Nach Nummer, nicht nach Zeilenposition: Beim Laufen ist Z2 in zwei Zeilen
 *  geteilt, und die zweite bekäme nach Position die Farbe von Z3.
 */
export const ZONE_COLOR = {
  1: HR_ZONE_COLOR[0],
  2: HR_ZONE_COLOR[1],
  3: HR_ZONE_COLOR[2],
  4: HR_ZONE_COLOR[3],
  5: HR_ZONE_COLOR[4],
  6: '#be123c',
  7: '#881337',
}

/** Die vier Intensitätsstufen — eine Tabelle für Wochenplan und Verlauf.
 *
 *  Vorher hielten beide eine eigene Kopie mit eigenen Farben (Grün-Orange-Rot
 *  aus einer anderen Palette), und der Kalender färbte Z6/Z7 Fuchsia und
 *  Violett — Farben, die hier ausdrücklich den Sportarten gehören. Die Stufen
 *  folgen jetzt der Zonenskala oben.
 */
export const INTENSITY_META = {
  base:       { label: 'Grundlage',       short: 'GRUNDLAGE', zone: 'Z1–Z2', color: ZONE_COLOR[2] },
  sweet_spot: { label: 'Sweet Spot / Tempo', short: 'SWEETSPOT', zone: 'Z3', color: ZONE_COLOR[3] },
  threshold:  { label: 'Schwelle',        short: 'SCHWELLE',  zone: 'Z4',    color: ZONE_COLOR[4] },
  vo2max:     { label: 'VO₂max',          short: 'VO₂MAX',    zone: 'Z5+',   color: ZONE_COLOR[5] },
}

/** Farbe einer Zielzone wie „Z3" oder „Z6". */
export const zoneColor = (hrZone) => ZONE_COLOR[parseInt(String(hrZone || '').replace(/\D/g, ''), 10)]

export const ACCENT = '#00d4ff'

// --- Erledigt ----------------------------------------------------------------
/** Ein absolvierter Tag im Wochenplan.
 *
 *  Bewusst **nicht** das Grün der Zonenskala (`#22c55e` = Z2): Das steht für
 *  eine Intensität und färbt in der Grundlagenphase auch die Phasenmarke. Eine
 *  Karte mit grünem Grund und grüner Intensitätsleiste wäre nicht mehr zu
 *  lesen — man wüsste nicht, ob das Grün „Z2" oder „gemacht" heißt.
 *
 *  Dieses Grün zieht ins Smaragd, liegt damit neben der Skala statt darauf.
 *  Und es trägt die Aussage nicht allein: Die Karte bekommt zusätzlich ein
 *  Häkchen. Wer Farben schlecht unterscheidet, liest es trotzdem.
 */
export const DONE_COLOR = '#10b981'

// --- Trainingsphasen ---------------------------------------------------------
/** Farbe einer Trainingsphase, abgeleitet aus der Zonenskala.
 *
 *  Die Phase sagt, in welcher Intensität die Woche überwiegend liegt — also
 *  dasselbe, was die Zonenskala abbildet. Deshalb wird sie hier nicht neu
 *  erfunden, sondern aus `HR_ZONE_COLOR` genommen: Wer die Zonenfarben aus
 *  dem Profil kennt, liest die Phase ohne Legende.
 *
 *  Bewusst nicht aus der Disziplinenfamilie (Blau/Violett/Pink): Die steht
 *  für Sportarten und bewertet nichts. Eine Phase dagegen beschreibt eine
 *  Intensität — sie gehört auf die Skala, nicht daneben.
 */
const [Z1, Z2, Z3, Z4, Z5] = HR_ZONE_COLOR

export const PHASE_COLOR = {
  grundlage: Z2,    // Grundlagenumfang, überwiegend Z2
  base: Z2,
  build: Z3,        // mehr Tempo: Z3, gelegentlich Z4
  peak: Z5,         // VO2max-Arbeit
  taper: Z1,        // aktive Erholung, Umfang zurück
  benchmark: Z4,    // harte Tests, aber kein Peak-Block
  race: ACCENT,     // die Woche, auf die alles hinausläuft
  off: '#79808f',   // Saison vorbei — gedämpft, keine Intensität
}

/** Phase auf ihre Farbe abbilden.
 *
 *  Die Namen tragen Nummern ("Base 1", "Peak 3") und mal Deutsch, mal
 *  Englisch ("Grundlage", "Race Week"). Verglichen wird deshalb der Anfang
 *  in Kleinschreibung, nicht der ganze Name.
 */
export function phaseColor(phase) {
  const name = (phase || '').toLowerCase().trim()
  if (!name) return 'var(--text-muted)'
  // Über `phaseFamilie`, nicht über `startsWith`: Das Backend nennt die
  // Grundlage kurz vor dem Aufbaustart "Vorbereitung auf den Aufbau", und die
  // beginnt mit keinem der Schlüsselwörter — sie fiel durch und wurde cyan
  // statt grün.
  const familie = phaseFamilie(name)
  return familie ? PHASE_COLOR[familie] : ACCENT
}
