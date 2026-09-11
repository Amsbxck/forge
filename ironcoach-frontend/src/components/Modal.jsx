import { useEffect } from 'react'
import { createPortal } from 'react-dom'

/** Overlay-Dialog — die eine Stelle, an der Dialogverhalten definiert ist.
 *
 *  Über ein Portal direkt an `<body>`, und das ist kein Stilfrage: die
 *  Seiteneinblendung (`.page-enter > *`) läuft mit `animation-fill-mode:
 *  forwards` und hinterlässt auf jedem Kind ein `transform`. Ein Vorfahre mit
 *  Transform wird zum Bezugsrahmen für `position: fixed` — ohne Portal legt
 *  sich ein Dialog deshalb nur über den eigenen Kasten statt über die Seite.
 *
 *  `width` ist eine Tailwind-Klasse für die Maximalbreite: schmal für ein
 *  Formular mit wenigen Feldern, breit für eine Tabelle.
 */
export default function Modal({
  open,
  onClose,
  title,
  subtitle,
  icon = null,
  width = 'max-w-md',
  // center | upper | top
  //   center — mittig, für kurze Dialoge
  //   upper  — etwas über der Mitte; exakte Mitte wirkt bei hohen Dialogen
  //            gedrängt, weil unten viel Luft bleibt und oben keine
  //   top    — oben angedockt, für sehr lange Inhalte
  align = 'center',
  // Für Dialoge, aus denen es nur über eine bewusste Entscheidung
  // herausgeht: Ohne diesen Schalter bliebe ein ✕ stehen, das nichts tut —
  // schlechter als gar keiner, weil es Wirkung verspricht.
  dismissible = true,
  children,
}) {
  useEffect(() => {
    if (!open) return
    const taste = e => e.key === 'Escape' && dismissible && onClose?.()
    document.addEventListener('keydown', taste)
    // Kein Scrollen dahinter, sonst rutscht die Seite unter dem Dialog weg.
    const vorher = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', taste)
      document.body.style.overflow = vorher
    }
  }, [open, onClose, dismissible])

  if (!open) return null

  return createPortal(
    <div
      className={`fixed inset-0 z-[100] flex justify-center p-4 ${
        align === 'top' ? 'items-start overflow-y-auto'
          // Die Verschiebung entsteht über den unteren Innenabstand statt über
          // einen Versatz: Der Dialog bleibt in einem kürzeren Kasten mittig
          // und kann deshalb bei kleinen Fenstern nicht oben herausragen.
          : align === 'upper' ? 'items-center pb-[12vh] overflow-y-auto'
          : 'items-center'
      }`}
      style={{
        background: '#05060bee',
        backdropFilter: 'blur(4px)',
        WebkitBackdropFilter: 'blur(4px)',
        animation: 'dialogEin 0.15s ease-out',
      }}
      onClick={dismissible ? onClose : undefined}
      role="dialog"
      aria-modal="true"
    >
      <div
        className={`w-full ${width} rounded-xl p-5 ${
          align === 'top' ? 'my-4' : align === 'upper' ? 'max-h-[80vh]' : 'max-h-[88vh]'
        } overflow-y-auto`}
        style={{
          background: '#111318',
          border: '1px solid #1e2228',
          boxShadow: '0 24px 60px -12px #000000cc',
          animation: 'dialogAuf 0.18s cubic-bezier(0.16, 1, 0.3, 1)',
        }}
        onClick={e => e.stopPropagation()}
      >
        {(title || icon) && (
          <div className="flex items-center justify-between gap-3 mb-4">
            <div className="flex items-center gap-3 min-w-0">
              {icon}
              <div className="min-w-0">
                <div
                  className="text-lg font-black tracking-tight text-[#e8eaf0] truncate"
                  style={{ fontFamily: 'Barlow Condensed, sans-serif' }}
                >
                  {title}
                </div>
                {subtitle && (
                  <div className="text-xs font-mono text-[var(--text-secondary)] mt-0.5">
                    {subtitle}
                  </div>
                )}
              </div>
            </div>
            {dismissible && (
              <button
                onClick={onClose}
                className="text-[var(--text-muted)] hover:text-[var(--text-secondary)] font-mono flex-shrink-0 px-1"
                title="Schließen (Esc)"
              >
                ✕
              </button>
            )}
          </div>
        )}
        {children}
      </div>
    </div>,
    document.body
  )
}
