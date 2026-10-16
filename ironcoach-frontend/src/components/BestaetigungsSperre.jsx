import { useCallback, useEffect, useState } from 'react'
import { getMe } from '../services/api'
import Modal from './Modal'
import { SendeStatus, useErneutSenden } from './EmailBestaetigung'

/** Statt der App: ein Fenster, das um die Bestätigung der E-Mail bittet.
 *
 *  Vorher kam ein unbestätigter Nutzer in die App und sah oben einen Hinweis.
 *  Scheiterte die Willkommensmail beim Mailanbieter, stand er dann in einer
 *  App, in der nichts weiterging — das Einstiegsfenster wartete auf eine
 *  Bestätigung, die nie kommen konnte.
 *
 *  Hinter dem Fenster wird nichts geladen: Die App baut sich erst auf, wenn
 *  die Bestätigung da ist. Der Link aus der Mail (`/verify`) und das Abmelden
 *  funktionieren weiter — beide liegen vor dieser Sperre.
 *
 *  Ob inzwischen bestätigt wurde, wird beim Zurückkehren in den Tab geprüft:
 *  Wer den Link in einem anderen Tab öffnet und hierher zurückkommt, soll
 *  nicht neu laden müssen.
 */
export default function BestaetigungsSperre({ konto, onBestaetigt, onAbmelden }) {
  const { status, detail, senden } = useErneutSenden()
  const [pruefe, setPruefe] = useState(false)
  const [nochNicht, setNochNicht] = useState(false)
  const [mailStatus, setMailStatus] = useState(konto?.verify_mail_status ?? null)

  const nachsehen = useCallback(async (vonHand = false) => {
    if (vonHand) setPruefe(true)
    try {
      const { data } = await getMe()
      setMailStatus(data.verify_mail_status ?? null)
      if (!data.bestaetigung_noetig) {
        onBestaetigt(data)
        return
      }
      if (vonHand) setNochNicht(true)
    } catch {
      // Abgelaufene Anmeldung: das übernimmt der 401-Handler der App.
    } finally {
      if (vonHand) setPruefe(false)
    }
  }, [onBestaetigt])

  useEffect(() => {
    nachsehen()
    const sichtbar = () => { if (document.visibilityState === 'visible') nachsehen() }
    document.addEventListener('visibilitychange', sichtbar)
    window.addEventListener('focus', sichtbar)
    return () => {
      document.removeEventListener('visibilitychange', sichtbar)
      window.removeEventListener('focus', sichtbar)
    }
  }, [nachsehen])

  const neuSenden = async () => {
    setNochNicht(false)
    const data = await senden()
    if (!data) return
    // Schon in einem anderen Tab bestätigt: keine Mail verschickt — direkt
    // in die App, statt „Neue Mail ist unterwegs" anzuzeigen.
    if (data.status === 'bereits_bestaetigt') {
      await nachsehen(true)
      return
    }
    setMailStatus(data.angenommen ? 'gesendet' : 'fehlgeschlagen')
  }

  // Ist bisher keine Mail angekommen? Dann darf der Text nicht „Wir haben
  // einen Link geschickt" sagen — weder nach einer gescheiterten ersten Mail
  // noch nach einem gescheiterten erneuten Versuch.
  const keineMailRaus = mailStatus === 'fehlgeschlagen'
    || status === 'abgelehnt' || status === 'fehler'
  // Den roten Satz im Text nur, solange noch nichts erneut angefordert
  // wurde — danach sagt die Statuszeile darunter dasselbe.
  const ersteGescheitert = keineMailRaus && status === null

  return (
    <div className="min-h-screen flex flex-col items-center justify-start pt-10"
         style={{ background: '#07080f' }}>
      <div className="font-bold tracking-[0.3em] text-[var(--text-muted)] text-sm"
           style={{ fontFamily: 'Barlow Condensed, sans-serif' }}>
        FORGE
      </div>

      <Modal open dismissible={false} title="E-MAIL BESTÄTIGEN" align="center">
        <div className="space-y-3">
          {/* Zwei Fassungen, damit sich Text und Lage nicht widersprechen:
              „Wir haben geschickt" neben „konnte nicht verschickt werden"
              las sich wie ein Fehler der App. */}
          {keineMailRaus ? (
            <p className="text-[13px] text-[var(--text-secondary)] leading-relaxed">
              Bitte bestätige deine Adresse{' '}
              <span className="font-mono text-[var(--text-primary)] break-all">{konto?.email}</span>.{' '}
              {ersteGescheitert && (
                <>
                  <span style={{ color: '#ef4444' }}>
                    Die erste Mail mit dem Link konnte nicht verschickt werden — fordere
                    unten eine neue an.
                  </span>{' '}
                </>
              )}
              Erst danach geht es weiter — Ziel, Zonen und Testwoche.
            </p>
          ) : (
            <p className="text-[13px] text-[var(--text-secondary)] leading-relaxed">
              Wir haben einen Link an{' '}
              <span className="font-mono text-[var(--text-primary)] break-all">{konto?.email}</span>{' '}
              geschickt. Erst danach geht es weiter — Ziel, Zonen und Testwoche.
              Schau auch im Spam-Ordner nach.
            </p>
          )}

          <SendeStatus status={status} detail={detail} />

          {nochNicht && status !== 'sendet' && (
            <p className="text-[12px] font-mono text-[var(--text-muted)]">
              Noch nicht bestätigt — öffne den Link aus der Mail und komm dann hierher zurück.
            </p>
          )}

          <div className="flex flex-wrap gap-2 pt-1">
            <button
              onClick={neuSenden}
              disabled={status === 'sendet'}
              className="px-3 py-2 rounded-lg text-[12px] font-mono tracking-wide disabled:opacity-40"
              style={{ background: '#f59e0b20', border: '1px solid #f59e0b44', color: '#f59e0b' }}
            >
              {status === 'sendet' ? 'SENDET…' : 'ERNEUT SENDEN'}
            </button>
            <button
              onClick={() => nachsehen(true)}
              disabled={pruefe}
              className="px-3 py-2 rounded-lg text-[12px] font-mono tracking-wide disabled:opacity-40"
              style={{ background: '#00d4ff15', border: '1px solid #00d4ff33', color: '#00d4ff' }}
            >
              {pruefe ? 'PRÜFT…' : 'ICH HABE BESTÄTIGT'}
            </button>
            <button
              onClick={onAbmelden}
              className="px-3 py-2 rounded-lg text-[12px] font-mono tracking-wide text-[var(--text-secondary)] ml-auto"
              style={{ border: '1px solid #1e2228' }}
            >
              ABMELDEN
            </button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
