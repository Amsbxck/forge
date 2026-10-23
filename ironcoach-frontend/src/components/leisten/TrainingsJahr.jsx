import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { DISCIPLINE_COLOR, DISCIPLINE_LABEL } from '../../utils/colors'
import { isoTag, parseTag } from '../../utils/dates'
import { stunden, tagesSummen } from '../../utils/einheiten'

/** Ein Jahr Training, ein Kästchen je Tag.
 *
 *  Gebaut wie die HRV-Heatmap (Wochen als Spalten, Montag oben), damit beide
 *  sich gleich lesen. Die Farbe ist die Hauptsportart des Tages, die
 *  Helligkeit der TSS in vier Stufen — so sieht man Regelmäßigkeit, lange
 *  Wochenenden und Lücken (Krankheit, Urlaub), ohne eine Zahl zu lesen.
 *
 *  Die Kachelgröße folgt der Breite: 53 Spalten passen auf dem Rechner ohne
 *  Scrollen; auf dem Telefon wird die Kachel nicht kleiner als 9 px, dann
 *  scrollt das Raster und steht zu Beginn auf der laufenden Woche.
 */

const WOCHEN = 53
const ABSTAND = 3
const ZELLE_MIN = 9
const ZELLE_MAX = 16
const TAGE = ['MON', '', 'WED', '', 'FRI', '', 'SUN']
// Helligkeit nach TSS: locker, mittel, hart, sehr hart.
const STUFEN = [
  { bis: 40, deckung: 0.32, name: '< 40' },
  { bis: 80, deckung: 0.55, name: '< 80' },
  { bis: 150, deckung: 0.8, name: '< 150' },
  { bis: Infinity, deckung: 1, name: '150+' },
]
const stufeVon = tss => STUFEN.find(s => (tss || 0) < s.bis)

export default function TrainingsJahr({ sessions }) {
  const [hover, setHover] = useState(null)
  const box = useRef(null)
  const [breite, setBreite] = useState(0)
  useLayoutEffect(() => {
    if (!box.current) return
    const messen = () => setBreite(box.current?.clientWidth || 0)
    messen()
    const beobachter = new ResizeObserver(messen)
    beobachter.observe(box.current)
    return () => beobachter.disconnect()
  }, [])

  const { spalten, aktiveTage, serie } = useMemo(() => {
    const jeTag = tagesSummen(sessions)
    const heute = parseTag(isoTag(new Date()))
    const montag = new Date(heute)
    montag.setDate(heute.getDate() - ((heute.getDay() + 6) % 7) - (WOCHEN - 1) * 7)

    const liste = []
    let aktiv = 0
    let laenge = 0
    let laengste = 0
    for (let w = 0; w < WOCHEN; w++) {
      const tage = []
      for (let t = 0; t < 7; t++) {
        const d = new Date(montag)
        d.setDate(montag.getDate() + w * 7 + t)
        const tag = isoTag(d)
        const zukunft = d > heute
        const summe = jeTag[tag]
        if (!zukunft) {
          if (summe) { aktiv++; laenge++; laengste = Math.max(laengste, laenge) } else laenge = 0
        }
        tage.push({ tag, zukunft, heute: tag === isoTag(heute), summe })
      }
      // Der Monat über der Spalte mit seinem ersten Montag.
      const ersterTag = parseTag(tage[0].tag)
      liste.push({
        tage,
        monat: ersterTag.getDate() <= 7 ? ersterTag.toLocaleDateString('en-GB', { month: 'short' }).toUpperCase() : '',
        jetzt: tage.some(t => t.heute),
      })
    }
    return { spalten: liste, aktiveTage: aktiv, serie: laengste }
  }, [sessions])

  const zelle = breite
    ? Math.max(ZELLE_MIN, Math.min(ZELLE_MAX, Math.floor((breite - (WOCHEN - 1) * ABSTAND) / WOCHEN)))
    : ZELLE_MIN

  // Zu Beginn an die laufende Woche: Sie ist die letzte Spalte, also ganz
  // nach rechts. Passt alles hinein, ändert das nichts.
  useLayoutEffect(() => {
    if (box.current) box.current.scrollLeft = box.current.scrollWidth
  }, [zelle, spalten])

  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 mb-3 flex-wrap">
        <span className="text-[9px] font-mono tracking-[0.2em] text-[var(--text-muted)]">TRAINING YEAR</span>
        <span className="text-[10px] font-mono tracking-widest text-[var(--text-secondary)]">
          <span className="text-[#e8eaf0] tabular-nums">{aktiveTage}</span> ACTIVE DAYS
          <span className="text-[var(--text-muted)]"> · </span>
          LONGEST STREAK <span className="text-[#e8eaf0] tabular-nums">{serie}</span>
        </span>
      </div>

      <div className="flex gap-2 items-start">
        {/* Wochentage stehen fest, nur das Raster scrollt */}
        <div className="flex flex-col shrink-0 font-mono text-[8px] text-[var(--text-muted)]"
             style={{ gap: ABSTAND, paddingTop: 14 }}>
          {TAGE.map((t, i) => (
            <div key={i} className="flex items-center" style={{ height: zelle, lineHeight: 1 }}>{t}</div>
          ))}
        </div>
        <div ref={box} className="overflow-x-auto overscroll-x-contain min-w-0 flex-1 pb-1" style={{ scrollbarWidth: 'thin' }}>
          <div className="inline-block">
            <div className="flex font-mono text-[8px] text-[var(--text-muted)] h-[14px]" style={{ gap: ABSTAND }}>
              {spalten.map((s, i) => (
                <div key={i} className="overflow-visible whitespace-nowrap" style={{ width: zelle }}>{s.monat}</div>
              ))}
            </div>
            <div className="flex" style={{ gap: ABSTAND }}>
              {spalten.map((s, i) => (
                <div key={i} className="flex flex-col" style={{ gap: ABSTAND }}>
                  {s.tage.map(t => {
                    const farbe = t.summe ? DISCIPLINE_COLOR[t.summe.haupt] || DISCIPLINE_COLOR.other : null
                    const an = hover?.tag === t.tag
                    return (
                      <div
                        key={t.tag}
                        onMouseEnter={() => setHover(t)}
                        onMouseLeave={() => setHover(null)}
                        className="rounded-[2px] transition-transform"
                        style={{
                          width: zelle,
                          height: zelle,
                          background: farbe || (t.zukunft ? '#0c0e12' : '#161920'),
                          opacity: farbe ? stufeVon(t.summe.tss).deckung : 1,
                          boxShadow: t.heute ? 'inset 0 0 0 1px #00d4ff' : an && farbe ? `0 0 6px ${farbe}` : 'none',
                          transform: an ? 'scale(1.3)' : 'none',
                        }}
                      />
                    )
                  })}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Fuß: was unter dem Zeiger liegt, sonst die Legende. Feste Höhe,
          damit nichts springt. */}
      <div className="mt-2 h-5 flex items-center justify-between gap-3 text-[10px] font-mono text-[var(--text-secondary)]">
        {hover ? (
          <span className="truncate">
            <span className="text-[#e8eaf0]">
              {parseTag(hover.tag).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })}
            </span>
            {hover.summe ? (
              <>
                <span className="text-[var(--text-muted)]"> · </span>
                <span style={{ color: DISCIPLINE_COLOR[hover.summe.haupt] }}>
                  {(DISCIPLINE_LABEL[hover.summe.haupt] || hover.summe.haupt).toUpperCase()}
                </span>
                {hover.summe.n > 1 && <span className="text-[var(--text-muted)]"> +{hover.summe.n - 1}</span>}
                <span className="text-[var(--text-muted)]"> · </span>{stunden(hover.summe.min)}
                <span className="text-[var(--text-muted)]"> · </span>{Math.round(hover.summe.tss)} TSS
              </>
            ) : (
              <span className="text-[var(--text-muted)]"> · {hover.zukunft ? 'still to come' : 'rest day'}</span>
            )}
          </span>
        ) : <span />}
        <span className="flex items-center gap-1 shrink-0 text-[9px] text-[var(--text-muted)]">
          TSS
          {STUFEN.map(s => (
            <span key={s.name} className="inline-block w-2.5 h-2.5 rounded-[2px]"
                  title={s.name} style={{ background: '#e8eaf0', opacity: s.deckung }} />
          ))}
        </span>
      </div>
    </div>
  )
}
