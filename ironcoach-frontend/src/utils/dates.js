/** Tage bis zu einem Datum; negativ, wenn es vorbei ist.
 *
 *  Eine Fassung für alle Seiten. Vorher rechnete jede Seite selbst: das
 *  Dashboard mit `Math.ceil` ab dem aktuellen Zeitpunkt, das Profil mit
 *  `Math.round` ab Mitternacht. Dasselbe Rennen stand dadurch je nach Seite
 *  mit 8 oder 9 Tagen da.
 *
 *  Gezählt wird von Mitternacht: „in 1 Tag" heißt morgen, unabhängig davon,
 *  ob es gerade früh oder spät am Abend ist.
 */
export function daysUntil(dateStr) {
  if (!dateStr) return null
  const ziel = new Date(dateStr)
  ziel.setHours(0, 0, 0, 0)
  const heute = new Date()
  heute.setHours(0, 0, 0, 0)
  return Math.round((ziel - heute) / 86400000)
}
