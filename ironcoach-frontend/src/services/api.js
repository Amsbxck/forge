import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
  timeout: 60000,
})

// HRV
export const postHrv = (data) => api.post('/api/hrv', data)
export const getHrv = (limit = 14) => api.get('/api/hrv', { params: { limit } })
export const getLatestHrv = () => api.get('/api/hrv/latest')

// Metrics
export const getWeekMetrics = () => api.get('/api/metrics/week')
export const getTrends = (weeks = 4) => api.get('/api/metrics/trends', { params: { weeks } })
export const getProfile = () => api.get('/api/profile')
export const updateProfile = (data) => api.patch('/api/profile', data)

// Upload
export const uploadFile = (file) => {
  const form = new FormData()
  form.append('file', file)
  return api.post('/api/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

// Plan
export const generatePlan = (requests = '') =>
  api.get('/api/plan/generate', { params: { requests } })
export const getCurrentPlan = () => api.get('/api/plan/current')
export const getPlanByWeek = (week) => api.get(`/api/plan/${week}`)
export const downloadPlanPDF = (week) =>
  api.get(`/api/plan/${week}/pdf`, { responseType: 'blob' })

// Chat
export const sendChat = (message) => api.post('/api/chat', { message })
export const clearChat = () => api.delete('/api/chat')

// History
export const getSessions = (params = {}) => api.get('/api/history/sessions', { params })
export const softDeleteSession = (id) => api.delete(`/api/history/sessions/${id}`)
export const hardDeleteSession = (id) => api.delete(`/api/history/sessions/${id}/hard`)
export const restoreSession = (id) => api.post(`/api/history/sessions/${id}/restore`)
export const getHistoryPlans = () => api.get('/api/history/plans')

// Strava
export const getStravaStatus = () => api.get('/api/strava/status')
export const getStravaAuthUrl = () => api.get('/api/strava/auth')
