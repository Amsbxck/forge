import { useState, useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { useNavigate } from 'react-router-dom'
import { uploadFile } from '../services/api'

const LABEL = 'text-xs font-mono tracking-widest text-[#8a909e]'

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
      const detail = e.response?.data?.detail || 'Upload failed'
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

  return (
    <div className="space-y-6 page-enter">

      {/* Header */}
      <div className="flex items-baseline gap-3">
        <h1
          className="text-3xl font-black tracking-tight text-[#e8eaf0]"
          style={{ fontFamily: 'Barlow Condensed, sans-serif' }}
        >
          UPLOAD
        </h1>
        <span className="text-xs font-mono text-[#3a3f4a] tracking-widest">.FIT / .GPX</span>
      </div>

      {/* Dropzone — diagonal cut corners */}
      <div
        {...getRootProps()}
        className="relative p-16 text-center cursor-pointer transition-all select-none overflow-hidden"
        style={{
          background: isDragActive ? '#00d4ff08' : '#111318',
          border: `1px solid ${isDragActive ? '#00d4ff55' : '#1e2228'}`,
          clipPath: 'polygon(0 0, calc(100% - 28px) 0, 100% 28px, 100% 100%, 28px 100%, 0 calc(100% - 28px))',
          boxShadow: isDragActive ? '0 0 40px #00d4ff12' : 'none',
        }}
      >
        <input {...getInputProps()} />

        {/* Accent lines on cut corners */}
        <div className="absolute top-0 right-0 w-8 h-px" style={{ background: isDragActive ? '#00d4ff' : '#3a3f4a', transformOrigin: 'right', transform: 'rotate(0deg)', top: '27px', right: 0 }} />
        <div className="absolute top-0 right-0 w-px h-8" style={{ background: isDragActive ? '#00d4ff' : '#3a3f4a', top: 0, right: '27px' }} />
        <div className="absolute bottom-0 left-0 w-8 h-px" style={{ background: isDragActive ? '#00d4ff' : '#3a3f4a', bottom: '27px', left: 0 }} />
        <div className="absolute bottom-0 left-0 w-px h-8" style={{ background: isDragActive ? '#00d4ff' : '#3a3f4a', bottom: 0, left: '27px' }} />

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
            <p className="text-sm font-mono tracking-widest" style={{ color: '#00d4ff' }}>PARSING...</p>
          </div>
        ) : isDragActive ? (
          <div className="flex flex-col items-center gap-2">
            <div
              className="text-5xl font-black"
              style={{ fontFamily: 'Barlow Condensed, sans-serif', color: '#00d4ff', animation: 'dropPulse 0.6s ease-in-out infinite alternate' }}
            >
              DROP IT
            </div>
            <p className="text-xs font-mono text-[#00d4ff] opacity-60 tracking-wide">Release to upload</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            <div
              className="text-5xl font-black text-[#1e2228]"
              style={{ fontFamily: 'Barlow Condensed, sans-serif' }}
            >
              DROP FILE
            </div>
            <p className="text-xs font-mono text-[#3a3f4a] tracking-wide">
              or click to select · .fit (Garmin/Wahoo) · .gpx
            </p>
          </div>
        )}
      </div>

      {/* Status */}
      {status && (
        <div
          className="rounded-xl p-5 relative overflow-hidden"
          style={{
            background: status.ok ? '#22c55e10' : '#ef444410',
            border: `1px solid ${status.ok ? '#22c55e30' : '#ef444430'}`,
          }}
        >
          {status.ok ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full" style={{ background: '#22c55e', boxShadow: '0 0 8px #22c55e88' }} />
                <span className="font-bold text-sm tracking-wide" style={{ fontFamily: 'Barlow Condensed, sans-serif', color: '#22c55e' }}>
                  {status.data.message}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2">
                {Object.entries(status.data.parsed || {}).map(([k, v]) =>
                  v != null ? (
                    <div key={k} className="rounded-lg px-3 py-2" style={{ background: '#111318', border: '1px solid #1e2228' }}>
                      <div className={`${LABEL} mb-0.5`}>{k.replace(/_/g, ' ').toUpperCase()}</div>
                      <div className="text-sm font-mono text-[#e8eaf0]">{String(v)}</div>
                    </div>
                  ) : null
                )}
              </div>
            </div>
          ) : (
            <div className="flex items-start gap-2">
              <span className="text-[#ef4444] font-bold font-mono mt-0.5">✕</span>
              <p className="text-sm font-mono text-[#ef4444]">{status.error}</p>
            </div>
          )}
        </div>
      )}

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
