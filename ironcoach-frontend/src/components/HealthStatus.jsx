import { useCallback, useEffect, useState } from 'react'
import { getHealthStatus, reportIllness, reportRecovered } from '../services/api'
import { isoTag } from '../utils/dates'
import { fehlerText } from '../utils/fehler'
import HealthIcon from './HealthIcon'
import Modal from './Modal'
import BodyMap from './BodyMap'

const LABEL = 'text-[10px] font-mono tracking-widest text-[var(--text-secondary)]'
const FIELD_STYLE = { background: '#0d0f17', border: '1px solid #1e2228' }

// Der Schweregrad bedeutet bei einer Verletzung etwas anderes als bei einem
// Infekt: dort entscheidet das Immunsystem, hier die Belastbarkeit. Mit
// Erkältungsbeschreibungen unter „Verletzung" wäre die Auswahl geraten.
const SEVERITIES = {
  illness: [
    { key: 'mild', label: 'MILD', hint: 'Schnupfen, Halskratzen — über dem Hals, kein Fieber' },
    { key: 'moderate', label: 'MODERATE', hint: 'Husten, Gliederschmerzen' },
    { key: 'severe', label: 'SEVERE', hint: 'Fieber oder ärztlich verordnete Pause' },
  ],
  injury: [
    { key: 'mild', label: 'MILD', hint: 'Schmerzfrei belastbar — nur kein harter Reiz' },
    { key: 'moderate', label: 'MODERATE', hint: 'Schmerz bei Belastung — betroffene Disziplin pausiert' },
    { key: 'severe', label: 'SEVERE', hint: 'Nicht belastbar oder ärztlich verordnete Pause' },
  ],
}

const NOTIZ_BEISPIEL = {
  illness: 'z. B. Erkältung, Magen-Darm',
  injury: 'Was ist betroffen? z. B. rechte Achillessehne',
}

const STATUS = {
  healthy: { color: '#22c55e', text: 'HEALTHY', sub: 'Training nach Plan' },
  sick: { color: '#ef4444', text: 'SICK', sub: 'Plan ausgesetzt' },
  returning: { color: '#f59e0b', text: 'COMEBACK', sub: 'Nur locker' },
}

// Die Art kommt vom Backend nur deutsch (`KIND_LABEL`), die Leiste ist
// englisch beschriftet. Unbekannte Arten fallen auf den deutschen Text zurück.
const ART_EN = { illness: 'ILLNESS', injury: 'INJURY', other: 'TIME OFF' }

const LEER_FORM = { kind: 'illness', severity: 'mild', fever: false, body_part: null, start_date: '', note: '' }

/** Meldeformular als Overlay.
 *
 *  Bewusst nicht eingebettet: auf dem Dashboard ist die Kachel dafür zu
 *  klein, und im Plan würde sie den Kalender wegschieben. So ist es an
 *  beiden Stellen dasselbe Formular.
 */
function ReportDialog({ onClose, onDone }) {
  const [form, setForm] = useState(LEER_FORM)
  const [busy, setBusy] = useState(false)
  // Vorher ohne Fehlerfang: Ein 422 oder 500 ließ den Dialog offen und
  // stumm, und man drückte noch einmal.
  const [fehler, setFehler] = useState(null)

  const senden = async () => {
    setBusy(true)
    setFehler(null)
    try {
      const { data } = await reportIllness({
        kind: form.kind,
        severity: form.severity,
        fever: form.severity === 'severe' ? form.fever : false,
        // Nur bei einer Verletzung: Eine Erkältung hat keine Körperstelle,
        // und der Endpunkt würde sie ohnehin verwerfen.
        body_part: form.kind === 'injury' ? form.body_part : null,
        start_date: form.start_date || null,
        note: form.note || null,
      })
      onDone(data)
    } catch (e) {
      setFehler(fehlerText(e, 'Die Meldung konnte nicht gespeichert werden.'))
    } finally { setBusy(false) }
  }

  return (
    <Modal
      open onClose={onClose}
      title={form.kind === 'injury' ? 'REPORT INJURY' : 'REPORT ILLNESS'}
      subtitle="Der Wochenplan wird danach neu erstellt"
      icon={<HealthIcon status="sick" kind={form.kind} size={26}
                        color={form.kind === 'injury' ? '#f59e0b' : '#ef4444'} />}
    >
      <div className="space-y-4">
        <div className="flex gap-1 p-0.5 rounded-lg" style={{ background: '#0d0f17' }}>
          {[
            { key: 'illness', label: 'ILLNESS' },
            { key: 'injury', label: 'INJURY' },
          ].map(t => (
            <button
              key={t.key} type="button"
              onClick={() => setForm(f => ({ ...f, kind: t.key, body_part: t.key === 'injury' ? f.body_part : null }))}
              className="flex-1 py-1.5 rounded-md text-[11px] font-mono tracking-wide transition-all"
              style={{
                background: form.kind === t.key ? '#00d4ff20' : 'transparent',
                color: form.kind === t.key ? '#00d4ff' : 'var(--text-muted)',
              }}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div>
          <span className={`${LABEL} block mb-1`}>SEVERITY</span>
          <div className="space-y-1">
            {SEVERITIES[form.kind].map(s => (
              <button
                key={s.key} type="button"
                onClick={() => setForm(f => ({ ...f, severity: s.key, fever: s.key === 'severe' ? f.fever : false }))}
                className="w-full text-left px-3 py-2 rounded-lg transition-all"
                style={{
                  background: form.severity === s.key ? '#00d4ff12' : '#0d0f17',
                  border: `1px solid ${form.severity === s.key ? '#00d4ff33' : '#1e2228'}`,
                }}
              >
                <div className="text-[11px] font-mono tracking-wide"
                     style={{ color: form.severity === s.key ? '#00d4ff' : '#8a909e' }}>
                  {s.label}
                </div>
                <div className="text-[10px] text-[var(--text-muted)] mt-0.5">{s.hint}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Wo es weh tut. Nur bei einer Verletzung — und ohne Zwang: Wer
            nicht zeigen kann, wo genau, meldet trotzdem. Die Vorgabe fällt
            dann allgemeiner aus, das ist besser als eine geratene Stelle. */}
        {form.kind === 'injury' && (
          <div>
            <span className={`${LABEL} block mb-2`}>WHERE? (OPTIONAL)</span>
            <BodyMap value={form.body_part}
                     onChange={stelle => setForm(f => ({ ...f, body_part: stelle }))} />
          </div>
        )}

        {/* Fieber wird getrennt abgefragt, nicht aus dem Schweregrad
            geraten: es ist die einzige Angabe, die Training vollständig
            ausschließt. */}
        {form.kind === 'illness' && form.severity === 'severe' && (
          <label className="flex items-center gap-2 cursor-pointer px-3 py-2 rounded-lg"
                 style={{ background: '#ef444410', border: '1px solid #ef444426' }}>
            <input type="checkbox" checked={form.fever}
                   onChange={e => setForm(f => ({ ...f, fever: e.target.checked }))} />
            <span className="text-xs text-[#e8eaf0]">Fieber</span>
            <span className="text-[10px] text-[var(--text-secondary)]">— dann wird kein Training geplant</span>
          </label>
        )}

        <label className="block">
          <span className={`${LABEL} block mb-1`}>SINCE (EMPTY = TODAY)</span>
          <input
            type="date" max={isoTag(new Date())}
            className="rounded-lg px-3 py-2 text-sm font-mono text-[#e8eaf0] outline-none w-full"
            style={FIELD_STYLE} value={form.start_date}
            onChange={e => setForm(f => ({ ...f, start_date: e.target.value }))}
          />
        </label>

        <label className="block">
          <span className={`${LABEL} block mb-1`}>
            {form.kind === 'injury' ? 'WHAT IS AFFECTED?' : 'NOTE (OPTIONAL)'}
          </span>
          <input
            className="rounded-lg px-3 py-2 text-sm font-mono text-[#e8eaf0] placeholder-[var(--text-muted)] outline-none w-full"
            style={FIELD_STYLE} value={form.note} placeholder={NOTIZ_BEISPIEL[form.kind]}
            onChange={e => setForm(f => ({ ...f, note: e.target.value }))}
          />
        </label>

        {fehler && (
          <div className="text-[11px] font-mono" style={{ color: '#ef4444' }}>{fehler}</div>
        )}

        <div className="flex gap-2 pt-1">
          <button
            onClick={senden} disabled={busy}
            className="flex-1 py-2 rounded-lg text-[11px] font-mono font-bold tracking-wide disabled:opacity-40"
            style={{ background: '#ef444420', border: '1px solid #ef444444', color: '#ef4444' }}
          >
            {busy ? '…' : 'REPORT & ADJUST PLAN'}
          </button>
          <button onClick={onClose}
                  className="px-4 py-2 rounded-lg text-[11px] font-mono text-[var(--text-muted)] hover:text-[var(--text-secondary)]">
            CANCEL
          </button>
        </div>
      </div>
    </Modal>
  )
}

/** Zustandsanzeige.
 *
 *  `variant="bar"` — breiter Balken über dem Wochenplan.
 *  `variant="tile"` — Kachel neben der HRV-Anzeige auf dem Dashboard.
 */
export default function HealthStatus({ variant = 'bar', onChanged }) {
  const [status, setStatus] = useState(null)
  const [dialog, setDialog] = useState(false)
  const [busy, setBusy] = useState(false)
  const [hinweis, setHinweis] = useState(null)

  const load = useCallback(async () => {
    try { setStatus((await getHealthStatus()).data) } catch { /* still */ }
  }, [])

  useEffect(() => { load() }, [load])

  const nachMeldung = async (text, antwort) => {
    setHinweis(text)
    await load()
    // Die Antwort mitgeben: Der Wochenplan verfolgt damit die Neuplanung
    // und sagt, wenn sie nicht geklappt hat.
    onChanged?.(antwort)
  }

  const gesund = async () => {
    setBusy(true)
    try {
      const { data } = await reportRecovered({})
      await nachMeldung(
        data.plan_wird_angepasst
          ? 'Willkommen zurück. Der Wiedereinstiegsplan wird erstellt.'
          : 'Willkommen zurück.',
        data,
      )
    } catch (e) {
      setHinweis(fehlerText(e, 'Gesundmeldung fehlgeschlagen.'))
    } finally { setBusy(false) }
  }

  if (!status) return null

  const stil = STATUS[status.status] || STATUS.healthy
  const event = status.event
  const kind = event?.kind
  // Eine Verletzung ist nicht „krank": andere Farbe, anderes Wort, damit die
  // Kachel nicht das Falsche behauptet.
  const verletzt = kind === 'injury' && status.status === 'sick'
  const farbe = verletzt ? '#f59e0b' : stil.color
  const zustandText = verletzt ? 'INJURED' : stil.text

  const dialogNode = dialog && (
    <ReportDialog
      onClose={() => setDialog(false)}
      onDone={async (antwort) => {
        setDialog(false)
        await nachMeldung(
          antwort?.plan_wird_angepasst
            ? 'Gemeldet. Der Wochenplan wird im Hintergrund angepasst.'
            : 'Gemeldet.',
          antwort,
        )
      }}
    />
  )

  // --- Kachel fürs Dashboard -------------------------------------------------
  if (variant === 'tile') {
    return (
      <>
        <button
          onClick={() => (status.status === 'sick' ? gesund() : setDialog(true))}
          disabled={busy}
          className="bg-[#111318] rounded-xl p-5 w-full h-full text-left relative overflow-hidden group transition-all"
          style={{ border: `1px solid ${status.status === 'healthy' ? '#1e2228' : farbe + '3a'}` }}
          title={status.status === 'sick'
            ? (verletzt ? 'Als wiederhergestellt melden' : 'Als gesund melden')
            : 'Krank oder verletzt melden'}
        >
          <div className="absolute inset-0 pointer-events-none" style={{
            background: `radial-gradient(ellipse 70% 90% at 80% 20%, ${farbe}12 0%, transparent 70%)`,
          }} />
          <div className="relative z-10 flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className={LABEL}>CONDITION</div>
              <div className="text-2xl font-black mt-1 leading-none"
                   style={{ color: farbe, fontFamily: 'Barlow Condensed, sans-serif' }}>
                {zustandText}
              </div>
              <div className="text-[10px] font-mono text-[var(--text-muted)] mt-1.5 leading-relaxed">
                {status.status === 'healthy'
                  ? 'Zum Melden klicken'
                  : status.status === 'sick'
                    ? `Seit ${event?.start_date} · klicken wenn vorbei`
                    : `Locker bis ${status.easy_until}`}
              </div>
            </div>
            <HealthIcon status={status.status} kind={kind} size={34} color={farbe} />
          </div>
        </button>
        {dialogNode}
      </>
    )
  }

  // --- Balken über dem Wochenplan --------------------------------------------
  return (
    <>
      {/* Getönt wie die Dashboard-Kacheln, statt Randstrich links und
          Lichtfleck. Gesund bleibt die Kachel neutral. */}
      <div
        className="rounded-xl px-5 py-4 relative overflow-hidden border"
        style={status.status === 'healthy'
          ? { background: '#111318', borderColor: '#1e2228' }
          : {
              background: `linear-gradient(115deg, ${farbe}17 0%, ${farbe}08 45%, transparent 75%), #111318`,
              borderColor: `${farbe}2a`,
            }}
      >

        <div className="relative z-10 flex items-center gap-4 flex-wrap">
          <HealthIcon status={status.status} kind={kind} size={32} color={farbe} />

          {/* Mindestbreite, damit der Text auf dem Handy unter das Zeichen
              rutscht. Sonst stand er als schmale Säule zwischen Herz und
              Knopf, ein Wort je Zeile. */}
          <div className="min-w-0 flex-1 basis-64">
            <div className="flex items-baseline gap-3 flex-wrap">
              <span className="text-xl font-black tracking-tight"
                    style={{ color: farbe, fontFamily: 'Barlow Condensed, sans-serif' }}>
                {zustandText}
              </span>
              <span className="text-[10px] font-mono tracking-widest text-[var(--text-muted)]">
                {event
                  ? `${ART_EN[kind] || event.kind_label.toUpperCase()} SINCE ${event.start_date} · ${event.days} ${event.days === 1 ? 'DAY' : 'DAYS'}`
                  : stil.sub.toUpperCase()}
              </span>
            </div>

            {/* Die Begründung ist wichtiger als der Zustand: sie sagt, was
                heute erlaubt ist. */}
            {status.lines?.length > 0 && (
              <ul className="mt-2 space-y-1">
                {status.lines.map((line, i) => (
                  <li key={i} className="text-xs text-[var(--text-secondary)] leading-relaxed">— {line}</li>
                ))}
              </ul>
            )}

            {status.status === 'returning' && status.easy_until && (
              <div className="text-[10px] font-mono mt-2" style={{ color: farbe }}>
                EASY UNTIL {status.easy_until} · VOLUME {Math.round(status.volume_factor * 100)} %
              </div>
            )}

            {hinweis && (
              <div className="text-[10px] font-mono text-[#00d4ff] mt-2">{hinweis}</div>
            )}
          </div>

          <div className="flex gap-2 flex-shrink-0">
            {status.status === 'sick' ? (
              <button
                onClick={gesund} disabled={busy}
                className="px-4 py-2 rounded-lg text-[11px] font-mono font-bold tracking-wide disabled:opacity-40"
                style={{ background: '#22c55e20', border: '1px solid #22c55e44', color: '#22c55e' }}
              >
                {busy ? '…' : (verletzt ? 'FIT AGAIN' : 'HEALTHY AGAIN')}
              </button>
            ) : (
              <button
                onClick={() => setDialog(true)}
                className="px-4 py-2 rounded-lg text-[11px] font-mono font-bold tracking-wide transition-all"
                style={{ background: '#ef444418', border: '1px solid #ef444438', color: '#ef4444' }}
              >
                SICK OR INJURED
              </button>
            )}
          </div>
        </div>
      </div>
      {dialogNode}
    </>
  )
}
