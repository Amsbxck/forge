import { useState } from 'react'
import SportIcon from './SportIcon'
import { DISCIPLINE_COLOR } from '../utils/colors'

const CARD = 'bg-[#111318] border border-[#1e2228] rounded-xl'
const DISPLAY = { fontFamily: 'Barlow Condensed, sans-serif' }

/** Anleitung zu den Testeinheiten.
 *
 *  Die automatische Auswertung braucht brauchbare Daten — Runden beim
 *  Schwimmen, einen sauberen Abschnitt beim Laufen und Radfahren. Klappt sie
 *  nicht, muss man die Werte ablesen können, statt ratlos dazustehen.
 *  Deshalb steht hier zu jedem Test, was zu tun ist, was die App daraus
 *  liest und wo der Wert sonst abzulesen ist.
 */
const TESTS = [
  {
    disziplin: 'bike',
    titel: 'RAD · FTP',
    ergebnis: 'FTP in Watt',
    varianten: [
      {
        name: '20-Minuten-Test (Standard)',
        ablauf: [
          '20 min einfahren, locker bis zügig',
          '5 min hart öffnen, danach 5 min ganz locker',
          '20 min maximal gleichmäßig — nicht zu schnell starten, die letzten fünf Minuten entscheiden',
          '10 min ausfahren',
        ],
        ablesen: 'Durchschnittswatt der 20 Minuten × 0,95 = FTP. Bei 275 W im Test sind es 261 W.',
      },
      {
        name: 'Zwift-Rampentest',
        ablauf: [
          'In Zwift unter Workouts → FTP Tests → „Ramp Test" oder „Ramp Test Lite"',
          'Die Belastung steigt jede Minute, bis nichts mehr geht',
          'Zwift rechnet selbst und zeigt die neue FTP am Ende an',
        ],
        ablesen: 'Zwift gibt die FTP direkt aus — diese Zahl unverändert eintragen, nicht noch einmal mit 0,95 rechnen.',
      },
    ],
    automatisch: 'Aus dem besten 20-Minuten-Abschnitt der Leistungsdaten.',
  },
  {
    disziplin: 'run',
    titel: 'LAUFEN · SCHWELLE',
    ergebnis: 'Schwellenpuls und Schwellenpace',
    varianten: [
      {
        name: '20-Minuten-Test (in der Testwoche)',
        ablauf: [
          '15 min einlaufen',
          '20 min maximal gleichmäßig, flache Strecke ohne Ampeln',
          '10 min auslaufen',
        ],
        ablesen: 'Durchschnittspuls der 20 Minuten × 0,98 = Schwellenpuls. Die Durchschnittspace dieser 20 Minuten ist die Schwellenpace. Beides steht in der Garmin-App unter der Aktivität → Runden.',
      },
      {
        name: 'Garmin-Schwellenlauf (geführt)',
        ablauf: [
          'Uhr: Training → Geführter Test → Laktatschwelle',
          'Brustgurt nötig — der Sensor am Handgelenk liefert die Schlagabstände nicht stabil genug',
          'Etwa 20–25 min: aufwärmen, dann stufenweise schneller, bis die Uhr den Knick erkennt',
        ],
        ablesen: 'Die Uhr meldet Puls und Pace direkt nach dem Test. Später nachzulesen in Garmin Connect unter Leistungswerte → Laktatschwelle.',
      },
    ],
    automatisch: 'Aus dem besten 20-Minuten-Abschnitt: Pace direkt, Puls über den Faktor 0,98.',
    hinweis: 'Beide Wege liefern dieselben zwei Zahlen. Der geführte Test der Uhr misst genauer, braucht aber einen Brustgurt.',
  },
  {
    disziplin: 'swim',
    titel: 'SCHWIMMEN · CSS',
    ergebnis: 'Schwellenpace je 100 m und Schwellenpuls im Wasser',
    varianten: [
      {
        name: 'CSS-Test (400 m / 200 m)',
        ablauf: [
          '400–600 m locker einschwimmen',
          '400 m maximal — Zeit stoppen oder Runde drücken',
          '5 min locker',
          '200 m maximal — Zeit stoppen oder Runde drücken',
          'Locker ausschwimmen',
        ],
        ablesen: 'CSS = (Zeit 400 m − Zeit 200 m) ÷ 2. Bei 6:40 und 3:10 sind das (400 − 190) ÷ 2 = 105 s, also 1:45 je 100 m.',
      },
    ],
    automatisch: 'Aus den Runden: die schnellste 400- und 200-Meter-Runde. Der Puls über die 400 m dient als Schätzung für die Schwelle im Wasser, abzüglich 5 %.',
    hinweis: 'Wichtig: Vor und nach jeder Teststrecke die Rundentaste drücken. Ohne Runden sieht die App nur eine Gesamtstrecke und kann nichts zuordnen — dann müssen die Zeiten von Hand eingetragen werden.',
  },
]

function Variante({ v, farbe }) {
  return (
    <div className="rounded-lg p-3" style={{ background: '#0d0f17', border: '1px solid #1e2228' }}>
      <div className="text-[11px] font-mono mb-2" style={{ color: farbe }}>{v.name}</div>
      <ol className="space-y-1 mb-2">
        {v.ablauf.map((z, i) => (
          <li key={i} className="text-xs text-[var(--text-secondary)] leading-relaxed flex gap-2">
            <span className="text-[var(--text-muted)] font-mono flex-shrink-0">{i + 1}.</span>
            <span>{z}</span>
          </li>
        ))}
      </ol>
      <div className="text-[11px] leading-relaxed border-l pl-2" style={{ borderColor: `${farbe}44`, color: 'var(--text-secondary)' }}>
        <span style={{ color: farbe }}>Ablesen: </span>{v.ablesen}
      </div>
    </div>
  )
}

export default function BenchmarkGuide() {
  const [offen, setOffen] = useState(false)

  return (
    <div className={CARD}>
      <button onClick={() => setOffen(o => !o)}
              className="w-full flex items-center justify-between px-5 py-4 hover:bg-[#0d0f17] transition-colors">
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-sm font-bold tracking-widest text-[var(--text-secondary)]" style={DISPLAY}>
            SO KOMMST DU ZU DEN WERTEN
          </span>
          <span className="text-[10px] font-mono text-[var(--text-muted)]">
            Testablauf, automatische Auswertung und Ablesen von Hand
          </span>
        </div>
        <span className="text-[var(--text-secondary)] font-mono text-sm">{offen ? '▲' : '▼'}</span>
      </button>

      {offen && (
        <div className="border-t border-[#1e2228] p-5 space-y-4">
          <p className="text-xs text-[var(--text-secondary)] leading-relaxed max-w-2xl">
            Die App wertet die Testeinheiten selbst aus. Klappt das nicht — weil die
            Runden fehlen, der Abschnitt unsauber war oder die Uhr nichts geliefert
            hat — trägst du die Werte im Profil von Hand ein. Eingetragene Werte
            werden von der Ableitung nicht mehr überschrieben.
          </p>

          {TESTS.map(t => {
            const farbe = DISCIPLINE_COLOR[t.disziplin]
            return (
              <div key={t.disziplin} className="rounded-xl p-4"
                   style={{ background: '#0d0f17', border: `1px solid ${farbe}22` }}>
                <div className="flex items-center gap-2 mb-1">
                  <SportIcon discipline={t.disziplin} size={16} color={farbe} />
                  <span className="text-[11px] font-mono tracking-widest" style={{ color: farbe }}>
                    {t.titel}
                  </span>
                  <span className="text-[10px] font-mono text-[var(--text-muted)]">→ {t.ergebnis}</span>
                </div>

                {/* Bei nur einer Variante über die volle Breite: als halbe
                    Spalte neben einer leeren Hälfte sah der Block aus, als
                    fehlte etwas. */}
                <div className={`grid gap-3 mt-3 ${t.varianten.length > 1 ? 'md:grid-cols-2' : ''}`}>
                  {t.varianten.map(v => <Variante key={v.name} v={v} farbe={farbe} />)}
                </div>

                <div className="text-[11px] text-[var(--text-muted)] leading-relaxed mt-3">
                  <span className="font-mono">Automatisch: </span>{t.automatisch}
                </div>
                {t.hinweis && (
                  <div className="mt-2 rounded-lg px-3 py-2 text-[11px] leading-relaxed"
                       style={{ background: '#f59e0b10', border: '1px solid #f59e0b28', color: '#f59e0b' }}>
                    {t.hinweis}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
