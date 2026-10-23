/** Summen über Einheiten — je Woche, je Tag, je Zeitraum.
 *
 *  Für die Verlauf-Seite (Wochenvolumen, Trainingsjahr, Zeitraumvergleich,
 *  Monatskopf). Alles im Browser aus den ohnehin geladenen Einheiten: Ein
 *  eigener Endpunkt würde dieselben Zahlen ein zweites Mal rechnen, und die
 *  Seite hat die zwei Jahre (`getSessionsSeit`) schon in der Hand.
 *
 *  Gelöschte Einheiten zählen nirgends mit — sie stehen im Verlauf nur auf
 *  Wunsch und ausgegraut, in einer Summe wären sie unsichtbar falsch.
 */
import { isoTag, parseTag } from './dates'

/** Reihenfolge der Sportarten in Leisten und Stapeln: wie im Plan. */
export const SPORTEN = ['swim', 'bike', 'run', 'brick', 'gym', 'hike', 'other']

export function sportVon(einheit) {
  const d = (einheit?.discipline || '').toLowerCase()
  return SPORTEN.includes(d) ? d : 'other'
}

const aktiv = sessions => (sessions || []).filter(s => !s.deleted_at && s.session_date)

/** Montag (`YYYY-MM-DD`) der Woche eines Tages. Sonntag gehört zur Woche
 *  davor — wie im Planer (`core/wochen.montag_von`). */
export function montagVon(tag) {
  const d = parseTag(typeof tag === 'string' ? tag.slice(0, 10) : isoTag(tag))
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7))
  return isoTag(d)
}

const leer = () => ({ min: 0, tss: 0, km: 0, n: 0, jeSport: {} })

function addiere(summe, s) {
  const sport = sportVon(s)
  summe.min += s.duration_min || 0
  summe.tss += s.tss || 0
  summe.km += s.distance_km || 0
  summe.n += 1
  summe.jeSport[sport] = (summe.jeSport[sport] || 0) + (s.duration_min || 0)
  return summe
}

/** `{montag: {min, tss, km, n, jeSport: {sport: min}}}` */
export function wochenSummen(sessions) {
  const ergebnis = {}
  for (const s of aktiv(sessions)) {
    const m = montagVon(s.session_date)
    ergebnis[m] = addiere(ergebnis[m] || leer(), s)
  }
  return ergebnis
}

/** `{tag: {min, tss, n, haupt}}` — `haupt` ist die Sportart mit den meisten
 *  Minuten des Tages; sie gibt der Kachel im Trainingsjahr die Farbe. */
export function tagesSummen(sessions) {
  const ergebnis = {}
  for (const s of aktiv(sessions)) {
    const t = s.session_date.slice(0, 10)
    ergebnis[t] = addiere(ergebnis[t] || leer(), s)
  }
  for (const summe of Object.values(ergebnis)) {
    summe.haupt = Object.entries(summe.jeSport).sort((a, b) => b[1] - a[1])[0]?.[0] || 'other'
  }
  return ergebnis
}

/** Summen der letzten `tage` Tage (bis heute) und der `tage` davor.
 *
 *  Für „+12 % gegenüber davor". Gezählt nach Kalendertagen, nicht nach
 *  Einheiten — dieselbe Lehre wie in der HRV History, wo „30d" lange die
 *  letzten 30 Messungen waren.
 */
export function zeitraum(sessions, tage, heute = new Date()) {
  const ende = parseTag(isoTag(heute))
  const start = new Date(ende)
  start.setDate(ende.getDate() - (tage - 1))
  const davorStart = new Date(start)
  davorStart.setDate(start.getDate() - tage)
  const [a, b, c] = [isoTag(davorStart), isoTag(start), isoTag(ende)]

  const jetzt = leer()
  const davor = leer()
  for (const s of aktiv(sessions)) {
    const t = s.session_date.slice(0, 10)
    if (t >= b && t <= c) addiere(jetzt, s)
    else if (t >= a && t < b) addiere(davor, s)
  }
  return { jetzt, davor }
}

/** Veränderung in Prozent, `null` ohne Vergleich (davor nichts trainiert). */
export function veraenderung(jetzt, davor) {
  if (!davor) return null
  return ((jetzt - davor) / davor) * 100
}

/** Stunden kurz: 8.2h, unter einer Stunde in Minuten. */
export function stunden(min) {
  if (!min) return '0h'
  return min < 60 ? `${Math.round(min)}m` : `${(min / 60).toFixed(1)}h`
}
