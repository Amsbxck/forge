/** Ein Datum ohne Uhrzeit ("2026-09-21") als lokalen Tag lesen.
 *
 *  `new Date("2026-09-21")` ist nicht der 21. September. Die Sprache liest
 *  eine reine Datumsangabe als **UTC**-Mitternacht — wer westlich von
 *  Greenwich sitzt, bekommt daraus den 20. September, 17 Uhr. Jede Anzeige,
 *  die daraus wieder ein Datum macht, zeigt dann den Vortag.
 *
 *  Genau das ist passiert: Das Backend erlaubte die Testwoche ab dem 21.,
 *  die Oberfläche schrieb „frühestens ab dem 20.". Ein Tag Unterschied, in
 *  einer Angabe, nach der sich jemand richtet.
 *
 *  Mit angehängter Uhrzeit liest dieselbe Funktion **lokale** Mitternacht —
 *  und ein Datum ohne Uhrzeit meint immer den Tag dort, wo der Athlet ist.
 */
export function parseTag(dateStr) {
  if (!dateStr) return null
  const nurDatum = /^\d{4}-\d{2}-\d{2}$/.test(dateStr)
  return new Date(nurDatum ? `${dateStr}T00:00:00` : dateStr)
}

/** Datum für die Anzeige, ohne Verschiebung um einen Tag. */
export function formatTag(dateStr, locale = 'de-DE') {
  const tag = parseTag(dateStr)
  return tag ? tag.toLocaleDateString(locale) : ''
}

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
  const ziel = parseTag(dateStr)
  if (!ziel) return null
  ziel.setHours(0, 0, 0, 0)
  const heute = new Date()
  heute.setHours(0, 0, 0, 0)
  return Math.round((ziel - heute) / 86400000)
}

/** Montag und Sonntag der Woche, in der `tag` liegt — als ISO-Datum.
 *
 *  Das Gegenstück zu `kalenderwoche` im Backend. "Diese Woche" ist eine
 *  Kalenderwoche, keine Planwoche: Über die Planwochennummer gefiltert
 *  fielen für jeden Athleten, dessen Aufbau noch nicht begonnen hat,
 *  sämtliche jemals absolvierten Einheiten in die laufende Woche.
 *
 *  Rückgabe als Zeichenkette, weil `session_date` aus der API ebenfalls
 *  "JJJJ-MM-TT" ist — in diesem Format ist ein Zeichenkettenvergleich
 *  gleichbedeutend mit einem Datumsvergleich, und es entsteht keine
 *  Zeitzonenfrage.
 */
export function kalenderwoche(tag = new Date()) {
  const montag = new Date(tag)
  montag.setHours(0, 0, 0, 0)
  // getDay(): 0 = Sonntag. Wir zählen Montag als Wochenanfang.
  const versatz = montag.getDay() === 0 ? 6 : montag.getDay() - 1
  montag.setDate(montag.getDate() - versatz)
  const sonntag = new Date(montag)
  sonntag.setDate(montag.getDate() + 6)
  return { von: isoTag(montag), bis: isoTag(sonntag) }
}

/** Lokales Datum als "JJJJ-MM-TT", ohne Umweg über UTC. */
export function isoTag(d) {
  const z = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}`
}
