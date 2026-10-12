import { useMemo, useState } from 'react'
import { FAMILIE_LABEL, phaseFamilie } from '../utils/phasen'
import { PHASE_COLOR } from '../utils/colors'

/** Was sich der Athlet für die Woche wünschen kann — und wann.
 *
 *  Die Trainingsformen hier stehen in den Studiendokumenten und der Coach
 *  plant sie, wenn man danach fragt — aber er schlägt sie nicht von selbst
 *  vor. Ohne diese Liste muss man wissen, dass es sie gibt, um sie zu
 *  bekommen. Genau das war der Anlass: Doppeltage sind seit der
 *  Studienumsetzung möglich, aber niemand kommt auf „teile den langen Lauf",
 *  wenn er den Begriff nie gelesen hat.
 *
 *  Zwei Dinge unterscheiden diese Liste von einem Nachschlagewerk:
 *
 *  1. **Sie weiß, welche Phase gerade läuft.** Was jetzt nicht geht, steht
 *     ausgegraut da — mit dem Grund, nicht ohne. Eine Liste, die alles gleich
 *     anzeigt, erzeugt Wünsche, die der Coach ablehnen muss.
 *  2. **Ein Klick trägt den Wunsch ein.** Der Text landet im Feld für
 *     besondere Wünsche, formuliert so, dass der Coach die Bedingung mitliest.
 *
 *  Die Bedingungen müssen mit `core/phasenregeln.py` übereinstimmen; dort
 *  steht die Wahrheit, hier die Anzeige.
 */

const ACCENT = '#00d4ff'

const AUTOMATISCH = 'automatisch'
const WUENSCHEN = 'wünschen'

const OPTIONEN = [
  // ── Belastungsverteilung ──────────────────────────────────────────────
  {
    id: 'block',
    name: 'Blockwoche',
    gruppe: 'Belastungsverteilung',
    art: AUTOMATISCH,
    phasen: ['build'],
    kurz: 'Eine Woche mit fünf harten Einheiten, danach drei Wochen mit je einer.',
    bedingung: 'HRV normal und ohne fallende Tendenz · nicht in einer Deload-Woche · nicht vor einem Wettkampf',
    beleg: 'VO2max +4,6 % gegenüber gleichmäßiger Verteilung bei gleicher Summe (Rønnestad 2014, 19 trainierte Radfahrer). Vier Wochen untersucht — Wiederholung ungeprüft.',
    wunsch: 'Wenn die HRV es zulässt: nächste Woche als Block mit fünf harten Einheiten, danach drei Wochen mit je einer.',
  },
  {
    id: 'formatwechsel',
    name: 'Formatwechsel beim Rad',
    gruppe: 'Belastungsverteilung',
    art: AUTOMATISCH,
    phasen: ['build'],
    kurz: '30/15, 4×8 min und 4–6×5 min über die Wochen wechseln.',
    bedingung: 'läuft von selbst — die App liest, was zuletzt vorgegeben war',
    beleg: 'Kein Format ist nachweislich besser als die anderen (Norte 2023). Der Wechsel ist deshalb kein Kompromiss.',
    wunsch: null,
  },

  // ── Doppeltage ────────────────────────────────────────────────────────
  {
    id: 'doppel_qualitaet',
    name: 'Locker morgens, Qualität abends',
    gruppe: 'Doppeltage',
    art: WUENSCHEN,
    phasen: ['grundlage', 'base', 'build', 'peak'],
    kurz: 'Zwei Einheiten an einem Tag, mindestens sechs Stunden auseinander.',
    bedingung: 'HRV in der Spanne · unter der Spanne fällt die zweite Einheit weg',
    beleg: 'Bei Weltklasseläufern Standard, 11–14 Einheiten pro Woche (Haugen 2022).',
    wunsch: 'Nutze einen Doppeltag: morgens locker, abends die Qualitätseinheit, mindestens sechs Stunden Abstand.',
  },
  {
    id: 'doppel_schwimmen',
    name: 'Schwimmen als zweite Einheit',
    gruppe: 'Doppeltage',
    art: WUENSCHEN,
    phasen: ['grundlage', 'base', 'build', 'peak'],
    kurz: 'Harte Rad- oder Laufeinheit, später am Tag Schwimmen. Oder Schwimmen plus Kraft.',
    bedingung: 'immer möglich · Schwimmen erzeugt keine Stoßbelastung und zählt nicht zum Laufumfang',
    beleg: 'Schwimmen 10 h nach harten Laufintervallen brachte am Folgetag +14 % Laufzeit bis zur Erschöpfung gegenüber passiver Ruhe, Entzündungsmarker −23 % (Lum 2010).',
    wunsch: 'Lege Schwimmen als zweite Einheit auf einen Trainingstag — gern mit Kraft am selben Tag, damit der Ruhetag frei bleibt.',
    hinweis: 'Das Mittel, wenn die Woche voll ist: zwei Einheiten auf einen Tag statt den Ruhetag zu opfern.',
  },
  {
    id: 'doppel_langer_lauf',
    name: 'Langen Lauf teilen',
    gruppe: 'Doppeltage',
    art: WUENSCHEN,
    phasen: ['grundlage', 'base', 'build'],
    kurz: 'Einen langen lockeren Lauf auf zwei Einheiten am Tag verteilen.',
    bedingung: 'hält jeden einzelnen Lauf unter der Einzellauf-Grenze · der Wochenumfang steigt trotzdem',
    beleg: 'Die Einzellauf-Grenze bezieht sich auf eine Einheit, nicht auf den Tag — zwei kürzere Läufe bleiben darunter.',
    wunsch: 'Teile den langen Lauf auf zwei Einheiten am selben Tag, damit jede einzelne unter der Distanzgrenze bleibt.',
  },
  {
    id: 'doppel_schwelle',
    name: 'Leichte Doppelschwelle',
    gruppe: 'Doppeltage',
    art: WUENSCHEN,
    phasen: ['build', 'peak'],
    kurz: 'Morgens etwa 5×6 min, abends 10×1000 m — beide bei 95–100 %, kontrolliert.',
    bedingung: 'HRV normal · erst wenn lockere Doppeltage vertragen werden · zählt als eine Qualitätseinheit',
    beleg: 'Geteilte Schwellenarbeit ergab RPE 6,0 statt 7,0 und weniger Muskelkater am Morgen danach (Talsnes 2024). Langfristige Anpassung ungeprüft.',
    wunsch: 'Plane einen leichten Doppelschwellentag: morgens 5×6 min, abends 10×1000 m, beide bei 95–100 % und kontrolliert.',
  },

  // ── Laufspezifisches ──────────────────────────────────────────────────
  {
    id: 'steigerungen',
    name: 'Steigerungsläufe',
    gruppe: 'Laufspezifisches',
    art: AUTOMATISCH,
    phasen: null, // überall
    kurz: '6–10 × 15–20 s locker schnell am Ende eines ruhigen Laufs, volle Erholung.',
    bedingung: 'in jeder Phase · kosten keine Erholung · nicht in Brick-Läufen',
    beleg: 'Schnelligkeit in kleinen Dosen (Haugen 2022). In der Grundlage besonders wertvoll, weil dort sonst nichts Schnelles stattfindet.',
    wunsch: 'Baue Steigerungsläufe ein: 6–10 × 15–20 s am Ende eines lockeren Laufs, volle Erholung.',
  },
  {
    id: 'kurzintervalle',
    name: '15/15 als Abwechslung',
    gruppe: 'Laufspezifisches',
    art: WUENSCHEN,
    phasen: ['build'],
    kurz: '2–3 × 10 min aus 15 s schnell / 15 s locker — der Unterschied muss klein bleiben.',
    bedingung: 'HRV normal · Abwechslung, nicht Standard',
    beleg: 'Kleiner Geschwindigkeitsunterschied ergab ~14 min bei VO2max, ein extremes Format nur ~7 min (Billat 2001). Bei Läufern schlagen Wiederholungen ab drei Minuten die kurzen deutlich.',
    wunsch: 'Als Abwechslung eine 15/15-Einheit: 2–3 × 10 min, schnell bei 112–118 %, locker bei 85–90 %.',
  },
  {
    id: 'zehnzwanzigdreissig',
    name: '10-20-30',
    gruppe: 'Laufspezifisches',
    art: WUENSCHEN,
    phasen: ['peak'],
    kurz: '3–4 × 5 min aus 30 s locker / 20 s mäßig / 10 s nahe maximal.',
    bedingung: 'zeitsparende Option im Peak',
    beleg: 'Gunnarsson & Bangsbo 2012.',
    wunsch: 'Plane eine 10-20-30-Einheit: 3–4 × 5 min, je 30 s locker / 20 s mäßig / 10 s nahe maximal, 2 min Pause.',
  },
]

const GRUPPEN = ['Belastungsverteilung', 'Doppeltage', 'Laufspezifisches']

function Etikett({ text, farbe, gedimmt }) {
  return (
    <span
      className="text-[9px] font-mono tracking-wider px-1.5 py-0.5 rounded"
      style={{
        color: gedimmt ? 'var(--text-muted)' : farbe,
        background: gedimmt ? '#16181f' : `${farbe}14`,
        border: `1px solid ${gedimmt ? '#1e2228' : `${farbe}33`}`,
      }}
    >
      {text}
    </span>
  )
}

function Option({ o, familie, onWunsch }) {
  const [offen, setOffen] = useState(false)
  const moeglich = o.phasen === null || (familie && o.phasen.includes(familie))
  const farbe = o.art === AUTOMATISCH ? '#40916c' : ACCENT

  return (
    <div
      className="rounded-lg overflow-hidden transition-colors"
      style={{
        background: '#111318',
        border: '1px solid #1e2228',
        // Die Schiene links sagt auf einen Blick, ob es jetzt geht. Ohne sie
        // liest sich die Liste wie ein Katalog, in dem alles gleich weit weg
        // ist. Nach `border`, damit sie es überschreibt und nicht umgekehrt.
        borderLeft: `2px solid ${moeglich ? farbe : '#1e2228'}`,
        opacity: moeglich ? 1 : 0.55,
      }}
    >
      <button
        onClick={() => setOffen(v => !v)}
        className="w-full text-left px-3 py-2.5 hover:bg-[#15171e] transition-colors"
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div
              className="text-[13px] font-bold leading-tight"
              style={{
                fontFamily: 'Barlow Condensed, sans-serif',
                color: moeglich ? '#e8eaf0' : 'var(--text-secondary)',
              }}
            >
              {o.name.toUpperCase()}
            </div>
            <div className="text-[11px] text-[var(--text-secondary)] mt-0.5 leading-snug">
              {o.kurz}
            </div>
          </div>
          <span className="text-[var(--text-muted)] font-mono text-[10px] shrink-0 mt-0.5">
            {offen ? '▲' : '▼'}
          </span>
        </div>

        <div className="flex flex-wrap gap-1 mt-2">
          <Etikett
            text={o.art === AUTOMATISCH ? 'KOMMT VON SELBST' : 'AUF WUNSCH'}
            farbe={farbe}
            gedimmt={!moeglich}
          />
          {(o.phasen || []).map(p => (
            <Etikett
              key={p}
              text={(FAMILIE_LABEL[p] || p).toUpperCase()}
              farbe={PHASE_COLOR[p] || ACCENT}
              gedimmt={!moeglich}
            />
          ))}
          {o.phasen === null && (
            <Etikett text="JEDE PHASE" farbe={PHASE_COLOR.base} gedimmt={false} />
          )}
        </div>
      </button>

      {offen && (
        <div className="px-3 pb-3 pt-1 space-y-2 border-t border-[#1e2228]">
          <div>
            <div className="text-[9px] font-mono tracking-widest text-[var(--text-muted)] mb-0.5">
              BEDINGUNGEN
            </div>
            <div className="text-[11px] text-[#c8ccd6] leading-snug">{o.bedingung}</div>
          </div>
          <div>
            <div className="text-[9px] font-mono tracking-widest text-[var(--text-muted)] mb-0.5">
              BELEG
            </div>
            <div className="text-[11px] text-[var(--text-secondary)] leading-snug">
              {o.beleg}
            </div>
          </div>
          {o.hinweis && (
            <div
              className="text-[11px] leading-snug px-2 py-1.5 rounded"
              style={{ background: `${ACCENT}0d`, color: '#c8ccd6' }}
            >
              {o.hinweis}
            </div>
          )}

          {!moeglich && (
            <div className="text-[11px] text-[var(--text-muted)] leading-snug">
              Jetzt nicht: diese Form gehört in{' '}
              {(o.phasen || []).map(p => FAMILIE_LABEL[p] || p).join(' oder ')}
              {familie ? `, die laufende Phase ist ${FAMILIE_LABEL[familie] || familie}.` : '.'}
            </div>
          )}

          {moeglich && o.wunsch && (
            <button
              onClick={() => onWunsch(o.wunsch)}
              className="text-[10px] font-mono tracking-wider px-2.5 py-1.5 rounded transition-colors"
              style={{
                color: ACCENT,
                background: `${ACCENT}14`,
                border: `1px solid ${ACCENT}44`,
              }}
              onMouseEnter={e => { e.currentTarget.style.background = `${ACCENT}26` }}
              onMouseLeave={e => { e.currentTarget.style.background = `${ACCENT}14` }}
            >
              IN DIE WÜNSCHE ÜBERNEHMEN →
            </button>
          )}
          {moeglich && !o.wunsch && (
            <div className="text-[11px] text-[var(--text-muted)] leading-snug">
              Kein Wunsch nötig — das macht die App von selbst.
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function PlanOptionen({ phase, onWunsch }) {
  const [open, setOpen] = useState(false)
  const familie = useMemo(() => phaseFamilie(phase), [phase])

  const moeglichJetzt = OPTIONEN.filter(
    o => o.phasen === null || (familie && o.phasen.includes(familie))
  ).length

  return (
    <div className="bg-[#0d0f17] border border-[#1e2228] rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-[#111318] transition-colors"
      >
        <div className="flex items-center gap-3 flex-wrap">
          <span
            className="font-bold tracking-widest text-[var(--text-secondary)]"
            style={{ fontFamily: 'Barlow Condensed, sans-serif', fontSize: '0.85rem' }}
          >
            WAS DU DIR WÜNSCHEN KANNST
          </span>
          <span className="text-xs font-mono text-[var(--text-muted)]">
            {moeglichJetzt} von {OPTIONEN.length} jetzt möglich
            {familie ? ` · Phase ${FAMILIE_LABEL[familie]}` : ''}
          </span>
        </div>
        <span className="text-[var(--text-secondary)] font-mono text-sm">
          {open ? '▲' : '▼'}
        </span>
      </button>

      {open && (
        <div className="border-t border-[#1e2228] p-5 space-y-5">
          <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed">
            Diese Trainingsformen stehen in den Studiendokumenten, und der Coach
            plant sie — aber die meisten schlägt er nicht von selbst vor. Was
            jetzt nicht geht, steht ausgegraut mit dem Grund dabei. Wo ein Beleg
            dünn ist, ist es vermerkt; das entscheidet, wie fest du darauf bauen
            solltest.
          </p>

          {GRUPPEN.map(gruppe => {
            const eintraege = OPTIONEN.filter(o => o.gruppe === gruppe)
            if (!eintraege.length) return null
            return (
              <div key={gruppe}>
                <div className="text-[10px] font-mono tracking-widest text-[var(--text-secondary)] mb-2">
                  {gruppe.toUpperCase()}
                </div>
                <div className="grid gap-2 md:grid-cols-2">
                  {eintraege.map(o => (
                    <Option
                      key={o.id}
                      o={o}
                      familie={familie}
                      onWunsch={onWunsch}
                    />
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
