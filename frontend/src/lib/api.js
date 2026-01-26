const API_BASE = 'https://localhost:8443/api/v2'

let token = localStorage.getItem('ucm_token')

export const api = {
  async login(username, password) {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    })
    
    if (!res.ok) throw new Error('Login failed')
    
    const data = await res.json()
    token = data.data.access_token
    localStorage.setItem('ucm_token', token)
    return data.data
  },
  
  async get(endpoint) {
    const res = await fetch(`${API_BASE}${endpoint}`, {
      headers: token ? { 'Authorization': `Bearer ${token}` } : {}
    })
    
    if (!res.ok) {
      if (res.status === 401) {
        localStorage.removeItem('ucm_token')
        token = null
        throw new Error('Unauthorized')
      }
      throw new Error(`HTTP ${res.status}`)
    }
    
    return res.json()
  },
  
  isAuthenticated() {
    return !!token
  },
  
  logout() {
    localStorage.removeItem('ucm_token')
    token = null
  }
}
