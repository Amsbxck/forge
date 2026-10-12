/** Was sich der Athlet für die Woche wünschen kann — und wann.
 *
 *  Die Trainingsformen hier stehen in den Studiendokumenten und der Coach
 *  plant sie, wenn man danach fragt — aber er schlägt sie nicht von selbst
 *  vor. Ohne diese Liste muss man wissen, dass es sie gibt, um sie zu
 *  bekommen. Genau das war der Anlass: Doppeltage sind seit der
 *  Studienumsetzung möglich, aber niemand kommt auf „teile den langen Lauf",
 *  wenn er den Begriff nie gelesen hat.
 *
 *  **Warum diese Liste hier liegt und nicht im Bauteil:** Zwei Ansichten
 *  benutzen sie — das aufklappbare Glossar (`components/PlanOptionen.jsx`)
 *  und die Knopfreihe über dem Eingabefeld (`components/WunschKnoepfe.jsx`).
 *  Zwei Kopien derselben Liste wären in dieser Reihe schon mehrfach der
 *  Fehler gewesen: Sobald eine Bedingung sich ändert, zeigt eine der beiden
 *  Ansichten etwas Falsches an, und niemand merkt, welche.
 *
 *  Die Bedingungen müssen mit `core/phasenregeln.py` übereinstimmen; dort
 *  steht die Wahrheit, hier die Anzeige.
 */

export const AUTOMATISCH = 'automatisch'
export const WUENSCHEN = 'wünschen'

/** `kuerzel` trägt nur, wer einen Knopf bekommt.
 *
 *  Nicht alle: Die Formatknöpfe für Intervalle sind ausdrücklich nicht
 *  gewollt — die Rotation beim Rad macht das von selbst und liest, was
 *  zuletzt vorgegeben war. Ein Knopf daneben wäre eine zweite Quelle für
 *  dieselbe Entscheidung. Die Knöpfe beschränken sich deshalb auf die
 *  Doppeltage und die Blockwoche: Formen, bei denen die Woche eine andere
 *  Gestalt bekommt und die Entscheidung wirklich beim Athleten liegt.
 *
 *  Die `name`-Werte sind für einen Knopf zu lang („Schwimmen als zweite
 *  Einheit"), deshalb ein eigenes, kurzes Feld statt einer Abschneidung.
 */
export const OPTIONEN = [
  // ── Belastungsverteilung ──────────────────────────────────────────────
  {
    id: 'block',
    name: 'Blockwoche',
    kuerzel: 'Blockwoche',
    // Die Blockwoche ändert die ganze Woche: fünf harte Einheiten statt zwei.
    // `services/plan_adjust.py` liefert aber nur geänderte Tage und verbietet
    // ausdrücklich zwei harte hintereinander — das Gegenteil einer
    // Blockwoche. Sie gehört deshalb in einen **neuen** Wochenplan.
    ganzeWoche: true,
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
    kuerzel: 'Locker + Qualität',
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
    kuerzel: 'Schwimmen + Kraft',
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
    kuerzel: 'Langen Lauf teilen',
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
    kuerzel: 'Doppelschwelle',
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

export const GRUPPEN = ['Belastungsverteilung', 'Doppeltage', 'Laufspezifisches']

/** Passt diese Option in die laufende Phase? `familie` aus `phaseFamilie`. */
export function istMoeglich(o, familie) {
  return o.phasen === null || (!!familie && o.phasen.includes(familie))
}

/** Die Optionen, für die es einen Knopf gibt — in der laufenden Phase.
 *
 *  Nur mit `kuerzel` **und** `wunsch`: Ein Knopf ohne Wunschsatz hätte nichts
 *  zu senden (`formatwechsel` ist genau dieser Fall und bewusst ohne).
 */
export function knopfOptionen(familie) {
  return OPTIONEN.filter(o => o.kuerzel && o.wunsch && istMoeglich(o, familie))
}

/** Der Text, der aus gewählten Knöpfen und Freitext entsteht.
 *
 *  **Erst beim Absenden zusammengesetzt, nicht beim Klick in das Feld
 *  geschrieben.** Angehängter Text müsste beim Abwählen wieder aus dem String
 *  herausgeschnitten werden — und wer ihn zwischendurch bearbeitet, bekommt
 *  Bruch: Der halb gelöschte Satz ginge wörtlich an das Modell. So hat jede
 *  Hälfte eine eigene Quelle, und das Abwählen ist folgenlos.
 */
export function wunschText(ids, freitext) {
  const saetze = OPTIONEN.filter(o => ids.has(o.id) && o.wunsch).map(o => o.wunsch)
  const rest = (freitext || '').trim()
  if (rest) saetze.push(rest)
  return saetze.join(' ')
}
