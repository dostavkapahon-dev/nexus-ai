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
  remove: (key) => api.delete(`/connections/${key}`),
  status: () => api.get('/connections/status'),
  recheck: (key) => api.post(`/connections/${key}/recheck`),
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

export const ai = {
  providers: () => api.get('/ai/providers'),
}

export const agent = {
  config: () => api.get('/agent/config'),
  saveConfig: (data) => api.post('/agent/config', data),
  skills: () => api.get('/agent/skills'),
  addSkill: (data) => api.post('/agent/skills', data),
  deleteSkill: (id) => api.delete(`/agent/skills/${id}`),
}

export const production = {
  jobs: (status = '', limit = 50) => api.get('/production/jobs', { params: { status, limit } }),
  next: () => api.get('/production/next'),
  create: (brief, kind = 'reel') => api.post('/production/jobs', { brief, kind }),
  result: (id, body) => api.post(`/production/${id}/result`, body),
  fail: (id, error) => api.post(`/production/${id}/fail`, { error }),
  retry: (id) => api.post(`/production/${id}/retry`),
  cancel: (id) => api.post(`/production/${id}/cancel`),
  setProducer: (producer) => api.post('/production/producer', { producer }),
}

export const agents = {
  list: () => api.get('/agents'),
  run: (key, task, context = '') => api.post(`/agents/${key}/run`, { task, context }),
}

export const agentProfile = {
  get: () => api.get('/agent-profile'),
  save: (data) => api.put('/agent-profile', data),
  preview: () => api.get('/agent-profile/preview'),
}

export const bot = {
  status: () => api.get('/bot/status'),
  testPost: (chat_id) => api.post('/bot/test-post', { chat_id }),
}

export const social = {
  accounts: () => api.get('/social/accounts'),
  health: () => api.get('/social/health'),
  healthOne: (platform) => api.get(`/social/health/${platform}`),
  refresh: (platform) => api.post(`/social/refresh/${platform}`),
  posts: (platform, limit = 10) => api.post(`/social/${platform}/posts`, { limit }),
  profile: (platform) => api.get(`/social/${platform}/profile`),
  oauthStart: () => api.get('/social/oauth/start'),
  connectInstagramToken: (access_token, account_id = '') =>
    api.post('/social/instagram/connect', { access_token, account_id }),
  webhookConfig: () => api.get('/social/webhook/config'),
  instagramAccess: () => api.get('/social/instagram/access'),
  browserStatus: () => api.get('/social/browser/status'),
  browserSession: (platform = 'instagram') => api.get('/social/browser/session', { params: { platform } }),
}

export const desktop = {
  status: () => api.get('/desktop/status'),
  command: (body) => api.post('/desktop/command', body),
  runAgent: (body) => api.post('/desktop/agent/run', body),
}

export const tasks = {
  list: (params) => api.get('/tasks', { params }),
  stats: () => api.get('/tasks/stats'),
  get: (id) => api.get(`/tasks/${id}`),
  cancel: (id) => api.post(`/tasks/${id}/cancel`),
}

export const strategy = {
  list: (niche_id = '') => api.get('/strategy', { params: { niche_id } }),
  current: (niche_id = '') => api.get('/strategy/current', { params: { niche_id } }),
  effectiveness: (niche_id = '') => api.get('/strategy/effectiveness', { params: { niche_id } }),
  activate: (id) => api.post(`/strategy/${id}/activate`),
  manual: (data) => api.post('/strategy/manual', data),
}

export const research = {
  history: (kind = '', limit = 20) => api.get('/research', { params: { kind, limit } }),
  stats: () => api.get('/research/stats'),
  context: () => api.get('/research/context'),
  competitors: () => api.get('/research/competitors'),
  trackCompetitor: (platform, handle) => api.post('/research/competitors', { platform, handle }),
  refreshCompetitors: () => api.post('/research/competitors/refresh'),
  stopCompetitor: (platform, handle) => api.delete(`/research/competitors/${platform}/${handle}`),
  search: (query, max_results = 8) => api.post('/research/search', { query, max_results }),
  fetch: (url) => api.post('/research/fetch', { url }),
  deep: (topic, pages = 3) => api.post('/research/deep', { topic, pages }),
}

export const performance = {
  overview: (days = 30) => api.get('/performance', { params: { days } }),
  top: (days = 30, limit = 10, worst = false) => api.get('/performance/top', { params: { days, limit, worst } }),
  collect: () => api.post('/performance/collect'),
  learn: (days = 30) => api.post('/performance/learn', null, { params: { days } }),
}

export const cost = {
  get: (hours = 24) => api.get('/cost', { params: { hours } }),
  setBudget: (budget_usd_day) => api.post('/cost/budget', { budget_usd_day }),
}

export const system = {
  summary: () => api.get('/system/summary'),
  health: () => api.get('/system/health'),
  build: () => api.get('/health'),
  agents: (hours = 24) => api.get('/system/agents', { params: { hours } }),
  scheduler: () => api.get('/system/scheduler'),
}

export const publishing = {
  queue: (status = '', limit = 50) => api.get('/publish/queue', { params: { status, limit } }),
  schedule: (body) => api.post('/publish/schedule', body),
  retry: (id) => api.post(`/publish/${id}/retry`),
  cancel: (id) => api.post(`/publish/${id}/cancel`),
  process: () => api.post('/publish/process'),
  pending: (limit = 50) => api.get('/publish/pending', { params: { limit } }),
  approve: (id) => api.post(`/publish/${id}/approve`),
  autoGet: () => api.get('/publish/auto'),
  autoSet: (body) => api.post('/publish/auto', body),
}

export const telegram = {
  status: () => api.get('/telegram/status'),
  botCheck: (token) => api.post('/telegram/bot/check', { token }),
  botConnect: (token) => api.post('/telegram/bot/connect', { token }),
  channels: () => api.get('/telegram/channels'),
  discover: () => api.get('/telegram/channels/discover'),
  check: (chat_id) => api.post('/telegram/channels/check', { chat_id }),
  test: (chat_id, keep = false) => api.post('/telegram/channels/test', { chat_id, keep }),
  add: (chat_id) => api.post('/telegram/channels/add', { chat_id }),
  setDefault: (chat_id) => api.post('/telegram/channels/default', { chat_id }),
  remove: (chat_id) => api.post('/telegram/channels/remove', { chat_id }),
  publish: (body) => api.post('/telegram/publish', body),
  message: (text, chat_id) => api.post('/telegram/message', { text, chat_id }),
  publicationStatus: (id) => api.get(`/telegram/publication/${id}`),
}

export const control = {
  command: (text) => api.post('/control/command', { text }),
  feed: (limit = 40) => api.get('/control/feed', { params: { limit } }),
}

export const automation = {
  director: (body) => api.post('/automation/director', body),
  video: (body) => api.post('/automation/video', body),
  publish: (planId) => api.post(`/automation/publish/${planId}`),
  factory: (body) => api.post('/automation/factory', body),
  brand: () => api.get('/automation/brand'),
  brandVoice: (voice) => api.post('/automation/brand/voice', { voice }),
  videoModels: () => api.get('/automation/video/models'),
}
