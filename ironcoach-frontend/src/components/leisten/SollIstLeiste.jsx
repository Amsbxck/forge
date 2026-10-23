/** Geplant gegen absolviert — eine Spur, in der das Ist das Soll füllt.
 *
 *  Vorher zeigte der Wochenplan an einem erledigten Tag nur ein Häkchen und
 *  grünen Grund. Ob aus 60 geplanten Minuten 35 oder 95 wurden, stand
 *  nirgends, obwohl das Backend die Einheit über `matched_session_id` kennt.
 *
 *  Das Soll ist der Rahmen, das Ist die Füllung darin. Was über das Soll
 *  hinausgeht, ragt schraffiert hinaus — mehr als geplant ist eine Aussage,
 *  kein Fehler der Zeichnung. `skala` setzt mehrere Leisten untereinander
 *  auf dasselbe Maß, damit 3 h Rad und 45 min Schwimmen vergleichbar bleiben;
 *  ohne sie füllt jede Leiste ihre eigene Breite.
 */
export default function SollIstLeiste({
  name, soll = 0, ist = 0, farbe, einheit = 'min', skala, kompakt = false,
}) {
  const max = Math.max(skala || 0, soll, ist, 1)
  const pct = v => `${Math.min(100, (v / max) * 100)}%`
  const ueber = ist > soll && soll > 0
  const ohnePlan = soll === 0 && ist > 0
  const fertig = soll > 0 && ist >= soll * 0.9

  const text = ohnePlan
    ? `${Math.round(ist)} ${einheit} unplanned`
    : `${Math.round(ist)} / ${Math.round(soll)} ${einheit}`

  return (
    <div className={kompakt ? '' : 'space-y-1'}>
      {!kompakt && (
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-[10px] font-mono tracking-wider" style={{ color: farbe }}>{name}</span>
          <span
            className="text-[10px] font-mono tabular-nums"
            style={{ color: fertig ? '#e8eaf0' : 'var(--text-secondary)' }}
          >
            {text}
          </span>
        </div>
      )}
      <div className={`relative ${kompakt ? 'h-1' : 'h-1.5'} rounded-full`} style={{ background: '#0a0c0f' }}>
        {/* Das Soll als Rahmen */}
        {soll > 0 && (
          <div
            className="absolute inset-y-0 left-0 rounded-full"
            style={{ width: pct(soll), boxShadow: `inset 0 0 0 1px ${farbe}55`, background: `${farbe}12` }}
          />
        )}
        {/* Das Ist bis zum Soll */}
        <div
          className="absolute inset-y-0 left-0 rounded-full transition-all duration-700 ease-out"
          style={{ width: pct(Math.min(ist, soll || ist)), background: farbe, opacity: 0.9 }}
        />
        {/* Was darüber hinausgeht */}
        {ueber && (
          <div
            className="absolute inset-y-0 rounded-r-full transition-all duration-700 ease-out"
            style={{
              left: pct(soll),
              width: `calc(${pct(ist)} - ${pct(soll)})`,
              background: farbe,
              opacity: 0.55,
              backgroundImage: 'repeating-linear-gradient(135deg, transparent 0 2px, #0a0c0f 2px 4px)',
            }}
          />
        )}
      </div>
      {kompakt && (
        <div className="mt-0.5 text-[9px] font-mono tabular-nums text-[var(--text-muted)]">{text}</div>
      )}
    </div>
  )
}
