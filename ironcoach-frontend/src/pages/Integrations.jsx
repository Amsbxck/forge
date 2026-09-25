import { useCallback, useEffect, useState } from 'react'
import {
  getIntegrations, updateObsidian, testObsidian,
  getStravaAuthUrl, disconnectStrava,
  getWebhookStatus, registerWebhook, deleteWebhook,
  reorganizeVault,
} from '../services/api'

const CARD = 'bg-[#111318] border border-[#1e2228] rounded-xl'
const LABEL = 'text-[10px] font-mono tracking-widest text-[var(--text-secondary)]'
const DISPLAY = { fontFamily: 'Barlow Condensed, sans-serif' }
const FIELD = 'rounded-lg px-3 py-2 text-sm font-mono text-[#e8eaf0] placeholder-[var(--text-muted)] outline-none w-full'
const FIELD_STYLE = { background: '#0d0f17', border: '1px solid #1e2228' }

function Status({ ok, children }) {
  const color = ok ? '#22c55e' : '#3a3f4a'
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] font-mono" style={{ color }}>
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: color }} />
      {children}
    </span>
  )
}

export default function Integrations() {
  const [state, setState] = useState(null)
  const [form, setForm] = useState({ base_url: '', api_key: '', vault_subdir: '' })
  const [test, setTest] = useState(null)
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState(null)
  const [saved, setSaved] = useState(false)
  const [webhook, setWebhook] = useState(null)
  const [publicUrl, setPublicUrl] = useState('')
  const [hookResult, setHookResult] = useState(null)
  const [ordnung, setOrdnung] = useState(null)
  // Ergebnis der Strava-Freigabe, aus der Adresszeile gelesen.
  const [stravaRueckmeldung, setStravaRueckmeldung] = useState(null)

  const load = useCallback(async () => {
    try {
      const { data } = await getIntegrations()
      setState(data)
      setForm(f => ({
        base_url: data.obsidian.base_url || '',
        // Der Schlüssel kommt nie im Klartext zurück — leeres Feld heißt
        // "unverändert lassen", nicht "löschen".
        api_key: '',
        vault_subdir: data.obsidian.vault_subdir || '',
      }))
    } catch {
      setError('Anbindungen konnten nicht geladen werden')
    }
    try {
      const { data } = await getWebhookStatus()
      setWebhook(data)
      // Vorschlag nur setzen, solange nichts eingetippt wurde.
      // Vorbelegen: erst die konfigurierte öffentliche Adresse, sonst die
      // bereits registrierte. Aus der Anfrage abgeleitet käme localhost heraus.
      setPublicUrl(prev => prev || data.public_base_url
        || (data.subscriptions?.[0]?.callback_url || '').replace(/\/webhook$/, ''))
    } catch { setWebhook(null) }
  }, [])

  useEffect(() => { load() }, [load])

  // Nach der Freigabe bei Strava leitet das Backend hierher zurück und hängt
  // das Ergebnis an die Adresse. Ohne diese Auswertung landete der Athlet auf
  // einer Seite, die aussieht wie vorher — ob es geklappt hat, wüsste er erst
  // nach einem Neuladen.
  useEffect(() => {
    const p = new URLSearchParams(window.location.search)
    const stand = p.get('strava')
    if (!stand) return
    setStravaRueckmeldung(
      stand === 'ok'
        ? {
            ok: true,
            text: p.get('historie') === '1'
              // Beim ersten Verbinden läuft das Nachholen im Hintergrund.
              // Ohne diesen Hinweis wirkt die Seite einen Moment lang leer,
              // und der Athlet drückt erneut auf Verbinden.
              ? 'Strava ist verbunden. Deine Einheiten der letzten drei Monate '
                + 'werden gerade geholt — das dauert einen Moment und läuft im '
                + 'Hintergrund weiter. Neue Aktivitäten kommen ab jetzt von selbst an.'
              : 'Strava ist verbunden. Neue Aktivitäten kommen ab jetzt von selbst an.',
          }
        : { ok: false, text: p.get('grund') || 'Die Verbindung mit Strava ist fehlgeschlagen.' }
    )
    // Parameter wieder entfernen: Ein Neuladen zeigte die Meldung sonst
    // erneut, obwohl gerade nichts passiert ist.
    window.history.replaceState({}, '', window.location.pathname)
    if (stand === 'ok') load()
  }, [load])

  const save = async (e) => {
    e.preventDefault()
    setBusy('save'); setError(null); setSaved(false)
    try {
      const payload = { base_url: form.base_url, vault_subdir: form.vault_subdir }
      if (form.api_key) payload.api_key = form.api_key
      const { data } = await updateObsidian(payload)
      setState(data)
      // Die vervollständigte Adresse zurück ins Feld: Wer nur `100.84.12.7`
      // eingefügt hat, sieht sonst weiter seine Eingabe, während gespeichert
      // etwas anderes ist. Beim nächsten Speichern stünde die Frage im Raum,
      // welche der beiden gilt.
      setForm(f => ({ ...f, base_url: data.obsidian.base_url || f.base_url, api_key: '' }))
      setSaved(true)
    } catch (err) {
      setError(err.response?.data?.detail || 'Speichern fehlgeschlagen')
    } finally { setBusy(null) }
  }

  const check = async () => {
    setBusy('test'); setTest(null); setError(null)
    try {
      const payload = {}
      if (form.base_url) payload.base_url = form.base_url
      if (form.api_key) payload.api_key = form.api_key
      const { data } = await testObsidian(payload)
      setTest(data)
      // Die vervollständigte Adresse sofort ins Feld — das Backend hat sie
      // für den Test ohnehin schon gebildet. Ohne das sieht der Athlet seine
      // nackte Eingabe stehen und hält die Ergänzung für kaputt, obwohl sie
      // funktioniert hat. Genau so ist es dem ersten neuen Nutzer ergangen.
      if (data?.base_url) setForm(f => ({ ...f, base_url: data.base_url }))
    } catch (err) {
      setTest({ ok: false, error: err.response?.data?.detail || 'Test fehlgeschlagen' })
    } finally { setBusy(null) }
  }

  const ordnen = async () => {
    setBusy('ordnen'); setOrdnung(null); setError(null)
    try {
      const { data } = await reorganizeVault()
      setOrdnung(data)
    } catch (err) {
      setOrdnung({ error: err.response?.data?.detail || 'Umsortieren fehlgeschlagen' })
    } finally { setBusy(null) }
  }

  const saveHook = async () => {
    setBusy('hook'); setHookResult(null)
    try {
      const { data } = await registerWebhook(publicUrl || undefined)
      setHookResult({ ok: true, message: `Registriert auf ${data.callback_url}` })
      await load()
    } catch (err) {
      setHookResult({ ok: false, message: err.response?.data?.detail || 'Registrierung fehlgeschlagen' })
    } finally { setBusy(null) }
  }

  const removeHook = async () => {
    if (!confirm('Webhook entfernen? Neue Einheiten kommen dann erst beim stündlichen Abgleich.')) return
    setBusy('hook'); setHookResult(null)
    try {
      await deleteWebhook()
      setHookResult({ ok: true, message: 'Webhook entfernt' })
      await load()
    } catch (err) {
      setHookResult({ ok: false, message: err.response?.data?.detail || 'Entfernen fehlgeschlagen' })
    } finally { setBusy(null) }
  }

  const connectStrava = async () => {
    setBusy('strava')
    try {
      const { data } = await getStravaAuthUrl()
      window.location.href = data.auth_url
    } catch (err) {
      setError('Strava-Verbindung konnte nicht gestartet werden')
      setBusy(null)
    }
  }

  const unlinkStrava = async () => {
    if (!confirm('Strava trennen? Bereits eingelesene Einheiten bleiben erhalten.')) return
    setBusy('strava')
    try { await disconnectStrava(); await load() } finally { setBusy(null) }
  }

  if (!state) {
    return <div className="text-[var(--text-secondary)] font-mono text-sm py-8 text-center tracking-widest">LÄDT…</div>
  }

  return (
    <div className="space-y-6 page-enter">
      <h1 className="text-3xl font-black tracking-tight text-[#e8eaf0]" style={DISPLAY}>
        ANBINDUNGEN
      </h1>

      {error && (
        <div className="rounded-lg px-3 py-2 font-mono text-xs"
             style={{ background: '#ef444415', border: '1px solid #ef444430', color: '#ef4444' }}>
          {error}
        </div>
      )}

      {/* Strava */}
      <div className={`${CARD} p-5`} style={{ borderLeft: '3px solid #fc4c02' }}>
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-lg font-black tracking-tight text-[#e8eaf0]" style={DISPLAY}>STRAVA</h2>
            <p className="text-xs text-[var(--text-secondary)] mt-1 max-w-md leading-relaxed">
              Liefert deine Einheiten samt Runden und Leistungsdaten. Ohne Verbindung
              bleibt nur der manuelle Upload von FIT-Dateien.
            </p>
            <div className="mt-2">
              <Status ok={state.strava.connected}>
                {state.strava.connected
                  ? `Verbunden · Athlet ${state.strava.athlete_id}`
                  : 'Nicht verbunden'}
              </Status>
            </div>
            {stravaRueckmeldung && (
              <div className="rounded-lg px-3 py-2 font-mono text-[11px] leading-relaxed mt-3 max-w-md"
                   style={{
                     background: stravaRueckmeldung.ok ? '#22c55e12' : '#ef444412',
                     border: `1px solid ${stravaRueckmeldung.ok ? '#22c55e33' : '#ef444433'}`,
                     color: stravaRueckmeldung.ok ? '#22c55e' : '#ef4444',
                   }}>
                {stravaRueckmeldung.ok ? '✓ ' : '✕ '}{stravaRueckmeldung.text}
              </div>
            )}
          </div>

          {state.strava.connected ? (
            <button onClick={unlinkStrava} disabled={busy === 'strava'}
                    className="px-3 py-2 rounded-lg text-xs font-mono tracking-wide text-[var(--text-secondary)] disabled:opacity-40"
                    style={{ border: '1px solid #1e2228' }}>
              TRENNEN
            </button>
          ) : (
            <button onClick={connectStrava} disabled={busy === 'strava'}
                    className="px-3 py-2 rounded-lg text-xs font-mono font-bold tracking-wide disabled:opacity-40"
                    style={{ background: '#fc4c0220', border: '1px solid #fc4c0255', color: '#fc4c02' }}>
              {busy === 'strava' ? 'ÖFFNET…' : 'MIT STRAVA VERBINDEN'}
            </button>
          )}
        </div>

        {/* Webhook — nur Beschleunigung. Standardmäßig eingeklappt, weil der
            stündliche Abgleich ohnehin jede Aktivität holt. */}
        {webhook && (
          <details className="mt-5 pt-4" style={{ borderTop: '1px solid #1e2228' }}>
            <summary className="cursor-pointer list-none flex items-center justify-between gap-3 flex-wrap">
              <span className="flex items-center gap-2 flex-wrap">
                <span className={LABEL}>WEBHOOK</span>
                <Status ok={webhook.active}>
                  {webhook.active
                    ? 'Registriert — Einheiten kommen sofort an'
                    : 'Nicht registriert — Abgleich läuft stündlich'}
                </Status>
              </span>
              <span className="text-[10px] font-mono text-[var(--text-muted)]">
                {webhook.can_manage ? 'EINRICHTEN ▾' : 'DETAILS ▾'}
              </span>
            </summary>

            <div className="mt-4 space-y-3">
              <p className="text-xs text-[var(--text-secondary)] max-w-2xl leading-relaxed">
                Optional. Meldet neue Aktivitäten sofort, statt bis zum nächsten stündlichen
                Abgleich zu warten. Dafür muss diese App von außen erreichbar sein — ohne
                Webhook geht nichts verloren, es dauert nur länger.
              </p>

              {webhook.subscriptions?.map(s => (
                <div key={s.id} className="text-[11px] font-mono text-[var(--text-muted)] break-all">
                  aktuell: {s.callback_url}
                </div>
              ))}

              {!webhook.can_manage && (
                <p className="text-[11px] font-mono text-[var(--text-muted)] leading-relaxed">
                  Diese Einstellung gilt für die gesamte Installation und wird vom Betreiber
                  verwaltet — Strava erlaubt nur eine Registrierung je Anwendung. Für dich
                  ändert sich nichts: fehlt der Webhook, holt der stündliche Abgleich deine
                  Einheiten.
                </p>
              )}

              {webhook.can_manage && (<>
              <label className="block">
                <span className={`${LABEL} block mb-1`}>ÖFFENTLICHE ADRESSE DIESER APP</span>
                <input className={FIELD} style={FIELD_STYLE} value={publicUrl}
                       onChange={e => setPublicUrl(e.target.value)}
                       placeholder="https://dein-rechner.tailnet.ts.net" />
                <span className="text-[10px] font-mono text-[var(--text-muted)] mt-1 block">
                  Strava ruft beim Registrieren <code>{'{Adresse}'}/webhook</code> auf — sie muss in
                  diesem Moment von außen erreichbar sein.
                </span>
              </label>

              <div className="flex gap-2 flex-wrap">
                <button onClick={saveHook} disabled={busy === 'hook' || !publicUrl}
                        className="px-3 py-2 rounded-lg text-xs font-mono tracking-wide text-[#00d4ff] disabled:opacity-40"
                        style={{ background: '#00d4ff15', border: '1px solid #00d4ff33' }}>
                  {busy === 'hook' ? 'REGISTRIERT…' : (webhook.active ? 'NEU REGISTRIEREN' : 'REGISTRIEREN')}
                </button>
                {webhook.active && (
                  <button onClick={removeHook} disabled={busy === 'hook'}
                          className="px-3 py-2 rounded-lg text-xs font-mono text-[var(--text-secondary)] disabled:opacity-40"
                          style={{ border: '1px solid #1e2228' }}>
                    ENTFERNEN
                  </button>
                )}
              </div>

              {hookResult && (
                <div className="rounded-lg px-3 py-2 font-mono text-[11px] leading-relaxed"
                     style={{
                       background: hookResult.ok ? '#22c55e12' : '#ef444412',
                       border: `1px solid ${hookResult.ok ? '#22c55e33' : '#ef444433'}`,
                       color: hookResult.ok ? '#22c55e' : '#ef4444',
                     }}>
                  {hookResult.ok ? `✓ ${hookResult.message}` : `✕ ${hookResult.message}`}
                </div>
              )}

              </>)}

              {webhook.can_manage && (
              <ol className="text-[11px] font-mono text-[var(--text-muted)] space-y-1 list-decimal list-inside leading-relaxed">
                <li>
                  App von außen erreichbar machen, etwa mit{' '}
                  <code className="text-[var(--text-secondary)]">tailscale funnel --bg 8000</code> — diese Adresse
                  bleibt dauerhaft gleich, anders als bei kostenlosem ngrok.
                </li>
                <li>Adresse oben eintragen, ohne <code>/webhook</code></li>
                <li>„Registrieren" drücken — Strava prüft die Adresse sofort</li>
                <li>Schläft der Rechner, kommt nichts an; der stündliche Abgleich holt es nach</li>
              </ol>
              )}

              <p className="text-[11px] font-mono text-[var(--text-muted)] leading-relaxed">
                Strava erlaubt eine Subscription je Anwendung — sie bedient alle Athleten dieser
                Installation. Die Zuordnung zum Konto passiert über die Athleten-ID im Event.
              </p>
            </div>
          </details>
        )}
      </div>

      {/* Obsidian */}
      <form onSubmit={save} className={`${CARD} p-5 space-y-4`} style={{ borderLeft: '3px solid #7c3aed' }}>
        <div>
          <h2 className="text-lg font-black tracking-tight text-[#e8eaf0]" style={DISPLAY}>OBSIDIAN</h2>
          <p className="text-xs text-[var(--text-secondary)] mt-1 max-w-2xl leading-relaxed">
            Optional. Jede Einheit wird als Notiz in <em>deinen eigenen</em> Vault geschrieben —
            mit Struktur, Plan/Ist-Vergleich und einem Bereich für deine Reflexion.
            Was du dort schreibst, liest der Coach bei der nächsten Planung mit.
          </p>
          <div className="mt-2">
            <Status ok={state.obsidian.configured}>
              {state.obsidian.configured
                ? `Eingerichtet · Schlüssel ${state.obsidian.api_key_hint}`
                : 'Nicht eingerichtet'}
            </Status>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block sm:col-span-2">
            <span className={`${LABEL} block mb-1`}>ADRESSE DER LOCAL REST API</span>
            <input className={FIELD} style={FIELD_STYLE} value={form.base_url}
                   onChange={e => setForm({ ...form, base_url: e.target.value })}
                   placeholder="100.84.12.7" />
            <span className="block mt-1 text-[11px] font-mono text-[var(--text-muted)]">
              Genau das einfügen, was in der Tailscale-App bei deinem Rechner steht —
              etwa <span className="text-[var(--text-secondary)]">100.84.12.7</span>.
              <span className="text-[var(--text-secondary)]"> https:// </span>und der
              Port<span className="text-[var(--text-secondary)]"> :27124 </span>
              ergänzt die App selbst, sobald du speicherst oder die Verbindung testest.
            </span>
          </label>
          <label className="block">
            <span className={`${LABEL} block mb-1`}>
              API-SCHLÜSSEL {state.obsidian.configured && '(LEER = UNVERÄNDERT)'}
            </span>
            <input type="password" className={FIELD} style={FIELD_STYLE} value={form.api_key}
                   onChange={e => setForm({ ...form, api_key: e.target.value })}
                   placeholder={state.obsidian.api_key_hint || 'aus dem Plugin kopieren'}
                   autoComplete="off" />
          </label>
          <label className="block">
            <span className={`${LABEL} block mb-1`}>ORDNER IM VAULT</span>
            <input className={FIELD} style={FIELD_STYLE} value={form.vault_subdir}
                   onChange={e => setForm({ ...form, vault_subdir: e.target.value })}
                   placeholder="Training" />
          </label>
        </div>

        <div className="flex gap-2 items-center flex-wrap">
          <button type="submit" disabled={busy === 'save'}
                  className="px-4 py-2 rounded-lg text-sm font-mono font-bold disabled:opacity-40"
                  style={{ background: '#00d4ff20', border: '1px solid #00d4ff44', color: '#00d4ff' }}>
            {busy === 'save' ? 'SPEICHERT…' : 'SPEICHERN'}
          </button>
          <button type="button" onClick={check} disabled={busy === 'test'}
                  className="px-4 py-2 rounded-lg text-sm font-mono text-[var(--text-secondary)] disabled:opacity-40"
                  style={{ border: '1px solid #1e2228' }}>
            {busy === 'test' ? 'PRÜFT…' : 'VERBINDUNG TESTEN'}
          </button>
          {state.obsidian.configured && (
            <button type="button" onClick={ordnen} disabled={busy === 'ordnen'}
                    className="px-4 py-2 rounded-lg text-sm font-mono text-[var(--text-secondary)] disabled:opacity-40"
                    style={{ border: '1px solid #1e2228' }}>
              {busy === 'ordnen' ? 'SORTIERT…' : 'VAULT NEU ORDNEN'}
            </button>
          )}
          {saved && <span className="text-[11px] font-mono" style={{ color: '#22c55e' }}>✓ gespeichert</span>}
        </div>

        {ordnung && (() => {
          const schiefgegangen = !!ordnung.error || ordnung.abgebrochen
          const farbe = schiefgegangen ? '#ef4444' : '#22c55e'
          return (
            <div className="rounded-lg px-3 py-2 font-mono text-[11px] leading-relaxed"
                 style={{
                   background: `${farbe}12`,
                   border: `1px solid ${farbe}33`,
                   color: farbe,
                 }}>
              {ordnung.error ? `✕ ${ordnung.error}` : schiefgegangen ? (
                <>
                  ✕ Abgebrochen nach {ordnung.erreicht} von {ordnung.einheiten} Notizen —
                  der Vault hat nicht geantwortet.
                  {ordnung.fehler && (
                    <div className="mt-1 break-all">{ordnung.fehler}</div>
                  )}
                  <div className="text-[var(--text-secondary)] mt-1">
                    Nichts verloren: „Verbindung testen" erst grün bekommen, dann
                    hier erneut drücken.
                  </div>
                </>
              ) : (
                <>
                  ✓ {ordnung.umgezogen?.length || 0} von {ordnung.einheiten} Notizen umgezogen
                  {ordnung.plaene?.weeks > 0 && `, ${ordnung.plaene.weeks} Wochenpläne geprüft`}
                  {ordnung.umgezogen?.length > 0 && (
                    <div className="text-[var(--text-secondary)] mt-1 break-all">
                      z.B. {ordnung.umgezogen[0].von} → {ordnung.umgezogen[0].nach}
                    </div>
                  )}
                  {ordnung.umgezogen?.length === 0 && (
                    <div className="text-[var(--text-secondary)] mt-1">
                      Alle Notizen lagen schon richtig.
                    </div>
                  )}
                </>
              )}
            </div>
          )
        })()}

        {test && (
          <div className="rounded-lg px-3 py-2 font-mono text-[11px] leading-relaxed"
               style={{
                 background: test.ok ? '#22c55e12' : '#ef444412',
                 border: `1px solid ${test.ok ? '#22c55e33' : '#ef444433'}`,
                 color: test.ok ? '#22c55e' : '#ef4444',
               }}>
            {test.ok ? (
              <>
                ✓ Verbunden · Plugin {test.plugin_version}
                {test.vault_root?.length > 0 && (
                  <div className="text-[var(--text-secondary)] mt-1">
                    Oberste Ebene: {test.vault_root.join(', ')}
                  </div>
                )}
              </>
            ) : (
              <>
                ✕ {test.error}
                {test.reachable === false && (
                  <div className="text-[var(--text-secondary)] mt-1">
                    Der Reihe nach: Ist Obsidian offen und der Rechner wach? Steht
                    „Binding Host" im Plugin auf 0.0.0.0? Zeigt die Tailscale-App
                    „Connected"? Stimmt die Adresse mit der überein, die dort steht?
                  </div>
                )}
              </>
            )}
          </div>
        )}

        <details className="text-[11px] font-mono text-[var(--text-muted)]">
          <summary className="cursor-pointer hover:text-[var(--text-secondary)]">So richtest du es ein</summary>
          <p className="mt-2 leading-relaxed">
            Dein Vault liegt auf deinem Rechner, IronCoach läuft im Netz. Tailscale legt
            zwischen beide eine direkte, verschlüsselte Verbindung — ohne offenen Port,
            ohne Router-Einstellung, ohne Terminal.
          </p>
          <ol className="mt-2 space-y-1 list-decimal list-inside leading-relaxed">
            <li>In Obsidian: Einstellungen → Community-Plugins → „Local REST API" installieren und aktivieren</li>
            <li>Im selben Plugin: API-Schlüssel kopieren, „Binding Host" auf 0.0.0.0 setzen</li>
            <li>Tailscale installieren (tailscale.com/download) und mit der Einladung anmelden, die du bekommen hast</li>
            <li>In der Tailscale-App steht bei deinem Rechner eine Adresse wie 100.84.12.7 — die ist gemeint (der Eintrag „IPv4")</li>
            <li>Diese Adresse oben einfügen, dazu den Schlüssel aus Schritt 2</li>
            <li><strong>„Speichern"</strong> drücken — dabei werden https:// und der Port :27124 ergänzt</li>
            <li>„Verbindung testen" drücken; steht dort ein grünes Häkchen, ist alles fertig</li>
          </ol>
          <p className="mt-2 leading-relaxed">
            Der Abgleich läuft nur, solange dein Rechner wach und Obsidian geöffnet ist.
            Verpasst er eine Einheit, holt er sie beim nächsten Mal nach — es geht nichts
            verloren.
          </p>
        </details>
      </form>
    </div>
  )
}
