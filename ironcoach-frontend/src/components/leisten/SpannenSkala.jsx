import { STATUS_COLOR } from '../../utils/colors'

/** Ein Wert in seiner Spanne — eine feine Leiste aus Zonen und Marken.
 *
 *  Zuerst entstanden in der Doppeltag-Kachel (`HrvAmpel`): Wo der HRV-Schnitt
 *  in der eigenen Spanne liegt. Amir mochte genau das — die Zahl nicht allein,
 *  sondern im Verhältnis zu dem, was für ihn normal ist. Deshalb ein eigener
 *  Baustein, damit HRV im Dashboard, im Chat und überall sonst gleich aussieht,
 *  statt dass jede Kachel ihre eigene Fassung baut.
 *
 *  `zonen`: `[{von, bis, farbe}]`, lückenlos aufsteigend. Die Leiste reicht
 *  vom ersten `von` bis zum letzten `bis`.
 *  `marken`: `[{wert, art, titel, name, farbe}]`. `haupt` ist der Strich, um
 *  den es geht (hell, mit Schein), `neben` ein Ring (etwa der heutige Wert
 *  neben dem Schnitt). Werte außerhalb werden an den Rand gesetzt, nicht
 *  versteckt — ein Ausreißer ist gerade die Information.
 *
 *  `name` beschriftet die Marke direkt an der Leiste: die Hauptmarke darüber,
 *  die Nebenmarke darunter. Vorher waren es zwei Striche ohne Namen, und
 *  niemand wusste, welcher der Schnitt und welcher heute ist. Oben und unten
 *  statt beide oben, weil Schnitt und Tageswert oft nur ein, zwei ms
 *  auseinanderliegen und sich die Namen sonst überdecken. Wer beschriftet,
 *  gibt der Skala über `className` Platz (oben und unten je etwa 1,25 rem).
 */
export default function SpannenSkala({ zonen, marken = [], className = 'mt-2' }) {
  if (!zonen?.length) return null
  const min = zonen[0].von
  const max = zonen[zonen.length - 1].bis
  if (!(max > min)) return null
  const pos = v => Math.min(100, Math.max(0, ((v - min) / (max - min)) * 100))

  return (
    <div className={`relative h-1 ${className}`}>
      {zonen.map(z => (
        <div
          key={`${z.von}-${z.bis}`}
          className="absolute inset-y-0"
          style={{
            left: `${pos(z.von)}%`,
            width: `${pos(z.bis) - pos(z.von)}%`,
            background: z.farbe,
            opacity: 0.35,
          }}
        />
      ))}
      {marken.filter(m => m.wert != null).map((m, i) => {
        const neben = m.art === 'neben'
        const farbe = m.farbe || '#e8eaf0'
        return (
          <div key={i} title={m.titel}>
            <div
              className="absolute -translate-x-1/2 rounded-full transition-all duration-700"
              style={
                neben
                  ? {
                      left: `${pos(m.wert)}%`, top: -3.5, width: 11, height: 11,
                      background: '#111318', border: `2px solid ${farbe}`,
                      boxShadow: `0 0 6px ${farbe}88`,
                    }
                  : {
                      left: `${pos(m.wert)}%`, top: -5, width: 3, height: 14,
                      background: farbe, boxShadow: `0 0 6px ${farbe}aa`,
                    }
              }
            />
            {m.name && (
              <span
                className="absolute -translate-x-1/2 whitespace-nowrap text-[9px] font-mono tracking-widest transition-all duration-700"
                style={{
                  // Der Name bleibt in der Kachel, auch wenn die Marke am
                  // Rand klebt — halb abgeschnitten wäre er nicht lesbar.
                  left: `${Math.min(94, Math.max(6, pos(m.wert)))}%`,
                  ...(neben ? { top: 12 } : { bottom: 12 }),
                  color: neben ? farbe : '#e8eaf0',
                }}
              >
                {m.name}
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}

/** Die HRV-Spanne als Zonen: rot unter, gelb dazwischen, grün im Band.
 *
 *  Ein Viertel der Spanne Luft auf beiden Seiten, damit ein Wert knapp
 *  außerhalb nicht am Rand klebt. `null` ohne vollständige Spanne — dann
 *  zeigt die Kachel die Zahl ohne Skala, statt eine erfundene zu zeichnen.
 */
export function hrvZonen(spanne) {
  const { rot_unter: rot, gruen_ab: ab, gruen_bis: bis } = spanne || {}
  if (!rot || !ab || !bis || bis <= rot) return null
  const luft = (bis - rot) * 0.25
  return [
    { von: rot - luft, bis: rot, farbe: STATUS_COLOR.red },
    { von: rot, bis: ab, farbe: STATUS_COLOR.yellow },
    { von: ab, bis, farbe: STATUS_COLOR.green },
    { von: bis, bis: bis + luft, farbe: `${STATUS_COLOR.green}55` },
  ]
}
