import { Component } from 'react'

/** Fängt Renderfehler ab, bevor sie die ganze App aushängen.
 *
 *  Ohne sie genügte ein einziger Fehler in einer Komponente — etwa eine
 *  Fehlerliste vom Server, die als Text ausgegeben werden sollte —, und die
 *  Seite war schwarz, ohne Hinweis und ohne Weg zurück. Hier bleibt eine
 *  Meldung mit einem Knopf zum Neuladen.
 */
export default class Fehlergrenze extends Component {
  constructor(props) {
    super(props)
    this.state = { fehler: null }
  }

  static getDerivedStateFromError(fehler) {
    return { fehler }
  }

  componentDidCatch(fehler, info) {
    console.error('Darstellungsfehler:', fehler, info?.componentStack)
  }

  render() {
    if (!this.state.fehler) return this.props.children
    return (
      <div className="min-h-screen flex items-center justify-center px-4" style={{ background: '#07080f' }}>
        <div className="max-w-md w-full rounded-xl p-6 space-y-4"
             style={{ background: '#111318', border: '1px solid #1e2228' }}>
          <div className="text-lg font-black tracking-tight text-[#e8eaf0]"
               style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>
            ETWAS IST SCHIEFGEGANGEN
          </div>
          <p className="text-sm text-[var(--text-secondary)] leading-relaxed">
            Diese Ansicht konnte nicht dargestellt werden. Deine Daten sind davon
            nicht betroffen. Lade die Seite neu — tritt es wieder auf, hilft die
            Meldung unten bei der Suche.
          </p>
          <pre className="text-[11px] font-mono text-[var(--text-muted)] whitespace-pre-wrap break-words">
            {String(this.state.fehler?.message || this.state.fehler)}
          </pre>
          <button onClick={() => window.location.reload()}
                  className="px-4 py-2 rounded-lg text-[12px] font-mono tracking-wide"
                  style={{ background: '#00d4ff15', border: '1px solid #00d4ff33', color: '#00d4ff' }}>
            NEU LADEN
          </button>
        </div>
      </div>
    )
  }
}
