import { useMemo, useState } from 'react'

/** Begriffe, die in der App vorkommen — an einer Stelle erklärt.
 *
 *  Vorher standen hier fünf Kennzahlen in einer Reiterleiste. Mit dreißig
 *  Einträgen trägt das nicht mehr: gruppiert und durchsuchbar findet man
 *  einen Begriff, ohne ihn schon zu kennen.
 *
 *  Deutsch, obwohl die Kacheln darüber englisch beschriftet sind: Die
 *  Begriffe selbst sind Fachvokabular und bleiben, wie sie in der App
 *  stehen — erklärt wird in der Sprache, in der auch der Coach schreibt.
 */

const ACCENT = '#00d4ff'
const ORANGE = '#f97316'
const GREEN = '#22c55e'
const PINK = '#ec4899'
const BLUE = '#38bdf8'
const VIOLET = '#a855f7'
const AMBER = '#f59e0b'

const EINTRAEGE = [
  // ── Belastung und Form ────────────────────────────────────────────────
  {
    term: 'TSS', full: 'Training Stress Score', gruppe: 'Belastung', color: ACCENT,
    desc: 'Eine Zahl für die Belastung einer Einheit — Dauer mal Intensität. Eine Stunde locker ist etwa 40, ein harter Wettkampf über zwei Stunden etwa 150.',
    formula: 'TSS = (Dauer_s × NP × IF) / (FTP × 3600) × 100',
    notes: [
      'Beim Rad mit Leistungsmessung exakt berechnet.',
      'Ohne Leistung über den Puls geschätzt — in der App mit ~ gekennzeichnet.',
    ],
  },
  {
    term: 'CTL', full: 'Chronic Training Load — Fitness', gruppe: 'Belastung', color: ACCENT,
    desc: 'Gleitender Durchschnitt der TSS über 42 Tage. Steht für deine Grundlage: baut sich langsam auf und verschwindet langsam.',
    formula: 'CTL = CTL_vorher + (TSS_heute − CTL_vorher) × (1 − e^(−1/42))',
    notes: ['Braucht rund sechs Wochen, bis sie einen Trainingsstand abbildet.'],
  },
  {
    term: 'ATL', full: 'Acute Training Load — Ermüdung', gruppe: 'Belastung', color: ORANGE,
    desc: 'Dasselbe über sieben Tage. Reagiert schnell und zeigt, wie müde du gerade bist.',
    formula: 'ATL = ATL_vorher + (TSS_heute − ATL_vorher) × (1 − e^(−1/7))',
  },
  {
    term: 'TSB', full: 'Training Stress Balance — Form', gruppe: 'Belastung', color: GREEN,
    desc: 'Fitness minus Ermüdung. Positiv heißt frisch, stark negativ heißt, dass die Ermüdung die Grundlage überholt hat.',
    formula: 'TSB = CTL − ATL',
    notes: [
      'über +5: frisch — passend für den Wettkampf',
      '−10 bis +5: optimal — hier wird trainiert',
      'unter −20: überlastet — Erholung nötig',
    ],
  },
  {
    term: 'IF', full: 'Intensity Factor', gruppe: 'Belastung', color: ACCENT,
    desc: 'Wie hart eine Einheit im Verhältnis zu deiner Schwelle war. 1,0 bedeutet, du bist die ganze Zeit an der Schwelle gefahren.',
    formula: 'IF = NP / FTP',
  },
  {
    term: 'NP', full: 'Normalized Power', gruppe: 'Belastung', color: VIOLET,
    desc: 'Gewichteter Leistungsschnitt. Berücksichtigt, dass Schwankungen stärker ermüden als gleichmäßiges Fahren — deshalb liegt NP über dem einfachen Durchschnitt.',
    notes: ['Bei gleichmäßiger Fahrt fast identisch mit dem Schnitt, bei Intervallen deutlich darüber.'],
  },

  // ── Leistungswerte ────────────────────────────────────────────────────
  {
    term: 'FTP', full: 'Functional Threshold Power', gruppe: 'Leistungswerte', color: VIOLET,
    desc: 'Die Leistung, die du rund eine Stunde am Stück halten kannst. Bezugsgröße für alle Wattvorgaben auf dem Rad.',
    formula: 'FTP = bester 20-Minuten-Schnitt × 0,95',
    notes: ['Wird aus der Testwoche gemessen, nicht geschätzt.'],
  },
  {
    term: 'Schwellenpace', full: 'Threshold Pace', gruppe: 'Leistungswerte', color: PINK,
    desc: 'Das Lauftempo, das du etwa eine Stunde durchhältst. Bezugsgröße für alle Pacevorgaben.',
    notes: ['Aus dem besten 20-Minuten-Abschnitt des Laufschwellentests.'],
  },
  {
    term: 'CSS', full: 'Critical Swim Speed', gruppe: 'Leistungswerte', color: BLUE,
    desc: 'Deine Schwellenpace im Wasser, je 100 m. Beide Teststrecken enthalten dieselbe Startreserve — die Differenz lässt den rein aeroben Anteil übrig.',
    formula: 'CSS = (Zeit 400 m − Zeit 200 m) ÷ 2',
    notes: ['Test: 400 m und 200 m je maximal, dazwischen 5 min locker.'],
  },
  {
    term: 'VO₂max', full: 'Maximale Sauerstoffaufnahme', gruppe: 'Leistungswerte', color: ORANGE,
    desc: 'Die obere Grenze deines Ausdauersystems. Als Trainingsstufe: kurze, sehr harte Intervalle in Zone 5.',
  },

  // ── Herzfrequenz ──────────────────────────────────────────────────────
  {
    term: 'HFmax', full: 'Maximale Herzfrequenz', gruppe: 'Herzfrequenz', color: '#ef4444',
    desc: 'Der höchste Wert, den du tatsächlich erreicht hast. Grundlage aller Zonengrenzen — geschätzt aus dem Alter wäre er für die meisten Menschen falsch.',
  },
  {
    term: 'Zonen', full: 'Z1 bis Z5', gruppe: 'Herzfrequenz', color: ACCENT,
    desc: 'Fünf Intensitätsbereiche als Anteil der maximalen Herzfrequenz.',
    notes: [
      'Z1 bis 70 % — Erholung',
      'Z2 bis 85 % — Grundlage, hier liegt der größte Teil des Trainings',
      'Z3 bis 90 % — Sweet Spot, zügig aber kontrolliert',
      'Z4 bis 95 % — Schwelle',
      'Z5 darüber — VO₂max',
    ],
  },
  {
    term: 'Schwellenpuls', full: 'Threshold HR / LTHR', gruppe: 'Herzfrequenz', color: '#eab308',
    desc: 'Der Puls an der Schwelle. Bezugsgröße, wenn die TSS über den Puls geschätzt wird — in dieser App die Obergrenze von Zone 2 aus deinem Profil.',
  },
  {
    term: 'rMSSD', full: 'Herzratenvariabilität', gruppe: 'Herzfrequenz', color: GREEN,
    desc: 'Streuung der Abstände zwischen zwei Herzschlägen, morgens im Liegen gemessen. Ein hoher Wert spricht für Erholung, ein Einbruch für Belastung oder beginnende Krankheit.',
    notes: ['Nur im Verlauf aussagekräftig — ein einzelner Wert sagt wenig.'],
  },

  // ── Trainingsformen ───────────────────────────────────────────────────
  {
    term: 'Base / Endurance', full: 'Grundlage', gruppe: 'Trainingsformen', color: GREEN,
    desc: 'Lockeres Training in Z1/Z2. Baut die aerobe Grundlage auf und macht den größten Teil des Umfangs aus.',
  },
  {
    term: 'Sweet Spot', full: 'Zone 3', gruppe: 'Trainingsformen', color: '#f4a261',
    desc: 'Zügig, aber noch kontrolliert — etwa 88 bis 94 % der FTP. Guter Reiz bei überschaubarer Ermüdung.',
  },
  {
    term: 'Threshold', full: 'Zone 4 — Schwelle', gruppe: 'Trainingsformen', color: '#e76f51',
    desc: 'An der Schwelle, typischerweise als Intervalle von 8 bis 20 Minuten.',
  },
  {
    term: 'Brick', full: 'Koppeltraining', gruppe: 'Trainingsformen', color: '#d946ef',
    desc: 'Rad und direkt danach Laufen. Trainiert die Umstellung, nicht das Tempo — der Laufteil ist immer kürzer als ein eigenständiger Lauf.',
  },
  {
    term: 'Walk-Run', full: 'Geh-Lauf-Intervalle', gruppe: 'Trainingsformen', color: PINK,
    desc: 'Laufen mit eingebauten Gehpausen. Bringt Umfang bei geringerer Aufprallbelastung — der Standard, solange die Schienbeine sich anpassen.',
  },
  {
    term: 'Strides', full: 'Steigerungsläufe', gruppe: 'Trainingsformen', color: PINK,
    desc: '15 bis 20 Sekunden schnell am Ende eines Laufs, mit voller Pause. Gewöhnt Sehnen und Muskulatur an höheres Tempo, ohne müde zu machen.',
  },
  {
    term: 'Ersatztraining', full: 'Cross-Training', gruppe: 'Trainingsformen', color: '#64748b',
    desc: 'StairMaster, Crosstrainer, Ruderergometer, Aquajogging. Erzeugt Ausdauerreiz, wenn die eigentliche Disziplin ausfällt — bei Aufprallproblemen ohne Stoßbelastung.',
    notes: ['Zählt zum Umfang, ersetzt aber keine disziplinspezifische Anpassung.'],
  },
  {
    term: 'Deload', full: 'Entlastungswoche', gruppe: 'Trainingsformen', color: BLUE,
    desc: 'Woche mit deutlich reduziertem Umfang am Ende eines Blocks. Der Trainingsreiz wirkt erst in der Erholung.',
  },

  // ── Saison und Planung ────────────────────────────────────────────────
  {
    term: 'Base · Build · Peak · Taper', full: 'Trainingsphasen', gruppe: 'Saison', color: ACCENT,
    desc: 'Der Aufbau einer Saison: erst Grundlage, dann Intensität, dann wettkampfnahe Belastung, zuletzt Erholung vor dem Renntag.',
    notes: ['Länge und Grenzen ergeben sich aus der Distanz deines Ziels.'],
  },
  {
    term: 'A-, B-, C-Rennen', full: 'Wettkampfpriorität', gruppe: 'Saison', color: AMBER,
    desc: 'A ist das Saisonziel und bestimmt Planlänge und Phasen. B wird ernst genommen, ändert die Saison aber nicht — kurze Entlastung davor. C wird als harte Einheit mitgenommen.',
  },
  {
    term: 'Taper', full: 'Formaufbau vor dem Rennen', gruppe: 'Saison', color: ACCENT,
    desc: 'Umfang runter, Intensität kurz halten. Die Form kommt aus der Erholung, nicht aus zusätzlichem Training.',
    notes: ['Ausfalltage kurz vor dem Rennen verkürzen den Taper — die Erholung hat bereits stattgefunden.'],
  },
  {
    term: 'Off Season', full: 'Übergang und Formerhalt', gruppe: 'Saison', color: 'var(--text-secondary)',
    desc: 'Nach dem Saisonziel. Zwei Wochen Übergang mit wenig und lockerem Training, danach Formerhalt: wenige regelmäßige Einheiten, ohne Watt- und Pacevorgaben.',
    notes: ['Ausdauer fällt schon nach zwei bis drei reizfreien Wochen messbar ab.'],
  },

  // ── Gesundheit ────────────────────────────────────────────────────────
  {
    term: 'Hals-Check', full: 'Trainieren mit Erkältung?', gruppe: 'Gesundheit', color: GREEN,
    desc: 'Beschwerden oberhalb des Halses ohne Fieber — Schnupfen, Halskratzen — erlauben lockeres Training in Z1/Z2. Husten, Gliederschmerzen oder Fieber bedeuten Pause.',
    notes: ['Training mit Fieber kann eine Herzmuskelentzündung auslösen. Dafür gibt es keine Abwägung.'],
  },
  {
    term: 'Wiedereinstieg', full: 'Nach Krankheit oder Verletzung', gruppe: 'Gesundheit', color: AMBER,
    desc: 'Etwa ein lockerer Tag je Ausfalltag, nach Fieber mindestens drei. Verpasste Einheiten werden nicht nachgeholt — der Aufbau setzt dort an, wo du stehst.',
  },
]

const GRUPPEN = ['Belastung', 'Leistungswerte', 'Herzfrequenz', 'Trainingsformen', 'Saison', 'Gesundheit']

function Eintrag({ g }) {
  return (
    <div className="rounded-xl p-4" style={{ background: '#111318', border: '1px solid #1e2228' }}>
      <div className="flex items-baseline gap-2 flex-wrap">
        <span className="text-lg font-bold tracking-wide"
              style={{ fontFamily: 'Barlow Condensed, sans-serif', color: g.color }}>
          {g.term}
        </span>
        <span className="text-[10px] font-mono text-[var(--text-muted)]">{g.full}</span>
      </div>
      <p className="text-xs text-[var(--text-secondary)] leading-relaxed mt-1.5">{g.desc}</p>
      {g.formula && (
        <div className="mt-2 rounded-lg px-3 py-2 text-[11px] font-mono overflow-x-auto"
             style={{ background: '#0d0f17', border: '1px solid #1e2228', color: g.color }}>
          {g.formula}
        </div>
      )}
      {g.notes && (
        <ul className="mt-2 space-y-0.5">
          {g.notes.map((n, i) => (
            <li key={i} className="text-[11px] text-[var(--text-muted)] leading-relaxed">— {n}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function Glossary() {
  const [open, setOpen] = useState(false)
  const [suche, setSuche] = useState('')

  const gefiltert = useMemo(() => {
    const q = suche.trim().toLowerCase()
    if (!q) return EINTRAEGE
    return EINTRAEGE.filter(g =>
      [g.term, g.full, g.desc, ...(g.notes || [])].join(' ').toLowerCase().includes(q)
    )
  }, [suche])

  return (
    <div className="bg-[#0d0f17] border border-[#1e2228] rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-[#111318] transition-colors"
      >
        <div className="flex items-center gap-3 flex-wrap">
          <span className="font-bold tracking-widest text-[var(--text-secondary)]"
                style={{ fontFamily: 'Barlow Condensed, sans-serif', fontSize: '0.85rem' }}>
            GLOSSAR
          </span>
          <span className="text-xs font-mono text-[var(--text-muted)]">
            {EINTRAEGE.length} Begriffe · TSS · FTP · CSS · Zonen · Phasen · Gesundheit
          </span>
        </div>
        <span className="text-[var(--text-secondary)] font-mono text-sm">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="border-t border-[#1e2228] p-5 space-y-5">
          <input
            value={suche}
            onChange={e => setSuche(e.target.value)}
            placeholder="Begriff suchen …"
            className="w-full rounded-lg px-3 py-2 text-sm font-mono text-[#e8eaf0] placeholder-[var(--text-muted)] outline-none"
            style={{ background: '#111318', border: '1px solid #1e2228' }}
          />

          {gefiltert.length === 0 && (
            <p className="text-xs font-mono text-[var(--text-muted)]">
              Kein Begriff gefunden. Fehlt einer? Dann gehört er hier hinein.
            </p>
          )}

          {GRUPPEN.map(gruppe => {
            const eintraege = gefiltert.filter(g => g.gruppe === gruppe)
            if (!eintraege.length) return null
            return (
              <div key={gruppe}>
                <div className="text-[10px] font-mono tracking-widest text-[var(--text-secondary)] mb-2">
                  {gruppe.toUpperCase()}
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  {eintraege.map(g => <Eintrag key={g.term} g={g} />)}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
