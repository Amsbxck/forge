import { useCallback, useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import Upload from './pages/Upload'
import WeeklyPlan from './pages/WeeklyPlan'
import Chat from './pages/Chat'
import History from './pages/History'
import Races from './pages/Races'
import Integrations from './pages/Integrations'
import Profile from './pages/Profile'
import SyncButton from './components/SyncButton'
import Login from './pages/Login'
import { ResetPage, VerifyPage } from './pages/AuthAction'
import { getMe, getToken, logoutEverywhere, setToken, setUnauthorizedHandler } from './services/api'

const navItems = [
  { to: '/',        label: 'Dashboard', short: 'Dash' },
  { to: '/history', label: 'History',   short: 'History' },
  { to: '/races',   label: 'Races',     short: 'Races' },
  { to: '/plan',    label: 'Plan',      short: 'Plan' },
  { to: '/chat',    label: 'Coach',     short: 'Coach' },
  { to: '/upload',  label: 'Upload',    short: 'Upload' },
  { to: '/profile', label: 'Profile',   short: 'Profile' },
  { to: '/connect', label: 'Connect',   short: 'Connect' },
]

export default function App() {
  // null = noch nicht geprüft, false = abgemeldet, Objekt = angemeldet
  const [user, setUser] = useState(null)

  const logout = useCallback(() => {
    // Erst serverseitig widerrufen, dann lokal vergessen. Nur das Token zu
    // löschen ließe eine Kopie davon bis zum Ablauf weitergelten.
    logoutEverywhere().catch(() => {}).finally(() => {
      setToken(null)
      setUser(false)
    })
  }, [])

  useEffect(() => {
    setUnauthorizedHandler(logout)
    if (!getToken()) { setUser(false); return }
    // Token vorhanden — aber es kann abgelaufen sein. Einmal prüfen, statt
    // die Oberfläche aufzubauen und dann in 401-Fehler zu laufen.
    getMe().then(({ data }) => setUser(data)).catch(() => setUser(false))
  }, [logout])

  // Links aus E-Mails werden im abgemeldeten Zustand geöffnet und müssen
  // deshalb vor der Anmeldeschranke greifen.
  const pfad = window.location.pathname
  if (pfad === '/verify') return <VerifyPage onAuthenticated={setUser} />
  if (pfad === '/reset') return <ResetPage onAuthenticated={setUser} />

  if (user === null) {
    return (
      <div className="min-h-screen flex items-center justify-center font-mono text-xs tracking-widest text-[var(--text-muted)]"
           style={{ background: '#07080f' }}>
        LÄDT…
      </div>
    )
  }

  if (user === false) {
    return <Login onAuthenticated={setUser} />
  }

  return (
    <BrowserRouter>
      <div className="min-h-screen flex flex-col" style={{ background: '#07080f' }}>
        <nav
          className="sticky top-0 z-40 border-b px-4 py-0"
          style={{ background: '#070810', borderColor: '#1e2228' }}
        >
          <div className="max-w-6xl mx-auto flex items-center h-14 gap-4 overflow-x-auto scrollbar-none">
            {/* Wordmark */}
            <span
              className="text-2xl font-black tracking-widest select-none flex-shrink-0"
              style={{
                fontFamily: 'Barlow Condensed, sans-serif',
                color: '#00d4ff',
                letterSpacing: '0.15em',
                textShadow: '0 0 20px #00d4ff44',
              }}
            >
              FORGE
            </span>

            {/* Nav links */}
            <div className="flex gap-1 flex-shrink-0">
              {navItems.map(({ to, label, short }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={to === '/'}
                  className={({ isActive }) =>
                    `px-2.5 py-1.5 rounded-lg text-xs font-mono tracking-wide transition-all whitespace-nowrap ${
                      isActive
                        ? 'text-[#00d4ff] bg-[#00d4ff15] border border-[#00d4ff33]'
                        : 'text-[var(--text-secondary)] hover:text-[#e8eaf0] border border-transparent'
                    }`
                  }
                >
                  <span className="hidden sm:inline">{label}</span>
                  <span className="sm:hidden">{short}</span>
                </NavLink>
              ))}
            </div>

            <SyncButton />

            <button
              onClick={logout}
              title={`Angemeldet als ${user.email} — abmelden`}
              className="px-2.5 py-1.5 rounded-lg text-xs font-mono tracking-wide text-[var(--text-muted)] hover:text-[#ef4444] transition-colors flex-shrink-0"
              style={{ border: '1px solid #1e2228' }}
            >
              ⏻
            </button>
          </div>
        </nav>

        <main className="flex-1 max-w-6xl mx-auto w-full px-4 py-6">
          <Routes>
            <Route path="/"        element={<Dashboard />} />
            <Route path="/upload"  element={<Upload />} />
            <Route path="/plan"    element={<WeeklyPlan />} />
            <Route path="/chat"    element={<Chat />} />
            <Route path="/history" element={<History />} />
            <Route path="/races"   element={<Races />} />
            <Route path="/profile" element={<Profile />} />
            <Route path="/connect" element={<Integrations />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
