/** Phasennamen auf ihre Familie abbilden.
 *
 *  Das Backend liefert je Saisonlage verschiedene Schreibweisen für dieselbe
 *  Phase: „Grundlage", „Vorbereitung auf den Aufbau", „Base 1", „Build 2",
 *  „Off Season · Formerhalt", „Race Week". Wer darauf mit `startsWith` prüft,
 *  übersieht die Hälfte — „Vorbereitung auf den Aufbau" beginnt mit keinem
 *  bekannten Schlüssel und fiel bisher durch.
 *
 *  Dieselbe Abbildung macht das Backend in `core/race_types.phase_family`.
 *  Hier doppelt, weil der Browser sie für die Anzeige braucht und ein
 *  zusätzlicher Endpunkt dafür zu viel wäre — die Liste ist kurz und ändert
 *  sich mit den Phasen, nicht mit den Daten.
 */

export const FAMILIEN = [
  'grundlage', 'base', 'build', 'peak', 'taper', 'benchmark', 'race', 'off',
]

/** Enthält-Prüfungen, Reihenfolge entscheidet: Spezifisches zuerst. */
const MUSTER = [
  ['off', ['off season', 'offseason', 'formerhalt', 'übergang']],
  ['race', ['race week', 'wettkampfwoche', 'rennwoche']],
  ['benchmark', ['benchmark', 'testwoche']],
  // „Vorbereitung auf den Aufbau" ist die Grundlage kurz vor dem Start — das
  // Backend nennt sie so, und sie beginnt mit keinem der Schlüsselwörter.
  ['grundlage', ['grundlage', 'vorbereitung auf den aufbau']],
  ['taper', ['taper']],
  ['peak', ['peak']],
  ['build', ['build', 'aufbau']],
  ['base', ['base']],
]

export function phaseFamilie(phase) {
  const name = (phase || '').toLowerCase().trim()
  if (!name) return null
  for (const [familie, worte] of MUSTER) {
    if (worte.some(w => name.includes(w))) return familie
  }
  return null
}

/** Lesbarer Name der Familie, für Etiketten. */
export const FAMILIE_LABEL = {
  grundlage: 'Grundlage',
  base: 'Base',
  build: 'Aufbau',
  peak: 'Peak',
  taper: 'Taper',
  benchmark: 'Testwoche',
  race: 'Wettkampfwoche',
  off: 'Off Season',
}
