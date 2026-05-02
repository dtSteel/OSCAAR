import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

// Attach access token to every request
api.interceptors.request.use(config => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// On 401 try to refresh, then retry once
api.interceptors.response.use(
  res => res,
  async err => {
    const original = err.config
    if (err.response?.status === 401 && !original._retry) {
      original._retry = true
      try {
        const { data } = await axios.post('/api/v1/auth/refresh', {}, { withCredentials: true })
        localStorage.setItem('access_token', data.access_token)
        original.headers.Authorization = `Bearer ${data.access_token}`
        return api(original)
      } catch {
        localStorage.removeItem('access_token')
        window.location.href = '/login'
      }
    }
    return Promise.reject(err)
  }
)

export default api

// ── Auth ─────────────────────────────────────────────
export const authApi = {
  register:        body  => api.post('/auth/register', body),
  login:           body  => api.post('/auth/login', body),
  logout:          ()    => api.post('/auth/logout'),
  me:              ()    => api.get('/auth/me'),
  changePassword:  body  => api.put('/auth/change-password', body),
  forgotPassword:  body  => api.post('/auth/forgot-password', body),
  resetPassword:   body  => api.post('/auth/reset-password', body),
  updateLanguage:  body  => api.put('/auth/language', body),
}

// ── Query ─────────────────────────────────────────────
export const queryApi = {
  submit:   body      => api.post('/query', body),
  history:  (page=1)  => api.get(`/query/history?page=${page}`),
  get:      id        => api.get(`/query/${id}`),
  delete:   id        => api.delete(`/query/${id}`),
  suggest:  ()        => api.post('/query/suggest', {}),
}

// ── Documents ─────────────────────────────────────────
export const docApi = {
  upload:   file => {
    const fd = new FormData()
    fd.append('file', file)
    return api.post('/documents/upload', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
  uploadUrl: body  => api.post('/documents/upload-url', body),
  list:      (page=1, status=null) => api.get(`/documents?page=${page}${status ? `&status_filter=${status}` : ''}`),
  get:       id    => api.get(`/documents/${id}`),
  delete:    id    => api.delete(`/documents/${id}`),
  stats:     ()    => api.get('/documents/status'),
  batch:     ()    => api.post('/documents/batch'),
}

// ── Admin ─────────────────────────────────────────────
export const adminApi = {
  users:       (page=1)  => api.get(`/admin/users?page=${page}`),
  getUser:     id        => api.get(`/admin/users/${id}`),
  disableUser: id        => api.patch(`/admin/users/${id}/disable`),
  enableUser:  id        => api.patch(`/admin/users/${id}/enable`),
  deleteUser:  id        => api.delete(`/admin/users/${id}`),
  setRole:     (id,body) => api.patch(`/admin/users/${id}/role`, body),
  usageReport: ()        => api.get('/admin/reports/usage'),
  auditLog:    (page=1)  => api.get(`/admin/reports/audit?page=${page}`),
  testEmail:   ()        => api.post('/admin/email/test'),
  health:      ()        => api.get('/admin/health'),
}
