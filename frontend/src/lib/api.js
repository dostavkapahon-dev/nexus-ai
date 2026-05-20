import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

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
