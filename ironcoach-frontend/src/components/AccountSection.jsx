import { useEffect, useState } from 'react'
import {
  adminVerifyEmail, deleteAccount, exportAccount, getMe, logoutEverywhere,
  resendVerification, setToken,
} from '../services/api'
import Modal from './Modal'
import { isoTag } from '../utils/dates'

const CARD = 'bg-[#111318] border border-[#1e2228] rounded-xl'
const LABEL = 'text-[10px] font-mono tracking-widest text-[var(--text-secondary)] block mb-1'
const FIELD = 'rounded-lg px-3 py-2 text-sm font-mono text-[#e8eaf0] placeholder-[var(--text-muted)] outline-none w-full'
const FIELD_STYLE = { background: '#0d0f17', border: '1px solid #1e2228' }

function fehlerText(err, fallback) {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail[0]?.msg || fallback
  return fallback
}

/** Konto verwalten: Bestätigung, Sitzungen, Daten mitnehmen, Konto löschen.
 *
 *  Die drei letzten Punkte sind kein Beiwerk — ohne sie ist ein Konto eine
 *  Einbahnstraße, und Auskunft wie Löschung sind bei personenbezogenen
 *  Gesundheitsdaten ohnehin Pflicht.
 */
export default function AccountSection({ onLoggedOut }) {
  const [konto, setKonto] = useState(null)
  const [hinweis, setHinweis] = useState(null)
  const [fehler, setFehler] = useState(null)
  const [busy, setBusy] = useState(false)
  const [loeschDialog, setLoeschDialog] = useState(false)
  const [loeschForm, setLoeschForm] = useState({ password: '', confirm: '' })

  useEffect(() => { getMe().then(({ data }) => setKonto(data)).catch(() => {}) }, [])

  const bestaetigungSenden = async () => {
    setBusy(true); setFehler(null); setHinweis(null)
    try {
      const { data } = await resendVerification()
      if (data.status === 'nicht_konfiguriert') {
        setFehler('Auf diesem Server ist kein Mailversand eingerichtet — eine Bestätigungsmail kann nicht verschickt werden.')
      } else if (data.status === 'bereits_bestaetigt') {
        setHinweis('Deine Adresse ist bereits bestätigt.')
        setKonto(k => ({ ...k, email_verified: true }))
      } else if (data.angenommen) {
        setHinweis(`Bestätigungsmail verschickt. Der Link gilt ${data.gueltig_stunden || 48} Stunden.`)
      } else {
        // Vorher stand hier in jedem Fall „verschickt" — auch wenn der
        // Mailanbieter abgelehnt hatte.
        setFehler('Die Mail konnte nicht verschickt werden. Versuche es in ein paar Minuten erneut.')
      }
    } catch (err) { setFehler(fehlerText(err, 'Versand fehlgeschlagen')) }
    finally { setBusy(false) }
  }

  // Notschalter für Admins: ein Konto von Hand bestätigen, wenn der
  // Mailanbieter ablehnt und jemand deshalb vor dem Bestätigungsfenster
  // festsitzt. Die Produktionsdatenbank ist von außen nicht erreichbar —
  // ohne diesen Weg bliebe er ausgesperrt, bis der Versand wieder läuft.
  const [fremdeAdresse, setFremdeAdresse] = useState('')
  // Eigene Rückmeldung direkt unter dem Feld — die allgemeine steht unter den
  // Kontoknöpfen und auf dem Telefon weit weg von der Eingabe.
  const [adminMeldung, setAdminMeldung] = useState(null)   // { ok, text }
  const kontoBestaetigen = async () => {
    const adresse = fremdeAdresse.trim()
    if (!adresse) return
    setBusy(true); setAdminMeldung(null)
    try {
      const { data } = await adminVerifyEmail(adresse)
      setAdminMeldung({
        ok: true,
        text: data.status === 'bereits_bestaetigt'
          ? `${data.email} war bereits bestätigt.`
          : `${data.email} ist jetzt bestätigt und kommt in die App.`,
      })
      setFremdeAdresse('')
    } catch (err) {
      setAdminMeldung({ ok: false, text: fehlerText(err, 'Bestätigen fehlgeschlagen') })
    } finally { setBusy(false) }
  }

  const datenLaden = async () => {
    setBusy(true); setFehler(null)
    try {
      const { data } = await exportAccount()
      // Als Datei anbieten statt anzuzeigen — es sind mehrere Megabyte JSON.
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      )
      const a = document.createElement('a')
      a.href = url
      a.download = `forge-daten-${isoTag(new Date())}.json`
      a.click()
      URL.revokeObjectURL(url)
      setHinweis('Datei wurde heruntergeladen.')
    } catch (err) { setFehler(fehlerText(err, 'Export fehlgeschlagen')) }
    finally { setBusy(false) }
  }

  const ueberallAbmelden = async () => {
    setBusy(true)
    try {
      await logoutEverywhere()
      setToken(null)
      onLoggedOut?.()
    } finally { setBusy(false) }
  }

  const kontoLoeschen = async () => {
    setBusy(true); setFehler(null)
    try {
      await deleteAccount(loeschForm.password, loeschForm.confirm)
      setToken(null)
      onLoggedOut?.()
    } catch (err) {
      setFehler(fehlerText(err, 'Löschen fehlgeschlagen'))
      setBusy(false)
    }
  }

  if (!konto) return null

  return (
    <div className={`${CARD} p-5`}>
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <span className="text-xs font-mono tracking-[0.25em] text-[var(--text-secondary)]">ACCOUNT</span>
        <span className="text-[10px] font-mono tracking-widest text-[var(--text-muted)]">{konto.email}</span>
      </div>

      {/* Unbestätigte Adresse: sichtbar, aber nicht blockierend. */}
      {!konto.email_verified && (
        <div className="mt-4 rounded-lg px-3 py-2.5 flex items-center justify-between gap-3 flex-wrap"
             style={{ background: '#f59e0b12', border: '1px solid #f59e0b33' }}>
          <span className="text-xs" style={{ color: '#f59e0b' }}>
            E-Mail-Adresse noch nicht bestätigt.
          </span>
          <button onClick={bestaetigungSenden} disabled={busy}
                  className="text-[10px] font-mono tracking-wide px-3 py-1.5 rounded-lg disabled:opacity-40"
                  style={{ background: '#f59e0b18', border: '1px solid #f59e0b40', color: '#f59e0b' }}>
            {busy ? '…' : 'RESEND'}
          </button>
        </div>
      )}

      {konto.is_admin && (
        <div className="mt-4 rounded-lg px-3 py-3" style={{ background: '#0d0f17', border: '1px solid #1e2228' }}>
          <label htmlFor="admin-bestaetigen" className={LABEL}>
            ADMIN · CONFIRM ACCOUNT BY HAND
          </label>
          <p className="text-[11px] text-[var(--text-muted)] leading-relaxed mb-2">
            Für den Fall, dass die Bestätigungsmail nicht ankommt und jemand
            deshalb nicht in die App kommt.
          </p>
          <div className="flex gap-2 flex-wrap">
            <input
              id="admin-bestaetigen"
              type="email"
              value={fremdeAdresse}
              onChange={e => setFremdeAdresse(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !busy) kontoBestaetigen() }}
              placeholder="adresse@beispiel.de"
              className={`${FIELD} flex-1 min-w-[12rem]`}
              style={FIELD_STYLE}
            />
            <button onClick={kontoBestaetigen} disabled={busy || !fremdeAdresse.trim()}
                    className="text-[10px] font-mono tracking-wide px-3 py-2 rounded-lg disabled:opacity-40"
                    style={{ background: '#00d4ff15', border: '1px solid #00d4ff33', color: '#00d4ff' }}>
              CONFIRM
            </button>
          </div>
          {adminMeldung && (
            <div className="text-[10px] font-mono mt-2"
                 style={{ color: adminMeldung.ok ? '#00d4ff' : '#ef4444' }}>
              {adminMeldung.text}
            </div>
          )}
        </div>
      )}

      <div className="mt-5 pt-5 border-t border-[#1e2228] grid gap-3 sm:grid-cols-3">
        <button onClick={datenLaden} disabled={busy}
                className="px-3 py-2 rounded-lg text-[11px] font-mono tracking-wide text-left disabled:opacity-40"
                style={{ background: '#0d0f17', border: '1px solid #1e2228', color: 'var(--text-secondary)' }}>
          <span className="block text-[#e8eaf0]">EXPORT DATA</span>
          <span className="text-[10px] text-[var(--text-muted)]">Alles als JSON-Datei</span>
        </button>

        <button onClick={ueberallAbmelden} disabled={busy}
                className="px-3 py-2 rounded-lg text-[11px] font-mono tracking-wide text-left disabled:opacity-40"
                style={{ background: '#0d0f17', border: '1px solid #1e2228', color: 'var(--text-secondary)' }}>
          <span className="block text-[#e8eaf0]">SIGN OUT EVERYWHERE</span>
          <span className="text-[10px] text-[var(--text-muted)]">Beendet alle Geräte</span>
        </button>

        <button onClick={() => { setLoeschDialog(true); setFehler(null) }} disabled={busy}
                className="px-3 py-2 rounded-lg text-[11px] font-mono tracking-wide text-left disabled:opacity-40"
                style={{ background: '#ef444410', border: '1px solid #ef444428', color: '#ef4444' }}>
          <span className="block">DELETE ACCOUNT</span>
          <span className="text-[10px] opacity-70">Endgültig, mit allen Daten</span>
        </button>
      </div>

      {hinweis && <div className="text-[10px] font-mono text-[#00d4ff] mt-3">{hinweis}</div>}
      {fehler && <div className="text-[10px] font-mono text-[#ef4444] mt-3">{fehler}</div>}

      <Modal
        open={loeschDialog}
        onClose={() => { setLoeschDialog(false); setLoeschForm({ password: '', confirm: '' }) }}
        title="KONTO LÖSCHEN"
        subtitle="Das lässt sich nicht rückgängig machen"
        width="max-w-sm"
      >
        <div className="space-y-4">
          <p className="text-sm text-[var(--text-secondary)] leading-relaxed">
            Alle Einheiten, Pläne, Zonen, Rennen und Reflexionen werden entfernt.
            Notes in deinem Obsidian-Vault bleiben liegen — die gehören dir und
            werden nicht angefasst.
          </p>
          <p className="text-xs font-mono text-[var(--text-muted)]">
            Exportiere vorher deine Daten, wenn du sie behalten willst.
          </p>

          <label className="block">
            <span className={LABEL}>PASSWORT</span>
            <input type="password" className={FIELD} style={FIELD_STYLE}
                   value={loeschForm.password} autoComplete="current-password"
                   onChange={e => setLoeschForm(f => ({ ...f, password: e.target.value }))} />
          </label>

          <label className="block">
            <span className={LABEL}>ZUR BESTÄTIGUNG „LÖSCHEN“ EINTIPPEN</span>
            <input className={FIELD} style={FIELD_STYLE} placeholder="LÖSCHEN"
                   value={loeschForm.confirm}
                   onChange={e => setLoeschForm(f => ({ ...f, confirm: e.target.value }))} />
          </label>

          {fehler && <div className="text-[11px] font-mono text-[#ef4444]">{fehler}</div>}

          <button onClick={kontoLoeschen} disabled={busy || !loeschForm.password}
                  className="w-full py-2 rounded-lg text-[11px] font-mono font-bold tracking-wide disabled:opacity-30"
                  style={{ background: '#ef444420', border: '1px solid #ef444444', color: '#ef4444' }}>
            {busy ? 'LÖSCHT…' : 'KONTO ENDGÜLTIG LÖSCHEN'}
          </button>
        </div>
      </Modal>
    </div>
  )
}
