import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
  timeout: 60000,
})

// --- Anmeldung ---------------------------------------------------------------

const TOKEN_KEY = 'ironcoach_token'

export const getToken = () => {
  try { return localStorage.getItem(TOKEN_KEY) } catch { return null }
}

export const setToken = (token) => {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch { /* privater Modus o.ä. — dann gilt die Sitzung nur im Speicher */ }
}

// Token an jede Anfrage hängen, statt es in jedem Aufruf mitzugeben.
api.interceptors.request.use(config => {
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Abgelaufenes oder ungültiges Token: einmal aufräumen und zur Anmeldung.
// Ohne das läuft die Oberfläche in eine Endlosschleife aus 401-Fehlern.
let onUnauthorized = null
export const setUnauthorizedHandler = (fn) => { onUnauthorized = fn }

api.interceptors.response.use(
  response => response,
  error => {
    const url = error.config?.url || ''
    if (error.response?.status === 401 && !url.includes('/api/auth/')) {
      setToken(null)
      onUnauthorized?.()
    }
    return Promise.reject(error)
  }
)

export const login = (email, password) => api.post('/api/auth/login', { email, password })
export const register = (email, password, name) =>
  api.post('/api/auth/register', { email, password, name })
export const getMe = () => api.get('/api/auth/me')
export const changePassword = (currentPassword, newPassword) =>
  api.post('/api/auth/change-password', {
    current_password: currentPassword, new_password: newPassword,
  })

// HRV
export const postHrv = (data) => api.post('/api/hrv', data)
export const getHrv = (limit = 14) => api.get('/api/hrv', { params: { limit } })
export const getLatestHrv = () => api.get('/api/hrv/latest')

// Metrics
export const getWeekMetrics = () => api.get('/api/metrics/week')
export const getTrends = (weeks = 4) => api.get('/api/metrics/trends', { params: { weeks } })
export const getPmc = () => api.get('/api/metrics/pmc')
export const getProfile = () => api.get('/api/profile')
export const updateProfile = (data) => api.patch('/api/profile', data)
export const getIntakeStatus = () => api.get('/api/profile/intake')
export const submitIntake = (data) => api.post('/api/profile/intake', data)

// Upload
export const uploadFile = (file) => {
  const form = new FormData()
  form.append('file', file)
  return api.post('/api/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

// Plan — generation can take 90+ seconds with long Claude prompts
export const generatePlan = (requests = '') =>
  api.get('/api/plan/generate', { params: { requests }, timeout: 180000 })
export const getCurrentPlan = () => api.get('/api/plan/current')
export const getPlanByWeek = (week) => api.get(`/api/plan/${week}`)
// Über den Montag statt über die Wochennummer: Die Nummer ist vor dem
// Beginn des Aufbaus für jedes Datum 1, damit liesse sich nicht blättern.
export const getPlanByMonday = (montag) => api.get(`/api/plan/am/${montag}`)
export const downloadPlanPDF = (week) =>
  api.get(`/api/plan/${week}/pdf`, { responseType: 'blob' })

// Planned sessions — normalisierte Projektion des Wochenplans
export const getPlannedCurrent = () => api.get('/api/planned/current')
export const getPlannedWeek = (week) => api.get(`/api/planned/week/${week}`)
export const getPlannedByMonday = (montag) => api.get(`/api/planned/am/${montag}`)
export const patchPlannedSession = (id, data) => api.patch(`/api/planned/${id}`, data)
export const setPlannedReplacement = (id, text, durationMin) =>
  api.post(`/api/planned/${id}/replacement`, { text, duration_min: durationMin ?? null })
export const clearPlannedReplacement = (id) =>
  api.delete(`/api/planned/${id}/replacement`)
export const swapPlannedSessions = (aId, bId) =>
  api.post('/api/planned/swap', { a_id: aId, b_id: bId })

// Ziele, Rennen, Benchmark
export const getRaceTypes = () => api.get('/api/race-types')
export const getGoals = () => api.get('/api/goals')
export const getActiveGoal = () => api.get('/api/goals/active')
export const createGoal = (data) => api.post('/api/goals', data)
export const updateGoal = (id, data) => api.patch(`/api/goals/${id}`, data)
export const getRaces = () => api.get('/api/races')
export const createRace = (data) => api.post('/api/races', data)
export const updateRace = (id, data) => api.patch(`/api/races/${id}`, data)
export const deleteRace = (id) => api.delete(`/api/races/${id}`)
export const uploadRaceImage = (id, file) => {
  const form = new FormData()
  form.append('file', file)
  return api.post(`/api/races/${id}/image`, form, {
    headers: { 'Content-Type': 'multipart/form-data' }, timeout: 60000,
  })
}
export const deleteRaceImage = (id) => api.delete(`/api/races/${id}/image`)
// Das Bild hängt hinter der Anmeldung — deshalb als Blob laden statt per <img src>.
export const fetchRaceImage = (id) =>
  api.get(`/api/races/${id}/image`, { responseType: 'blob' })
export const getBenchmarkWeek = () => api.get('/api/benchmark/week')
export const createBenchmarkPlan = () => api.post('/api/benchmark/plan')
export const getOnboardingStatus = () => api.get('/api/onboarding/status')
export const deriveZones = (apply = false) =>
  api.post(`/api/benchmark/derive?apply=${apply}&days=60`)

// Chat
export const sendChat = (message) => api.post('/api/chat', { message })
export const clearChat = () => api.delete('/api/chat')

// History
export const getSessions = (params = {}) => api.get('/api/history/sessions', { params })
export const softDeleteSession = (id) => api.delete(`/api/history/sessions/${id}`)
export const hardDeleteSession = (id) => api.delete(`/api/history/sessions/${id}/hard`)
export const restoreSession = (id) => api.post(`/api/history/sessions/${id}/restore`)
export const updateReflection = (id, reflection) =>
  api.patch(`/api/history/sessions/${id}`, { reflection })
export const getHistoryPlans = () => api.get('/api/history/plans')

// Strava
export const getStravaStatus = () => api.get('/api/strava/status')
export const getStravaAuthUrl = () => api.get('/api/strava/auth')
export const getSchedulerStatus = () => api.get('/api/strava/scheduler')
// Kann je nach Anzahl neuer Aktivitäten dauern — pro Einheit zwei Strava-Requests
export const syncNow = () => api.post('/api/strava/sync-now', null, { timeout: 180000 })
export const disconnectStrava = () => api.delete('/api/integrations/strava')

// Anbindungen
export const getIntegrations = () => api.get('/api/integrations')
export const updateObsidian = (data) => api.patch('/api/integrations/obsidian', data)
export const testObsidian = (data = {}) =>
  api.post('/api/integrations/obsidian/test', data, { timeout: 20000 })
export const getWebhookStatus = () => api.get('/api/integrations/strava/webhook')
export const registerWebhook = (publicBaseUrl) =>
  api.post('/api/integrations/strava/webhook', { public_base_url: publicBaseUrl || null }, { timeout: 30000 })
export const deleteWebhook = () => api.delete('/api/integrations/strava/webhook')

// --- Gesundheit ---
export const getHealthStatus = () => api.get('/api/health/status')
export const getHealthEvents = () => api.get('/api/health/events')
export const reportIllness = (data) => api.post('/api/health/illness', data)
export const reportRecovered = (data = {}) => api.post('/api/health/recovered', data)
export const deleteHealthEvent = (id) => api.delete(`/api/health/events/${id}`)

// --- Konto ---
export const forgotPassword = (email) => api.post('/api/auth/forgot-password', { email })
export const resetPassword = (token, newPassword) =>
  api.post('/api/auth/reset-password', { token, new_password: newPassword })
export const verifyEmail = (token) => api.post('/api/auth/verify-email', { token })
export const resendVerification = () => api.post('/api/auth/resend-verification')
export const logoutEverywhere = () => api.post('/api/auth/logout')
export const exportAccount = () => api.get('/api/auth/export')
export const deleteAccount = (password, confirm) =>
  api.delete('/api/auth/account', { data: { password, confirm } })
export const getUpcomingRaces = () => api.get('/api/goals/upcoming')
export const deleteGoal = (id) => api.delete(`/api/goals/${id}`)
export const setSwimTest = (data) => api.post('/api/profile/swim-test', data)
export const clearSwimTest = () => api.delete('/api/profile/swim-test')
export const setThresholds = (data) => api.post('/api/profile/thresholds', data)
export const clearThresholds = () => api.delete('/api/profile/thresholds')
export const getHrvRange = () => api.get('/api/hrv/range')
export const setHrvRange = (data) => api.post('/api/hrv/range', data)
export const clearHrvRange = () => api.delete('/api/hrv/range')
export const getBudget = () => api.get('/api/budget')
export const getBudgetUsage = () => api.get('/api/budget/usage')
