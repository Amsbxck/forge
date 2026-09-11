import { useCallback, useEffect, useState } from 'react'
import { getHealthStatus, reportIllness, reportRecovered } from '../services/api'
import HealthIcon from './HealthIcon'
import Modal from './Modal'

const LABEL = 'text-[10px] font-mono tracking-widest text-[var(--text-secondary)]'
const FIELD_STYLE = { background: '#0d0f17', border: '1px solid #1e2228' }

// Der Schweregrad bedeutet bei einer Verletzung etwas anderes als bei einem
// Infekt: dort entscheidet das Immunsystem, hier die Belastbarkeit. Mit
// Erkältungsbeschreibungen unter „Verletzung" wäre die Auswahl geraten.
const SEVERITIES = {
  illness: [
    { key: 'mild', label: 'LEICHT', hint: 'Schnupfen, Halskratzen — über dem Hals, kein Fieber' },
    { key: 'moderate', label: 'MÄSSIG', hint: 'Husten, Gliederschmerzen' },
    { key: 'severe', label: 'SCHWER', hint: 'Fieber oder ärztlich verordnete Pause' },
  ],
  injury: [
    { key: 'mild', label: 'LEICHT', hint: 'Schmerzfrei belastbar — nur kein harter Reiz' },
    { key: 'moderate', label: 'MÄSSIG', hint: 'Schmerz bei Belastung — betroffene Disziplin pausiert' },
    { key: 'severe', label: 'SCHWER', hint: 'Nicht belastbar oder ärztlich verordnete Pause' },
  ],
}

const NOTIZ_BEISPIEL = {
  illness: 'z. B. Erkältung, Magen-Darm',
  injury: 'Was ist betroffen? z. B. rechte Achillessehne',
}

const STATUS = {
  healthy: { color: '#22c55e', text: 'GESUND', sub: 'Training nach Plan' },
  sick: { color: '#ef4444', text: 'KRANK', sub: 'Plan ausgesetzt' },
  returning: { color: '#f59e0b', text: 'WIEDEREINSTIEG', sub: 'Nur locker' },
}

const LEER_FORM = { kind: 'illness', severity: 'mild', fever: false, start_date: '', note: '' }

/** Meldeformular als Overlay.
 *
 *  Bewusst nicht eingebettet: auf dem Dashboard ist die Kachel dafür zu
 *  klein, und im Plan würde sie den Kalender wegschieben. So ist es an
 *  beiden Stellen dasselbe Formular.
 */
function ReportDialog({ onClose, onDone }) {
  const [form, setForm] = useState(LEER_FORM)
  const [busy, setBusy] = useState(false)

  const senden = async () => {
    setBusy(true)
    try {
      await reportIllness({
        kind: form.kind,
        severity: form.severity,
        fever: form.severity === 'severe' ? form.fever : false,
        start_date: form.start_date || null,
        note: form.note || null,
      })
      onDone()
    } finally { setBusy(false) }
  }

  return (
    <Modal
      open onClose={onClose}
      title={form.kind === 'injury' ? 'VERLETZUNG MELDEN' : 'KRANKHEIT MELDEN'}
      subtitle="Der Wochenplan wird danach neu erstellt"
      icon={<HealthIcon status="sick" kind={form.kind} size={26}
                        color={form.kind === 'injury' ? '#f59e0b' : '#ef4444'} />}
    >
      <div className="space-y-4">
        <div className="flex gap-1 p-0.5 rounded-lg" style={{ background: '#0d0f17' }}>
          {[
            { key: 'illness', label: 'KRANKHEIT' },
            { key: 'injury', label: 'VERLETZUNG' },
          ].map(t => (
            <button
              key={t.key} type="button"
              onClick={() => setForm(f => ({ ...f, kind: t.key }))}
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
          <span className={`${LABEL} block mb-1`}>SCHWEREGRAD</span>
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
          <span className={`${LABEL} block mb-1`}>SEIT WANN (LEER = HEUTE)</span>
          <input
            type="date" max={new Date().toISOString().slice(0, 10)}
            className="rounded-lg px-3 py-2 text-sm font-mono text-[#e8eaf0] outline-none w-full"
            style={FIELD_STYLE} value={form.start_date}
            onChange={e => setForm(f => ({ ...f, start_date: e.target.value }))}
          />
        </label>

        <label className="block">
          <span className={`${LABEL} block mb-1`}>
            {form.kind === 'injury' ? 'WAS IST BETROFFEN?' : 'NOTIZ (OPTIONAL)'}
          </span>
          <input
            className="rounded-lg px-3 py-2 text-sm font-mono text-[#e8eaf0] placeholder-[var(--text-muted)] outline-none w-full"
            style={FIELD_STYLE} value={form.note} placeholder={NOTIZ_BEISPIEL[form.kind]}
            onChange={e => setForm(f => ({ ...f, note: e.target.value }))}
          />
        </label>

        <div className="flex gap-2 pt-1">
          <button
            onClick={senden} disabled={busy}
            className="flex-1 py-2 rounded-lg text-[11px] font-mono font-bold tracking-wide disabled:opacity-40"
            style={{ background: '#ef444420', border: '1px solid #ef444444', color: '#ef4444' }}
          >
            {busy ? '…' : 'MELDEN & PLAN ANPASSEN'}
          </button>
          <button onClick={onClose}
                  className="px-4 py-2 rounded-lg text-[11px] font-mono text-[var(--text-muted)] hover:text-[var(--text-secondary)]">
            ABBRECHEN
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

  const nachMeldung = async (text) => {
    setHinweis(text)
    await load()
    onChanged?.()
  }

  const gesund = async () => {
    setBusy(true)
    try {
      await reportRecovered({})
      await nachMeldung('Willkommen zurück. Der Wiedereinstiegsplan wird erstellt.')
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
  const zustandText = verletzt ? 'VERLETZT' : stil.text

  const dialogNode = dialog && (
    <ReportDialog
      onClose={() => setDialog(false)}
      onDone={async () => {
        setDialog(false)
        await nachMeldung('Gemeldet. Der Wochenplan wird im Hintergrund angepasst.')
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
              <div className={LABEL}>ZUSTAND</div>
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
      <div
        className="rounded-xl px-5 py-4 relative overflow-hidden"
        style={{
          background: '#111318',
          border: `1px solid ${status.status === 'healthy' ? '#1e2228' : farbe + '44'}`,
          borderLeft: `3px solid ${farbe}`,
        }}
      >
        <div className="absolute inset-0 pointer-events-none" style={{
          background: `radial-gradient(ellipse 40% 120% at 0% 50%, ${farbe}14 0%, transparent 70%)`,
        }} />

        <div className="relative z-10 flex items-center gap-4 flex-wrap">
          <HealthIcon status={status.status} kind={kind} size={32} color={farbe} />

          <div className="min-w-0 flex-1">
            <div className="flex items-baseline gap-3 flex-wrap">
              <span className="text-xl font-black tracking-tight"
                    style={{ color: farbe, fontFamily: 'Barlow Condensed, sans-serif' }}>
                {zustandText}
              </span>
              <span className="text-[10px] font-mono tracking-widest text-[var(--text-muted)]">
                {event
                  ? `${event.kind_label.toUpperCase()} SEIT ${event.start_date} · ${event.days} ${event.days === 1 ? 'TAG' : 'TAGE'}`
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
                LOCKER BIS {status.easy_until} · UMFANG {Math.round(status.volume_factor * 100)} %
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
                {busy ? '…' : (verletzt ? 'WIEDER BELASTBAR' : 'WIEDER GESUND')}
              </button>
            ) : (
              <button
                onClick={() => setDialog(true)}
                className="px-4 py-2 rounded-lg text-[11px] font-mono font-bold tracking-wide transition-all"
                style={{ background: '#ef444418', border: '1px solid #ef444438', color: '#ef4444' }}
              >
                KRANK ODER VERLETZT
              </button>
            )}
          </div>
        </div>
      </div>
      {dialogNode}
    </>
  )
}
