const API_BASE = '/api/v2'

async function fetchAPI(endpoint, options = {}) {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  })
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Request failed' }))
    throw new Error(error.message || `HTTP ${response.status}`)
  }
  
  return response.json()
}

export const api = {
  login: (credentials) => fetchAPI('/auth/login', { method: 'POST', body: JSON.stringify(credentials) }),
  logout: () => fetchAPI('/auth/logout', { method: 'POST' }),
  getDashboardStats: () => fetchAPI('/dashboard/stats'),
  getCAs: () => fetchAPI('/cas'),
  getCertificates: () => fetchAPI('/certificates'),
  getUsers: () => fetchAPI('/users'),
}
