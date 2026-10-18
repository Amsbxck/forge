/** Fehlermeldung aus einer API-Antwort — immer als Text.
 *
 *  FastAPI liefert `detail` mal als Text, mal als Liste von Prüffehlern
 *  (`[{loc, msg, type}]`), mal als Objekt. Direkt gerendert warf eine Liste
 *  einen React-Fehler, und ohne Fehlergrenze verschwand die ganze App — so
 *  geschehen im Einstiegsdialog bei einer Kommazahl im Pulsfeld.
 */
const FELDNAMEN = {
  max_hr: 'Maximalpuls', threshold_hr: 'Schwellenpuls', ftp_watts: 'FTP',
  threshold_pace_s_per_km: 'Schwellenpace', css_pace_s_per_100m: 'CSS',
  swim_threshold_hr: 'Schwellenpuls Schwimmen',
}

export function fehlerText(err, fallback = 'Das hat nicht geklappt.') {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length) {
    return detail.map(d => {
      const feld = Array.isArray(d?.loc) ? d.loc[d.loc.length - 1] : null
      const name = FELDNAMEN[feld] || feld
      return name ? `${name}: ${d?.msg || 'ungültig'}` : (d?.msg || 'ungültig')
    }).join(' · ')
  }
  if (detail && typeof detail === 'object') return detail.message || fallback
  if (!err?.response) return 'Keine Verbindung zum Server.'
  return fallback
}
