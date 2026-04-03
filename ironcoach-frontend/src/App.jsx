import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import Upload from './pages/Upload'
import WeeklyPlan from './pages/WeeklyPlan'
import Chat from './pages/Chat'
import History from './pages/History'
import Profile from './pages/Profile'

const navItems = [
  { to: '/',        label: 'Dashboard', short: 'Dash' },
  { to: '/history', label: 'History',   short: 'History' },
  { to: '/plan',    label: 'Plan',      short: 'Plan' },
  { to: '/chat',    label: 'Coach',     short: 'Coach' },
  { to: '/upload',  label: 'Upload',    short: 'Upload' },
  { to: '/profile', label: 'Profile',   short: 'Profile' },
]

export default function App() {
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
                        : 'text-[#8a909e] hover:text-[#e8eaf0] border border-transparent'
                    }`
                  }
                >
                  <span className="hidden sm:inline">{label}</span>
                  <span className="sm:hidden">{short}</span>
                </NavLink>
              ))}
            </div>
          </div>
        </nav>

        <main className="flex-1 max-w-6xl mx-auto w-full px-4 py-6">
          <Routes>
            <Route path="/"        element={<Dashboard />} />
            <Route path="/upload"  element={<Upload />} />
            <Route path="/plan"    element={<WeeklyPlan />} />
            <Route path="/chat"    element={<Chat />} />
            <Route path="/history" element={<History />} />
            <Route path="/profile" element={<Profile />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
