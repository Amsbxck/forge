import { useCallback, useEffect, useState } from 'react'
import {
  getIntegrations, updateObsidian, testObsidian,
  getStravaAuthUrl, disconnectStrava, confirmStrava,
  getWebhookStatus, registerWebhook, deleteWebhook,
  connectGarmin, garminAbrufen, disconnectGarmin,
  connectIntervals, intervalsAbgleichen, disconnectIntervals,
  getIntervalsAuthUrl, confirmIntervals,
} from '../services/api'
import { fehlerText } from '../utils/fehler'

import { SeitenKopf, TITEL, knopfStil, toenung } from '../components/leisten/Kachel'
const CARD = 'bg-[#111318] border border-[#1e2228] rounded-xl'
const LABEL = 'text-[9px] font-mono tracking-[0.2em] text-[var(--text-muted)]'
// Knöpfe aus `leisten/Kachel`: dieselbe Größe überall, Marke als Farbe des Hauptknopfs.
const KNOPF = 'px-3 py-1.5 rounded-lg text-[10px] font-mono font-semibold tracking-widest transition-colors hover:brightness-125 disabled:opacity-40'
const DISPLAY = { fontFamily: 'Barlow Condensed, sans-serif' }
const FIELD = 'rounded-lg px-3 py-2 text-sm font-mono text-[#e8eaf0] placeholder-[var(--text-muted)] outline-none w-full'
const FIELD_STYLE = { background: '#0d0f14', border: '1px solid #1e2228' }

function Status({ ok, children }) {
  const color = ok ? '#22c55e' : '#3a3f4a'
  return (
    <span className="inline-flex items-center gap-1.5 text-[10px] font-mono tracking-widest uppercase" style={{ color: ok ? color : 'var(--text-muted)' }}>
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: color, boxShadow: ok ? `0 0 6px ${color}88` : 'none' }} />
      {children}
    </span>
  )
}

// Garmin-Blau, wie im Garmin-Connect-Logo. Gleiche Tönung wie beim
// Strava-Knopf: Hintergrund <farbe>20, Rand <farbe>55, Schrift <farbe>.
const GARMIN = '#007CC3'

function zeitpunkt(iso) {
  if (!iso) return null
  const d = new Date(iso)
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function Rueckmeldung({ ok, children }) {
  return (
    <div className="rounded-lg px-3 py-2 font-mono text-[11px] leading-relaxed mt-3 max-w-md"
         style={{
           background: ok ? '#22c55e12' : '#ef444412',
           border: `1px solid ${ok ? '#22c55e33' : '#ef444433'}`,
           color: ok ? '#22c55e' : '#ef4444',
         }}>
      {ok ? '✓ ' : '✕ '}{children}
    </div>
  )
}

/** Garmin Connect über die Personal API.
 *
 *  Jeder Athlet trägt seinen eigenen Schlüssel ein; FORGE holt danach jeden
 *  Morgen die nächtliche HRV und jeden Sonntag Garmins Normalspanne. Der
 *  Schlüssel kommt nie zurück, nur die letzten vier Zeichen.
 */
function GarminKachel({ zustand, onChange }) {
  const [schluessel, setSchluessel] = useState('')
  const [busy, setBusy] = useState(null)
  const [rueckmeldung, setRueckmeldung] = useState(null)
  const verbunden = zustand?.configured
  // Bei einem Schlüsselfehler (abgelaufen, gelöscht, nicht mehr lesbar)
  // kommt das Feld zurück: Der Athlet soll den Schlüssel an Ort und Stelle
  // ersetzen können. Bei einem vorübergehenden Fehler (429, Garmin nicht
  // erreichbar) nicht — ein neuer Schlüssel hilft dann nicht, und das Feld
  // legte nahe, der alte sei kaputt.
  const feldZeigen = !verbunden || zustand?.fehler_art === 'schluessel'

  const zusammenfassung = (e) => {
    if (!e) return ''
    const teile = [`${e.neu} neue Werte`, `${e.aktualisiert} aktualisiert`]
    if (e.spanne_uebernommen === true) teile.push('Normalspanne übernommen')
    if (e.spanne_uebernommen === false) {
      teile.push('Normalspanne folgt, sobald Garmin sie gelernt hat (die ersten etwa drei Wochen)')
    }
    return teile.join(' · ')
  }

  const verbinden = async (ev) => {
    ev.preventDefault()
    if (!schluessel.trim()) return
    setBusy('verbinden'); setRueckmeldung(null)
    try {
      const { data } = await connectGarmin(schluessel.trim())
      setSchluessel('')
      onChange(data)
      // Ein Fehler beim ersten Abruf steht als `letzter_fehler` schon in der
      // roten Box der Kachel. Eine eigene Rückmeldung zeigte ihn doppelt.
      if (data.ergebnis?.ok !== false) {
        setRueckmeldung({ ok: true, text: `Garmin ist verbunden. ${zusammenfassung(data.ergebnis)}` })
      }
    } catch (err) {
      setRueckmeldung({ ok: false, text: fehlerText(err, 'Verbinden fehlgeschlagen') })
    } finally { setBusy(null) }
  }

  const abrufen = async () => {
    setBusy('abrufen'); setRueckmeldung(null)
    try {
      const { data } = await garminAbrufen()
      onChange(data)
      // Ein Fehler steht danach ohnehin als rote Box in der Kachel.
      if (data.ergebnis?.ok !== false) {
        setRueckmeldung({ ok: true, text: zusammenfassung(data.ergebnis) })
      }
    } catch (err) {
      setRueckmeldung({ ok: false, text: fehlerText(err, 'Abruf fehlgeschlagen') })
    } finally { setBusy(null) }
  }

  const trennen = async () => {
    if (!confirm('Garmin trennen? Bereits geholte HRV-Werte bleiben erhalten.')) return
    setBusy('trennen'); setRueckmeldung(null)
    try {
      const { data } = await disconnectGarmin()
      onChange(data)
    } catch (err) {
      setRueckmeldung({ ok: false, text: fehlerText(err, 'Trennen fehlgeschlagen') })
    } finally { setBusy(null) }
  }

  return (
    // Getönt in der Markenfarbe statt eines Streifens am linken Rand — wie
    // die Kacheln im Dashboard.
    <div className={`${CARD} p-5`} style={toenung(GARMIN, 0.7)}>
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className={TITEL}>GARMIN CONNECT</h2>
          <p className="text-xs text-[var(--text-secondary)] mt-3 max-w-md leading-relaxed">
            Holt jeden Morgen deine nächtliche HRV und jeden Sonntag deine Normalspanne
            direkt aus Garmin Connect. Dafür brauchst du einen persönlichen API-Schlüssel.
          </p>
          <div className="mt-3">
            <Status ok={verbunden && !zustand?.letzter_fehler}>
              {verbunden ? `Connected · key ${zustand.api_key_hint}` : 'Not connected'}
            </Status>
          </div>
          {verbunden && (
            <div className="text-[9px] font-mono tracking-widest text-[var(--text-muted)] mt-1.5">
              LAST FETCH {zeitpunkt(zustand.letzter_abruf) || '—'}
            </div>
          )}
          {zustand?.letzter_fehler && <Rueckmeldung ok={false}>{zustand.letzter_fehler}</Rueckmeldung>}
          {rueckmeldung && <Rueckmeldung ok={rueckmeldung.ok}>{rueckmeldung.text}</Rueckmeldung>}
          {/* Unabhängig davon, ob schon verbunden: Der Text oben verspricht
              den Abruf jeden Morgen, auch vor dem Verbinden. Ohne Verbindung
              gibt es den Knopf „Jetzt abrufen" noch nicht, also auch keinen
              Verweis darauf. */}
          {zustand?.sync_aktiv === false && (
            <p className="text-[11px] font-mono text-[var(--text-muted)] mt-2 max-w-md leading-relaxed">
              Der automatische Abruf ist auf dem Server nicht eingeschaltet.
              {verbunden
                ? ' ‚Fetch now‘ funktioniert trotzdem.'
                : ' Nach dem Verbinden kannst du von Hand abrufen.'}
            </p>
          )}
        </div>

        {verbunden && (
          <div className="flex gap-2 flex-wrap">
            <button onClick={abrufen} disabled={!!busy}
                    className={KNOPF}
                    style={knopfStil('haupt', GARMIN)}>
              {busy === 'abrufen' ? 'FETCHING…' : 'FETCH NOW'}
            </button>
            <button onClick={trennen} disabled={!!busy}
                    className={KNOPF}
                    style={knopfStil('leise')}>
              DISCONNECT
            </button>
          </div>
        )}
      </div>

      {feldZeigen && (
        <form onSubmit={verbinden} className="mt-4 space-y-3">
          <label className="block max-w-md">
            <span className={`${LABEL} block mb-1`}>
              API KEY {verbunden && '(ENTER A NEW KEY)'}
            </span>
            <input type="password" className={FIELD} style={FIELD_STYLE} value={schluessel}
                   onChange={e => setSchluessel(e.target.value)}
                   placeholder="aus Garmin Connect kopieren" autoComplete="off" />
          </label>
          <button type="submit" disabled={!!busy || !schluessel.trim()}
                  className={KNOPF}
                  style={knopfStil('haupt', GARMIN)}>
            {busy === 'verbinden' ? 'CONNECTING…' : 'CONNECT'}
          </button>

          <details className="text-[11px] font-mono text-[var(--text-muted)]">
            <summary className="cursor-pointer hover:text-[var(--text-secondary)]">So bekommst du den Schlüssel</summary>
            <ol className="mt-2 space-y-1 list-decimal list-inside leading-relaxed">
              <li>
                In Garmin Connect im Browser anmelden und{' '}
                <span className="text-[var(--text-secondary)]">connect.garmin.com/app/settings/personalApiToken</span>{' '}
                öffnen.
              </li>
              <li>„Create Key" wählen, die Bedingungen akzeptieren und als Ablauf <strong>1 Jahr</strong> wählen.</li>
              <li>Den Schlüssel sofort kopieren, denn Garmin zeigt ihn nur einmal.</li>
              <li>Hier einfügen und „Verbinden" drücken.</li>
              <li>
                Läuft der Schlüssel ab, schickt Garmin eine Woche vorher eine Mail. Dann einen
                neuen anlegen und hier eintragen.
              </li>
            </ol>
          </details>
        </form>
      )}
    </div>
  )
}

// Eigene Farbe für intervals.icu, abseits der Sportfarben und von Strava,
// Garmin und Obsidian.
const INTERVALS = '#5b8def'

/** intervals.icu: die geplanten Läufe und Radeinheiten als Workout auf die Geräte.
 *
 *  Garmin nimmt selbst nichts an (Personal API nur lesend, Connect
 *  importiert keine Workout-Dateien). intervals.icu schon, und von dort
 *  gehen die Workouts zu dem, was der Athlet dort verbunden hat: Garmin,
 *  Wahoo oder beides. Das richtet jeder bei intervals.icu selbst ein. Zwei Wege: der Knopf (OAuth,
 *  sobald intervals.icu die App freigeschaltet hat) oder ID und Schlüssel.
 *  Gesendet wird danach von selbst, nach jeder Planänderung.
 */
function IntervalsKachel({ zustand, rueckmeldungAussen, onChange }) {
  const [athleteId, setAthleteId] = useState('')
  const [schluessel, setSchluessel] = useState('')
  const [busy, setBusy] = useState(null)
  const [rueckmeldung, setRueckmeldung] = useState(null)
  const verbunden = zustand?.configured
  const meldung = rueckmeldung || rueckmeldungAussen

  const zaehlung = (e) => {
    if (!e) return ''
    const teile = []
    if (e.angelegt) teile.push(`${e.angelegt} neu`)
    if (e.ersetzt) teile.push(`${e.ersetzt} aktualisiert`)
    if (e.geloescht) teile.push(`${e.geloescht} entfernt`)
    return teile.length ? teile.join(' · ') : 'Alles schon aktuell.'
  }

  const oauth = async () => {
    setBusy('oauth'); setRueckmeldung(null)
    try {
      const { data } = await getIntervalsAuthUrl()
      window.location.href = data.auth_url
    } catch (err) {
      setRueckmeldung({ ok: false, text: fehlerText(err, 'Verbindung konnte nicht gestartet werden') })
      setBusy(null)
    }
  }

  const verbinden = async (ev) => {
    ev.preventDefault()
    if (!athleteId.trim() || !schluessel.trim()) return
    setBusy('verbinden'); setRueckmeldung(null)
    try {
      const { data } = await connectIntervals(athleteId.trim(), schluessel.trim())
      setSchluessel('')
      onChange(data)
      setRueckmeldung({ ok: true, text: 'intervals.icu ist verbunden. Die Workouts dieser und der nächsten Woche gehen gerade raus.' })
    } catch (err) {
      setRueckmeldung({ ok: false, text: fehlerText(err, 'Verbinden fehlgeschlagen') })
    } finally { setBusy(null) }
  }

  const abgleichen = async () => {
    setBusy('abgleich'); setRueckmeldung(null)
    try {
      const { data } = await intervalsAbgleichen()
      onChange(data)
      if (!data.ergebnis?.fehler) setRueckmeldung({ ok: true, text: zaehlung(data.ergebnis) })
    } catch (err) {
      setRueckmeldung({ ok: false, text: fehlerText(err, 'Abgleich fehlgeschlagen') })
    } finally { setBusy(null) }
  }

  const trennen = async () => {
    if (!confirm('intervals.icu trennen? Die kommenden FORGE-Workouts werden dort und damit auch auf Uhr und Radcomputer entfernt.')) return
    setBusy('trennen'); setRueckmeldung(null)
    try {
      const { data } = await disconnectIntervals()
      onChange(data)
      if (data.aufgeraeumt === false) {
        setRueckmeldung({ ok: false, text: 'Getrennt. Die kommenden Workouts konnten bei intervals.icu nicht entfernt werden, bitte dort von Hand löschen.' })
      }
    } catch (err) {
      setRueckmeldung({ ok: false, text: fehlerText(err, 'Trennen fehlgeschlagen') })
    } finally { setBusy(null) }
  }

  return (
    <div className={`${CARD} p-5`} style={toenung(INTERVALS, 0.7)}>
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className={TITEL}>INTERVALS.ICU · TO GARMIN & WAHOO</h2>
          <p className="text-xs text-[var(--text-secondary)] mt-3 max-w-md leading-relaxed">
            Schickt deine geplanten Läufe (mit Ziel-Pace) und Radeinheiten (mit Watt) als
            Workout an intervals.icu. Von dort landen sie auf der Garmin-Uhr oder dem
            Wahoo, je nachdem, was du dort verbindest. Nach jeder Planänderung von selbst.
          </p>
          <div className="mt-3">
            <Status ok={verbunden && !zustand?.letzter_fehler}>
              {verbunden
                ? `Connected · ${zustand.athlete_id}${zustand.weg === 'schluessel' ? ` · key ${zustand.api_key_hint}` : ''}`
                : 'Not connected'}
            </Status>
          </div>
          {verbunden && (
            <div className="text-[9px] font-mono tracking-widest text-[var(--text-muted)] mt-1.5">
              LAST SYNC {zeitpunkt(zustand.letzter_abgleich) || '—'}
            </div>
          )}
          {zustand?.letzter_fehler && <Rueckmeldung ok={false}>{zustand.letzter_fehler}</Rueckmeldung>}
          {meldung && <Rueckmeldung ok={meldung.ok}>{meldung.text}</Rueckmeldung>}
        </div>

        {verbunden ? (
          <div className="flex gap-2 flex-wrap">
            <button onClick={abgleichen} disabled={!!busy} className={KNOPF}
                    style={knopfStil('haupt', INTERVALS)}>
              {busy === 'abgleich' ? 'SYNCING…' : 'SYNC NOW'}
            </button>
            <button onClick={trennen} disabled={!!busy} className={KNOPF} style={knopfStil('leise')}>
              DISCONNECT
            </button>
          </div>
        ) : zustand?.oauth_bereit && (
          <button onClick={oauth} disabled={!!busy} className={KNOPF}
                  style={knopfStil('haupt', INTERVALS)}>
            {busy === 'oauth' ? 'OPENING…' : 'CONNECT INTERVALS.ICU'}
          </button>
        )}
      </div>

      {!verbunden && (
        <details className="mt-4" open={!zustand?.oauth_bereit}>
          <summary className="text-[11px] font-mono text-[var(--text-muted)] cursor-pointer hover:text-[var(--text-secondary)]">
            {zustand?.oauth_bereit ? 'Oder mit API-Schlüssel verbinden' : 'Mit API-Schlüssel verbinden'}
          </summary>
          <form onSubmit={verbinden} className="mt-3 space-y-3">
            <div className="grid sm:grid-cols-[10rem_minmax(0,1fr)] gap-3 max-w-md">
              <label className="block">
                <span className={`${LABEL} block mb-1`}>ATHLETE ID</span>
                <input className={FIELD} style={FIELD_STYLE} value={athleteId}
                       onChange={e => setAthleteId(e.target.value)} placeholder="i12345" autoComplete="off" />
              </label>
              <label className="block">
                <span className={`${LABEL} block mb-1`}>API KEY</span>
                <input type="password" className={FIELD} style={FIELD_STYLE} value={schluessel}
                       onChange={e => setSchluessel(e.target.value)}
                       placeholder="aus intervals.icu kopieren" autoComplete="off" />
              </label>
            </div>
            <button type="submit" disabled={!!busy || !athleteId.trim() || !schluessel.trim()}
                    className={KNOPF} style={knopfStil('haupt', INTERVALS)}>
              {busy === 'verbinden' ? 'CONNECTING…' : 'CONNECT'}
            </button>
          </form>
        </details>
      )}

      <details className="text-[11px] font-mono text-[var(--text-muted)] mt-4">
        <summary className="cursor-pointer hover:text-[var(--text-secondary)]">So richtest du es ein</summary>
        <ol className="mt-2 space-y-1 list-decimal list-inside leading-relaxed max-w-md">
          <li>Ein kostenloses Konto bei intervals.icu anlegen.</li>
          <li>
            Dort unter Settings → Connections Garmin und/oder Wahoo verbinden und
            jeweils <strong> „Upload planned workouts"</strong> einschalten. Ohne das
            bleiben die Workouts in intervals.icu und kommen nie aufs Gerät.
          </li>
          {!zustand?.oauth_bereit && (
            <li>
              Unter Settings → Developer Settings die Athleten-ID ablesen und einen
              API-Schlüssel erzeugen, beides hier eintragen.
            </li>
          )}
          <li>
            Gesendet werden Läufe und Radeinheiten ab heute, ein Koppeltraining als
            zwei Workouts (Rad, dann Lauf). Rennen nicht: Dort trainierst du ohne Workout.
          </li>
        </ol>
      </details>
    </div>
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
  // Ergebnis der Strava-Freigabe, aus der Adresszeile gelesen.
  const [stravaRueckmeldung, setStravaRueckmeldung] = useState(null)
  const [intervalsRueckmeldung, setIntervalsRueckmeldung] = useState(null)

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
    // Die Freigabe wird erst mit dem angemeldeten Konto wirksam. Schickt
    // jemand einen fremden Freigabelink, passt das Konto nicht, und es wird
    // nichts verbunden.
    if (stand === 'bestaetigen') {
      window.history.replaceState({}, '', window.location.pathname)
      confirmStrava(p.get('vorgang'))
        .then(({ data }) => {
          setStravaRueckmeldung({
            ok: true,
            text: data.historie
              ? 'Strava ist verbunden. Deine Einheiten der letzten drei Monate '
                + 'werden gerade geholt — das dauert einen Moment und läuft im '
                + 'Hintergrund weiter. Neue Aktivitäten kommen ab jetzt von selbst an.'
              : 'Strava ist verbunden. Neue Aktivitäten kommen ab jetzt von selbst an.',
          })
          load()
        })
        .catch(err => setStravaRueckmeldung({
          ok: false,
          text: typeof err.response?.data?.detail === 'string'
            ? err.response.data.detail
            : 'Die Verbindung mit Strava konnte nicht abgeschlossen werden.',
        }))
      return
    }
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

  // Rückkehr aus der Freigabe bei intervals.icu, wie bei Strava: erst mit
  // dem angemeldeten Konto bestätigen, dann ist verbunden.
  useEffect(() => {
    const p = new URLSearchParams(window.location.search)
    const stand = p.get('intervals')
    if (!stand) return
    window.history.replaceState({}, '', window.location.pathname)
    if (stand !== 'bestaetigen') {
      setIntervalsRueckmeldung({ ok: false, text: p.get('grund') || 'Die Verbindung mit intervals.icu ist fehlgeschlagen.' })
      return
    }
    confirmIntervals(p.get('vorgang'))
      .then(() => {
        setIntervalsRueckmeldung({ ok: true, text: 'intervals.icu ist verbunden. Die Workouts dieser und der nächsten Woche gehen gerade raus.' })
        load()
      })
      .catch(err => setIntervalsRueckmeldung({
        ok: false, text: fehlerText(err, 'Die Verbindung mit intervals.icu konnte nicht abgeschlossen werden.'),
      }))
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
      setError(fehlerText(err, 'Speichern fehlgeschlagen'))
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
      setTest({ ok: false, error: fehlerText(err, 'Test fehlgeschlagen') })
    } finally { setBusy(null) }
  }

  const saveHook = async () => {
    setBusy('hook'); setHookResult(null)
    try {
      const { data } = await registerWebhook(publicUrl || undefined)
      setHookResult({ ok: true, message: `Registriert auf ${data.callback_url}` })
      await load()
    } catch (err) {
      setHookResult({ ok: false, message: fehlerText(err, 'Registrierung fehlgeschlagen') })
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
      setHookResult({ ok: false, message: fehlerText(err, 'Entfernen fehlgeschlagen') })
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
      <SeitenKopf titel="CONNECTIONS" />

      {error && (
        <div className="rounded-lg px-3 py-2 font-mono text-xs"
             style={{ background: '#ef444415', border: '1px solid #ef444430', color: '#ef4444' }}>
          {error}
        </div>
      )}

      {/* Strava */}
      <div className={`${CARD} p-5`} style={toenung('#fc4c02', 0.7)}>
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h2 className={TITEL}>STRAVA</h2>
            <p className="text-xs text-[var(--text-secondary)] mt-3 max-w-md leading-relaxed">
              Liefert deine Einheiten samt Runden und Leistungsdaten. Ohne Verbindung
              bleibt nur der manuelle Upload von FIT-Dateien.
            </p>
            <div className="mt-3">
              <Status ok={state.strava.connected}>
                {state.strava.connected
                  ? `Connected · athlete ${state.strava.athlete_id}`
                  : 'Not connected'}
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
                    className={KNOPF}
                    style={knopfStil('leise')}>
              DISCONNECT
            </button>
          ) : (
            <button onClick={connectStrava} disabled={busy === 'strava'}
                    className={KNOPF}
                    style={knopfStil('haupt', '#fc4c02')}>
              {busy === 'strava' ? 'OPENING…' : 'CONNECT STRAVA'}
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
                    ? 'Registered · sessions arrive instantly'
                    : 'Not registered · hourly sync'}
                </Status>
              </span>
              <span className="text-[10px] font-mono text-[var(--text-muted)]">
                {webhook.can_manage ? 'SET UP ▾' : 'DETAILS ▾'}
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
                <span className={`${LABEL} block mb-1`}>PUBLIC ADDRESS OF THIS APP</span>
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
                        className={KNOPF}
                        style={knopfStil('haupt')}>
                  {busy === 'hook' ? 'REGISTERING…' : (webhook.active ? 'RE-REGISTER' : 'REGISTER')}
                </button>
                {webhook.active && (
                  <button onClick={removeHook} disabled={busy === 'hook'}
                          className={KNOPF}
                          style={knopfStil('leise')}>
                    REMOVE
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

      {/* Garmin Connect — direkt unter Strava, gleicher Aufbau. */}
      <GarminKachel zustand={state.garmin}
                    onChange={(daten) => setState(s => ({ ...s, ...daten }))} />

      {/* intervals.icu direkt unter Garmin: Es bringt die Workouts auf dieselbe Uhr (und aufs Wahoo). */}
      <IntervalsKachel zustand={state.intervals} rueckmeldungAussen={intervalsRueckmeldung}
                       onChange={(daten) => setState(s => ({ ...s, ...daten }))} />

      {/* Obsidian */}
      <form onSubmit={save} className={`${CARD} p-5 space-y-4`} style={toenung('#7c3aed', 0.7)}>
        <div>
          <h2 className={TITEL}>OBSIDIAN</h2>
          <p className="text-xs text-[var(--text-secondary)] mt-3 max-w-2xl leading-relaxed">
            Optional. Jede Einheit wird als Notiz in <em>deinen eigenen</em> Vault geschrieben —
            mit Struktur, Plan/Ist-Vergleich und einem Bereich für deine Reflexion.
            Was du dort schreibst, liest der Coach bei der nächsten Planung mit.
          </p>
          <div className="mt-3">
            <Status ok={state.obsidian.configured}>
              {state.obsidian.configured
                ? `Set up · key ${state.obsidian.api_key_hint}`
                : 'Not set up'}
            </Status>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block sm:col-span-2">
            <span className={`${LABEL} block mb-1`}>LOCAL REST API ADDRESS</span>
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
              API KEY {state.obsidian.configured && '(EMPTY = UNCHANGED)'}
            </span>
            <input type="password" className={FIELD} style={FIELD_STYLE} value={form.api_key}
                   onChange={e => setForm({ ...form, api_key: e.target.value })}
                   placeholder={state.obsidian.api_key_hint || 'aus dem Plugin kopieren'}
                   autoComplete="off" />
          </label>
          <label className="block">
            <span className={`${LABEL} block mb-1`}>VAULT FOLDER</span>
            <input className={FIELD} style={FIELD_STYLE} value={form.vault_subdir}
                   onChange={e => setForm({ ...form, vault_subdir: e.target.value })}
                   placeholder="Training" />
          </label>
        </div>

        <div className="flex gap-2 items-center flex-wrap">
          <button type="submit" disabled={busy === 'save'}
                  className={KNOPF}
                  style={knopfStil('haupt')}>
            {busy === 'save' ? 'SAVING…' : 'SAVE'}
          </button>
          <button type="button" onClick={check} disabled={busy === 'test'}
                  className={KNOPF}
                  style={knopfStil('leise')}>
            {busy === 'test' ? 'TESTING…' : 'TEST CONNECTION'}
          </button>
          {saved && <span className="text-[11px] font-mono" style={{ color: '#22c55e' }}>✓ saved</span>}
        </div>


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
            Dein Vault liegt auf deinem Rechner, FORGE läuft im Netz. Tailscale legt
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
