/** Erkennt die Rennserie am Namen — Ironman, Challenge, Hyrox, Majors …
 *
 *  Bewusst aus dem Namen abgeleitet und nicht als Feld gespeichert: der Name
 *  steht ohnehin schon da, und ein zusätzliches Auswahlfeld beim Anlegen
 *  wäre eine Pflichtangabe für etwas, das rein der Optik dient.
 *
 *  Die Reihenfolge zählt: "Ironman 70.3" muss vor "Ironman" greifen.
 */

const SERIES = [
  {
    key: 'ironman703',
    test: /\b(70\.?3|half\s*ironman|ironman\s*70)/i,
    label: 'IRONMAN', sub: '70.3', color: '#e0142c',
  },
  {
    key: 'ironman',
    test: /\biron\s?man\b|\bim\s*\d{2,3}\b/i,
    label: 'IRONMAN', sub: null, color: '#e0142c',
  },
  {
    key: 'challenge',
    test: /\bchallenge\b/i,
    label: 'CHALLENGE', sub: 'FAMILY', color: '#f5a623',
  },
  {
    key: 'hyrox',
    test: /\bhyrox\b/i,
    label: 'HYROX', sub: null, color: '#eab308',
  },
  {
    key: 'spartan',
    test: /\bspartan\b/i,
    label: 'SPARTAN', sub: null, color: '#ef4444',
  },
  {
    key: 'xterra',
    test: /\bxterra\b/i,
    label: 'XTERRA', sub: null, color: '#22c55e',
  },
  {
    key: 't100',
    test: /\bt100\b|\bpto\b/i,
    label: 'T100', sub: null, color: '#06b6d4',
  },
  {
    // Die sechs World Marathon Majors — die einzige Laufserie mit einer
    // Identität, die über den einzelnen Ort hinausgeht.
    key: 'majors',
    test: /\b(berlin|london|boston|chicago|new\s*york|nyc|tokio|tokyo)\b/i,
    label: 'MAJORS', sub: null, color: '#f59e0b',
    // Nur über die volle Distanz: der Halbmarathon in Berlin gehört nicht dazu.
    onlyFor: race => race?.sport === 'running' && race?.distance === 'marathon',
  },
]

// Ohne erkannte Serie zählt die Distanz — bei Laufrennen ist das ohnehin die
// aussagekräftigste Angabe, die meisten Volksläufe gehören zu keiner Serie.
const BY_DISTANCE = {
  '10k': { label: '10 KM', color: '#8a909e' },
  half_marathon: { label: 'HALBMARATHON', color: '#8a909e' },
  marathon: { label: 'MARATHON', color: '#8a909e' },
  sprint: { label: 'SPRINT', color: '#8a909e' },
  olympic: { label: 'OLYMPISCH', color: '#8a909e' },
  middle: { label: 'MITTELDISTANZ', color: '#8a909e' },
  full: { label: 'LANGDISTANZ', color: '#8a909e' },
}

export function detectSeries(race) {
  const name = race?.race_name || ''
  for (const series of SERIES) {
    if (series.onlyFor && !series.onlyFor(race)) continue
    if (series.test.test(name)) return series
  }
  const fallback = BY_DISTANCE[race?.distance]
  return fallback
    ? { key: null, label: fallback.label, sub: null, color: fallback.color }
    : null
}
