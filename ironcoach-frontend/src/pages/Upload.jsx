import { useState, useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { useNavigate } from 'react-router-dom'
import { uploadFile } from '../services/api'

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
      setTimeout(() => navigate('/'), 1500)
    } catch (e) {
      const detail = e.response?.data?.detail || 'Upload fehlgeschlagen'
      setStatus({ ok: false, error: detail })
    } finally {
      setUploading(false)
    }
  }, [navigate])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/octet-stream': ['.fit'], 'application/gpx+xml': ['.gpx'], 'text/xml': ['.gpx'] },
    maxFiles: 1,
  })

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Einheit hochladen</h1>
      <p className="text-gray-400">Lade eine <code>.fit</code> (Garmin/Wahoo) oder <code>.gpx</code> Datei hoch.</p>

      <div
        {...getRootProps()}
        className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors ${
          isDragActive ? 'border-brand-500 bg-brand-500/10' : 'border-gray-700 hover:border-gray-500'
        }`}
      >
        <input {...getInputProps()} />
        {uploading ? (
          <p className="text-gray-400">Wird hochgeladen und geparst...</p>
        ) : isDragActive ? (
          <p className="text-brand-500 font-medium">Datei hier ablegen</p>
        ) : (
          <div>
            <p className="text-gray-300 font-medium mb-1">Datei hier ablegen</p>
            <p className="text-gray-500 text-sm">oder klicken zum Auswählen (.fit / .gpx)</p>
          </div>
        )}
      </div>

      {status && (
        <div className={`rounded-xl p-5 ${status.ok ? 'bg-green-900/40 border border-green-700' : 'bg-red-900/40 border border-red-700'}`}>
          {status.ok ? (
            <div>
              <p className="font-semibold text-green-400 mb-2">{status.data.message}</p>
              <div className="text-sm text-gray-300 space-y-1">
                {Object.entries(status.data.parsed || {}).map(([k, v]) => (
                  v != null && (
                    <div key={k} className="flex gap-2">
                      <span className="text-gray-500 w-36 shrink-0">{k}</span>
                      <span>{String(v)}</span>
                    </div>
                  )
                ))}
              </div>
            </div>
          ) : (
            <p className="text-red-400">{status.error}</p>
          )}
        </div>
      )}
    </div>
  )
}
