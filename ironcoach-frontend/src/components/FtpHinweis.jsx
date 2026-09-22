/**
 * Hinweis, wenn eine normale Fahrt die hinterlegte FTP in Frage stellt.
 *
 * Bewusst nur ein Hinweis: Die FTP wird nie automatisch geändert. Ein
 * einzelner harter Anstieg oder ein Gruppenantritt zöge den Wert nach oben,
 * und danach wäre jede Wattvorgabe der Folgemonate zu hart. Hier steht
 * deshalb der Beleg mit Datum und Zahlen — entscheiden muss der Athlet.
 *
 * `kompakt` für die Stelle im Profil, wo der Wert ohnehin schon steht.
 */
export default function FtpHinweis({ befund, kompakt = false, onTestwoche }) {
  if (!befund) return null

  if (kompakt) {
    return (
      <p className="text-[10px] font-mono leading-relaxed mt-2" style={{ color: '#f59e0b' }}>
        {befund.text} Deine Wattvorgaben sind damit womöglich zu niedrig.
      </p>
    )
  }

  return (
    <div
      className="rounded-xl p-4 flex items-start gap-3 flex-wrap"
      style={{ background: '#111318', border: '1px solid #1e2228', borderLeft: '3px solid #f59e0b' }}
    >
      <div className="min-w-0 flex-1">
        <div className="text-sm font-bold text-[#e8eaf0]">Deine FTP könnte überholt sein</div>
        <p className="text-[13px] text-[var(--text-secondary)] mt-1 leading-relaxed">
          {befund.text}
        </p>
        <p className="text-[12px] text-[var(--text-muted)] mt-2 leading-relaxed">
          Geändert wird nichts — aus einer normalen Fahrt lässt sich keine Schwelle
          ablesen. Wenn die Form stimmt, bestätigt das eine Testwoche.
        </p>
      </div>
      {onTestwoche && (
        <button
          onClick={onTestwoche}
          className="px-3 py-1.5 rounded-lg text-[12px] font-mono tracking-wide flex-shrink-0"
          style={{ background: '#f59e0b20', border: '1px solid #f59e0b44', color: '#f59e0b' }}
        >
          ZUR TESTWOCHE
        </button>
      )}
    </div>
  )
}
