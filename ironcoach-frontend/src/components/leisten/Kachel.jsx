/** Gemeinsame Bausteine für das Design des Dashboards — für alle Seiten.
 *
 *  Das Dashboard bekam Kachel für Kachel ein neues Kleid (THIS WEEK,
 *  BREAKDOWN, PERFORMANCE, TODAY): ein Kopf in gesperrter Mono-Schrift,
 *  kleine Unterzeilen über großen Barlow-Zahlen, Tönung in der Farbe der
 *  Sache statt farbiger Randstriche. Die übrigen Seiten hatten jede ihre
 *  eigene Kopie von `CARD` und `LABEL`, mit eigenen Größen, dazu farbige
 *  Streifen links und Kartentitel in Barlow. Damit nicht jede Seite das neue
 *  Kleid wieder ein wenig anders nachschneidert, kommt es von hier.
 */

export const DISPLAY = { fontFamily: 'Barlow Condensed, sans-serif' }

export const CARD = 'bg-[#111318] border border-[#1e2228] rounded-xl'
/** Kopf einer Kachel: THIS WEEK, BREAKDOWN … */
export const TITEL = 'text-xs font-mono tracking-[0.25em] text-[var(--text-secondary)]'
/** Unterzeile über einer Zahl oder einem Abschnitt in der Kachel. */
export const KOPF = 'text-[9px] font-mono tracking-[0.2em] text-[var(--text-muted)]'
/** Rechts im Kopf: Zeitraum, Stand, kleine Verweise. */
export const NEBEN = 'text-[10px] font-mono tracking-widest text-[var(--text-muted)]'

/** Hintergrund und Rand einer getönten Kachel — wie THIS WEEK und TODAY:
 *  die Farbe der Sache als Verlauf von links oben, der Rand im selben Ton.
 *  Ersetzt die farbigen Streifen am linken Rand. */
export function toenung(farbe, staerke = 1) {
  if (!farbe) return { background: '#111318', borderColor: '#1e2228' }
  const a = n => Math.round(n * staerke).toString(16).padStart(2, '0')
  return {
    background: `linear-gradient(115deg, ${farbe}${a(0x17)} 0%, ${farbe}${a(0x08)} 45%, transparent 75%), #111318`,
    borderColor: `${farbe}2a`,
  }
}

/** Eine Kachel mit Kopf. `titel` links, `rechts` daneben, `farbe` tönt sie. */
export function Kachel({ titel, rechts, farbe, staerke, className = '', innen = 'p-5', style, children, ...rest }) {
  return (
    <div className={`${CARD} ${innen} relative ${className}`} style={{ ...toenung(farbe, staerke), ...style }} {...rest}>
      {(titel || rechts) && (
        <div className="flex items-baseline justify-between gap-3 flex-wrap mb-4">
          {typeof titel === 'string' ? <span className={TITEL}>{titel}</span> : titel}
          {rechts && (typeof rechts === 'string' ? <span className={NEBEN}>{rechts}</span> : rechts)}
        </div>
      )}
      {children}
    </div>
  )
}

/** Seitenkopf wie DASHBOARD: Barlow groß, rechts frei für Datum oder Knöpfe. */
export function SeitenKopf({ titel, zusatz, rechts, children }) {
  return (
    <div className="flex items-end justify-between gap-4 flex-wrap">
      <div className="flex items-baseline gap-3 flex-wrap min-w-0">
        <h1 className="text-3xl font-black tracking-tight text-[#e8eaf0]" style={DISPLAY}>{titel}</h1>
        {zusatz && <span className={NEBEN}>{zusatz}</span>}
        {children}
      </div>
      {rechts}
    </div>
  )
}

/** Eine große Zahl mit Einheit und Unterzeile darüber. */
export function Zahl({ name, wert, einheit, farbe = '#f2f4f8', groesse = 'text-4xl', unten, className = '' }) {
  return (
    <div className={className}>
      {name && <div className={KOPF}>{name}</div>}
      <div className="flex items-baseline gap-1 mt-1.5">
        <span className={`${groesse} font-black leading-none tabular-nums`} style={{ ...DISPLAY, color: farbe }}>{wert}</span>
        {einheit && <span className="text-xs font-mono text-[var(--text-muted)]">{einheit}</span>}
      </div>
      {unten && <div className="text-[9px] font-mono tracking-widest text-[var(--text-muted)] mt-1.5">{unten}</div>}
    </div>
  )
}

/** Umschalter wie 6W/3M/6M/1Y der Performance-Kachel. Mit `farbe` je
 *  Option leuchtet die gewählte in ihrer Farbe (Sportarten im Verlauf),
 *  sonst neutral weiß. */
export function Schalter({ optionen, wert, onWahl, className = '' }) {
  return (
    <div className={`flex flex-wrap rounded-lg p-0.5 gap-0.5 ${className}`} style={{ background: '#0d0f14', border: '1px solid #1e2228' }}>
      {optionen.map(o => {
        const an = wert === o.wert
        const f = o.farbe || '#e8eaf0'
        return (
          <button
            key={o.wert}
            type="button"
            onClick={() => onWahl(o.wert)}
            className="px-2.5 py-1 rounded-md text-[10px] font-mono tracking-widest transition-colors flex items-center gap-1.5"
            style={{
              color: an ? f : o.farbe ? `${o.farbe}b3` : '#8a909e',
              background: an ? (o.farbe ? `${f}1f` : '#ffffff14') : 'transparent',
              boxShadow: an ? `inset 0 0 0 1px ${o.farbe ? `${f}55` : '#ffffff26'}` : 'none',
            }}
          >
            {o.icon}
            {o.label}
          </button>
        )
      })}
    </div>
  )
}

/** Knöpfe in drei Arten. `haupt` ist die eine Handlung der Kachel (Cyan),
 *  `leise` alles daneben, `gefahr` Löschen und Trennen. Mit `farbe` nimmt
 *  der Hauptknopf die Farbe der Sache an (Strava-Orange). */
export function knopfStil(art = 'leise', farbe) {
  if (art === 'haupt') {
    const f = farbe || '#00d4ff'
    return { background: `${f}1f`, border: `1px solid ${f}55`, color: f }
  }
  if (art === 'gefahr') return { background: '#ef444414', border: '1px solid #ef444440', color: '#f87171' }
  return { background: 'transparent', border: '1px solid #1e2228', color: '#a7aebd' }
}

export function Knopf({ art = 'leise', farbe, className = '', children, ...rest }) {
  return (
    <button
      type="button"
      className={`px-3 py-1.5 rounded-lg text-[10px] font-mono font-semibold tracking-widest transition-colors hover:brightness-125 disabled:opacity-50 disabled:cursor-not-allowed ${className}`}
      style={knopfStil(art, farbe)}
      {...rest}
    >
      {children}
    </button>
  )
}

/** Stand einer Verbindung oder Sache: Punkt und Text in einer Zeile. */
export function Stand({ farbe = '#22c55e', children }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[10px] font-mono tracking-widest" style={{ color: farbe }}>
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: farbe, boxShadow: `0 0 6px ${farbe}88` }} />
      {children}
    </span>
  )
}
