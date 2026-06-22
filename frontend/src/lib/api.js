import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

api.interceptors.request.use(cfg => {
  const token = localStorage.getItem('nx_token')
  if (token) cfg.headers['Authorization'] = `Bearer ${token}`
  return cfg
})

api.interceptors.response.use(
  r => r,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem('nx_token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export const auth = {
  login: (password) => api.post('/auth/login', { password }),
  googleLogin: (credential) => api.post('/auth/google', { credential }),
  googleClientId: () => api.get('/auth/google-client-id'),
  logout: () => localStorage.removeItem('nx_token'),
}

export const niches = {
  list: () => api.get('/niches'),
  get: (id) => api.get(`/niches/${id}`),
  create: (data) => api.post('/niches', data),
  update: (id, data) => api.patch(`/niches/${id}`, data),
  delete: (id) => api.delete(`/niches/${id}`),
  generatePlan: (id) => api.post(`/niches/${id}/plan`),
  getPlan: (id) => api.get(`/niches/${id}/plan`),
}

export const queue = {
  list: (params) => api.get('/queue', { params }),
  update: (id, data) => api.patch(`/queue/${id}`, data),
  delete: (id) => api.delete(`/queue/${id}`),
  generate: (id) => api.post(`/queue/${id}/generate`),
  publish: (id) => api.post(`/queue/${id}/publish`),
}

export const prompts = {
  list: () => api.get('/prompts'),
  get: (name) => api.get(`/prompts/${name}`),
  update: (name, data) => api.patch(`/prompts/${name}`, data),
  reset: (name) => api.post(`/prompts/${name}/reset`),
}

export const connections = {
  list: () => api.get('/connections'),
  save: (data) => api.post('/connections', data),
  test: (data) => api.post('/connections/test', data),
}

export const analytics = {
  get: (nicheId) => api.get(`/analytics/${nicheId}`),
}

export const profile = {
  get: () => api.get('/profile'),
  save: (data) => api.post('/profile', data),
  costEstimate: (params) => api.get('/profile/cost-estimate', { params }),
}

export const infrastructure = {
  check: () => api.post('/infrastructure/check'),
}

export const desktop = {
  status: () => api.get('/desktop/status'),
  command: (body) => api.post('/desktop/command', body),
  runAgent: (body) => api.post('/desktop/agent/run', body),
}

export const automation = {
  director: (body) => api.post('/automation/director', body),
  video: (body) => api.post('/automation/video', body),
  publish: (planId) => api.post(`/automation/publish/${planId}`),
  factory: (body) => api.post('/automation/factory', body),
  brand: () => api.get('/automation/brand'),
  videoModels: () => api.get('/automation/video/models'),
}
