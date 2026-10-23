import { useMemo } from 'react'
import { phaseFamilie } from '../utils/phasen'
import { knopfOptionen } from '../utils/trainingsoptionen'
import DoppeltagZiehung from './DoppeltagZiehung'
import WunschKnoepfe from './WunschKnoepfe'

/** Wo die Woche gestaltet wird: Wünsche, Doppeltag, Optionen, Absenden.
 *
 *  Vorher stand all das in der Kopfzeile neben dem Titel — ein einzeiliges
 *  Feld von 16 rem, Knöpfe und die gezogene Form dazwischen, je nach
 *  Bildschirmbreite irgendwo umgebrochen. Ein Wunsch wie „Donnerstag frei,
 *  Samstag lieber lang aufs Rad" passte nicht in die Zeile, und was zu was
 *  gehörte, war nicht zu sehen.
 *
 *  Jetzt eine eigene Karte mit zwei Spalten: links der Text (mehrzeilig, mit
 *  der Vorschau dessen, was gesendet wird, direkt darunter), rechts was die
 *  App vorschlägt und was man anklicken kann, und darunter der eine Knopf.
 *  Schmal untereinander.
 *
 *  Die Logik (was gesendet wird, ob neu erstellt oder angepasst wird) bleibt
 *  in `pages/WeeklyPlan.jsx`; diese Komponente zeigt nur an.
 */

const ACCENT = '#00d4ff'

function Abschnitt({ titel, children }) {
  return (
    <div className="space-y-2">
      <div className="text-[9px] font-mono tracking-[0.2em] text-[var(--text-muted)]">{titel}</div>
      {children}
    </div>
  )
}

export default function WunschKonsole({
  plan, phase, zielSpanne, modus,
  requests, onRequests, vorschau,
  gewaehlt, onToggle,
  ziehung, ohneDoppeltag, ersetzt, onDoppeltag,
  absendbar, absenden, generating,
}) {
  const hatKnoepfe = useMemo(() => knopfOptionen(phaseFamilie(phase)).length > 0, [phase])
  const zeigtZiehung = !plan && ziehung

  // Beispiele je Modus: Beim Anpassen geht es um Tage, beim Erstellen um die
  // ganze Woche. Ein Platzhalter „Besondere Wünsche" sagte beides nicht.
  const platzhalter = plan
    ? 'Was soll sich ändern? z. B. „Donnerstag und Freitag tauschen“ oder „Samstag nur 60 min“'
    : 'Was soll diese Woche berücksichtigen? z. B. „Mittwoch keine Zeit, Sonntag langer Lauf, Knie etwas gereizt“'

  return (
    <section
      className="relative rounded-xl overflow-hidden"
      style={{ background: '#111318', border: '1px solid #1e2228' }}
    >
      {/* Die Signallinie oben: ruhig, solange nichts läuft; während Claude
          plant, läuft ein Lichtstreif darüber. Mehr Rückmeldung braucht ein
          Aufruf von bis zu drei Minuten nicht — aber diese braucht er. */}
      <div className="absolute inset-x-0 top-0 h-px" style={{ background: `${ACCENT}33` }} />
      {generating && (
        <div
          className="absolute top-0 h-[2px] w-1/3"
          style={{
            background: `linear-gradient(90deg, transparent, ${ACCENT}, transparent)`,
            animation: 'konsole-lauf 1.6s ease-in-out infinite',
          }}
        />
      )}

      <div className="grid lg:grid-cols-[minmax(0,1fr)_320px]">
        {/* Links: der Wunsch in eigenen Worten */}
        <div className="p-4 sm:p-5 space-y-3">
          {/* Kopf wie die Dashboard-Kacheln: Titel links, Zeitraum und Modus
              rechts. Der Modus steht neutral, Cyan trägt nur der Knopf. */}
          <div className="flex items-baseline justify-between gap-3 flex-wrap">
            <span className="text-xs font-mono tracking-[0.25em] text-[var(--text-secondary)]">YOUR WISHES</span>
            <span className="text-[10px] font-mono tracking-widest text-[var(--text-muted)]">
              {modus} · {zielSpanne}
            </span>
          </div>
          <textarea
            value={requests}
            onChange={e => onRequests(e.target.value)}
            // Enter macht eine neue Zeile — das Feld ist jetzt mehrzeilig.
            // Abschicken mit Strg/⌘ + Enter, oder über den Knopf.
            onKeyDown={e => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && absendbar) {
                e.preventDefault()
                absenden()
              }
            }}
            rows={4}
            placeholder={platzhalter}
            className="w-full resize-y min-h-[104px] rounded-lg px-3.5 py-3 text-sm leading-relaxed text-[#e8eaf0] placeholder-[var(--text-muted)] outline-none transition-colors"
            style={{ background: '#0d0f14', border: '1px solid #1e2228' }}
            onFocus={e => { e.target.style.borderColor = '#ffffff26' }}
            onBlur={e => { e.target.style.borderColor = '#1e2228' }}
          />
          <div className="flex items-start justify-between gap-3 min-h-[16px]">
            <div className="text-[11px] text-[var(--text-secondary)] leading-snug">
              {vorschau && (
                <>
                  <span className="font-mono text-[9px] tracking-[0.2em] text-[var(--text-muted)]">WILL SEND · </span>
                  {vorschau}
                </>
              )}
            </div>
            <span className="hidden sm:inline shrink-0 text-[9px] font-mono text-[var(--text-muted)]">
              CTRL/⌘ + ENTER
            </span>
          </div>
        </div>

        {/* Rechts: was die App vorschlägt, was man anklicken kann, Absenden */}
        <div
          className="p-4 sm:p-5 flex flex-col gap-5 border-t lg:border-t-0 lg:border-l"
          style={{ borderColor: '#1e2228', background: '#0d0f14' }}
        >
          {zeigtZiehung && (
            <Abschnitt titel="DOUBLE DAY THIS WEEK">
              <DoppeltagZiehung
                ziehung={ziehung}
                aus={ohneDoppeltag}
                ersetzt={ersetzt}
                onToggle={onDoppeltag}
              />
            </Abschnitt>
          )}

          {hatKnoepfe && (
            <Abschnitt titel={zeigtZiehung ? 'OR PICK YOURSELF' : 'OPTIONS'}>
              <WunschKnoepfe phase={phase} gewaehlt={gewaehlt} onToggle={onToggle} />
            </Abschnitt>
          )}

          <button
            onClick={absenden}
            disabled={!absendbar}
            className="mt-auto w-full px-4 py-3 rounded-lg font-mono font-bold tracking-wider text-sm transition-all disabled:opacity-40 disabled:cursor-not-allowed"
            style={{
              background: generating ? `${ACCENT}12` : `${ACCENT}1f`,
              border: `1px solid ${ACCENT}55`,
              color: ACCENT,
              boxShadow: absendbar && !generating ? `0 0 24px ${ACCENT}14` : 'none',
            }}
            onMouseEnter={e => { if (absendbar && !generating) e.currentTarget.style.background = `${ACCENT}30` }}
            onMouseLeave={e => { e.currentTarget.style.background = generating ? `${ACCENT}12` : `${ACCENT}1f` }}
          >
            {generating ? (
              <span className="flex items-center justify-center gap-2">
                <span className="inline-flex gap-0.5">
                  {[0, 1, 2].map(i => (
                    <span
                      key={i}
                      className="w-1 h-1 rounded-full"
                      style={{ background: ACCENT, animation: `pulse 1.2s ease-in-out ${i * 0.2}s infinite` }}
                    />
                  ))}
                </span>
                {plan ? 'ADJUSTING' : 'PLANNING'}
              </span>
            ) : (
              <span className="flex items-center justify-center gap-2">
                {modus}
                <span className="font-normal text-[11px] opacity-70">{zielSpanne}</span>
              </span>
            )}
          </button>
        </div>
      </div>

      <style>{`
        @keyframes konsole-lauf {
          0% { left: -33%; }
          100% { left: 100%; }
        }
      `}</style>
    </section>
  )
}
