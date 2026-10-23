import { useState, useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { useNavigate } from 'react-router-dom'
import { uploadFile } from '../services/api'
import { fehlerText } from '../utils/fehler'
import { DISPLAY, KOPF, Kachel, SeitenKopf, Stand, TITEL, toenung } from '../components/leisten/Kachel'

function Particles() {
  const particles = Array.from({ length: 18 }, (_, i) => {
    const angle = (i / 18) * 360
    const dist = 60 + Math.random() * 50
    const size = 3 + Math.random() * 4
    const delay = Math.random() * 0.2
    return { angle, dist, size, delay }
  })

  return (
    <div className="absolute inset-0 pointer-events-none flex items-center justify-center" style={{ zIndex: 10 }}>
      {particles.map((p, i) => (
        <div
          key={i}
          className="absolute rounded-full"
          style={{
            width: `${p.size}px`,
            height: `${p.size}px`,
            background: '#00d4ff',
            animation: `particle 0.7s ${p.delay}s ease-out forwards`,
            '--tx': `${Math.cos((p.angle * Math.PI) / 180) * p.dist}px`,
            '--ty': `${Math.sin((p.angle * Math.PI) / 180) * p.dist}px`,
            opacity: 0,
          }}
        />
      ))}
    </div>
  )
}

export default function Upload() {
  const [status, setStatus] = useState(null)
  const [uploading, setUploading] = useState(false)
  const navigate = useNavigate()

  const onDrop = useCallback(async (accepted) => {
    if (!accepted.length) return
    const file = accepted[0]
    setUploading(true)
    setStatus(null)
    try {
      const resp = await uploadFile(file)
      setStatus({ ok: true, data: resp.data })
      setTimeout(() => navigate('/'), 2000)
    } catch (e) {
      const detail = fehlerText(e, 'Upload failed')
      setStatus({ ok: false, error: detail })
    } finally {
      setUploading(false)
    }
  }, [navigate])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/octet-stream': ['.fit'],
      'application/gpx+xml': ['.gpx'],
      'text/xml': ['.gpx'],
    },
    maxFiles: 1,
  })

  // Woher die Datei kommt — als drei kurze Wege statt eines leeren Bildschirms
  // unter der Ablage. Die Seite bestand vorher nur aus der Ablagefläche.
  const QUELLEN = [
    { name: 'GARMIN CONNECT', weg: 'Aktivität öffnen → Zahnrad → „Original exportieren". Die ZIP enthält die .fit.' },
    { name: 'WAHOO', weg: 'In der ELEMNT-App die Fahrt öffnen → Teilen → .fit-Datei.' },
    { name: 'STRAVA', weg: 'Aktivität öffnen → ⋯ → „Original exportieren" (nur am Rechner).' },
  ]

  return (
    <div className="space-y-4 page-enter">
      <SeitenKopf titel="UPLOAD" zusatz=".FIT · .GPX" />

      {/* Die Ablage als Kachel wie im Dashboard. Vorher eine Fläche mit
          abgeschnittenen Ecken und Zierstrichen — die gibt es sonst nirgends
          in der App mehr. */}
      <Kachel titel="DROP A FILE" rechts="ONE FILE AT A TIME">
        <div
          {...getRootProps()}
          className="relative rounded-lg px-6 py-14 text-center cursor-pointer transition-all select-none overflow-hidden"
          style={{
            background: isDragActive ? '#00d4ff0a' : '#0d0f14',
            border: `1px dashed ${isDragActive ? '#00d4ff88' : '#2a2f38'}`,
            boxShadow: isDragActive ? 'inset 0 0 40px #00d4ff10' : 'none',
          }}
        >
          <input {...getInputProps()} />

          {/* Particles on success */}
          {status?.ok && <Particles />}

          {uploading ? (
            <div className="flex flex-col items-center gap-4">
              <div className="flex items-end gap-1" style={{ height: '32px' }}>
                {[0, 1, 2, 3, 4].map(i => (
                  <div
                    key={i}
                    className="w-2 rounded-sm"
                    style={{
                      background: '#00d4ff',
                      animation: `uploadBar 0.8s ease-in-out ${i * 0.12}s infinite alternate`,
                      height: `${12 + i * 5}px`,
                    }}
                  />
                ))}
              </div>
              <p className="text-[10px] font-mono tracking-[0.25em]" style={{ color: '#00d4ff' }}>READING FILE…</p>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-3">
              <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke={isDragActive ? '#00d4ff' : '#5b6475'}
                   strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"
                   style={{ animation: isDragActive ? 'dropPulse 0.6s ease-in-out infinite alternate' : 'none' }}>
                <path d="M12 16V4" /><path d="M7 9l5-5 5 5" /><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" />
              </svg>
              <div className="text-4xl font-black leading-none"
                   style={{ ...DISPLAY, color: isDragActive ? '#00d4ff' : '#f2f4f8' }}>
                {isDragActive ? 'RELEASE TO UPLOAD' : 'DROP FILE HERE'}
              </div>
              <p className="text-[10px] font-mono tracking-widest text-[var(--text-muted)]">
                OR CLICK TO SELECT · .FIT (GARMIN / WAHOO) · .GPX
              </p>
            </div>
          )}
        </div>
      </Kachel>

      {/* Ergebnis: die gelesenen Werte als Zahlen wie in den Kacheln,
          getönt grün oder rot statt einer vollen Farbfläche. */}
      {status && (
        <div className="rounded-xl p-5 border relative overflow-hidden" style={toenung(status.ok ? '#22c55e' : '#ef4444')}>
          {status.ok ? (
            <div className="space-y-4">
              <div className="flex items-baseline justify-between gap-3 flex-wrap">
                <span className={TITEL}>IMPORTED</span>
                <Stand>{status.data.message}</Stand>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-4">
                {Object.entries(status.data.parsed || {}).map(([k, v]) =>
                  v != null ? (
                    <div key={k} className="min-w-0">
                      <div className={KOPF}>{k.replace(/_/g, ' ').toUpperCase()}</div>
                      <div className="text-2xl font-black leading-none tabular-nums text-[#f2f4f8] mt-1.5 truncate" style={DISPLAY}>
                        {String(v)}
                      </div>
                    </div>
                  ) : null
                )}
              </div>
              <div className="text-[9px] font-mono tracking-widest text-[var(--text-muted)]">BACK TO THE DASHBOARD IN A MOMENT…</div>
            </div>
          ) : (
            <div className="space-y-2">
              <span className={TITEL}>NOT IMPORTED</span>
              <p className="text-sm text-[#f87171] leading-relaxed">{status.error}</p>
            </div>
          )}
        </div>
      )}

      <Kachel titel="WHERE TO GET THE FILE">
        <div className="grid gap-4 sm:grid-cols-3">
          {QUELLEN.map((q, i) => (
            <div key={q.name} className={i ? 'sm:pl-5 sm:border-l sm:border-[#ffffff0f]' : ''}>
              <div className={KOPF}>{q.name}</div>
              <p className="text-xs text-[var(--text-secondary)] leading-relaxed mt-1.5">{q.weg}</p>
            </div>
          ))}
        </div>
      </Kachel>

      <style>{`
        @keyframes uploadBar {
          from { opacity: 0.4; transform: scaleY(0.5); }
          to   { opacity: 1;   transform: scaleY(1); }
        }
        @keyframes dropPulse {
          from { transform: scale(1);    opacity: 0.8; }
          to   { transform: scale(1.04); opacity: 1; }
        }
        @keyframes particle {
          0%   { opacity: 1; transform: translate(0, 0) scale(1); }
          100% { opacity: 0; transform: translate(var(--tx), var(--ty)) scale(0); }
        }
      `}</style>
    </div>
  )
}
