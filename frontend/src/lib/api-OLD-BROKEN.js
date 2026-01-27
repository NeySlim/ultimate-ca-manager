const API_BASE = '/api/v2'  // Relative URL to avoid CORS issues

// ============================================
// LOW-LEVEL HTTP CLIENT (Session-based auth)
// ============================================

async function request(endpoint, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers
  }
  
  try {
    const res = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers,
      credentials: 'include' // Send session cookies
    })
    
    // Handle 401 Unauthorized
    if (res.status === 401) {
      window.location.href = '/login'
      throw new Error('Unauthorized - Please login')
    }
    
    // Parse response
    const contentType = res.headers.get('content-type')
    let data
    
    if (contentType && contentType.includes('application/json')) {
      data = await res.json()
    } else {
      data = await res.text()
    }
    
    // Handle errors
    if (!res.ok) {
      const message = data?.message || data?.error || `HTTP ${res.status}: ${res.statusText}`
      throw new Error(message)
    }
    
    // UCM API returns { success, data, message } or { data, message }
    return data?.data !== undefined ? data.data : data
    
  } catch (error) {
    // Network errors
    if (error.name === 'TypeError' || error.message.includes('fetch')) {
      throw new Error('Network error - Cannot reach server')
    }
    throw error
  }
}

// ============================================
// API CLIENT
// ============================================

export const api = {
  // ========== AUTHENTICATION ==========
  
  async login(username, password) {
    const data = await request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password })
    })
    
    // Session cookie set by backend
    // No need to store token
    return data
  },
  
  async logout() {
    try {
      await request('/auth/logout', { method: 'POST' })
    } finally {
      // Session cleared by backend
      token = null
    }
  },
  
  isAuthenticated() {
    return true // Optimistic
  },
  
  // ========== DASHBOARD ==========
  
  async getDashboardStats() {
    return request('/dashboard/stats')
  },
  
  async getActivityLog(limit = 10) {
    return request(`/activity?limit=${limit}`)
  },
  
  // ========== CERTIFICATE AUTHORITIES ==========
  
  async getCAs() {
    return request('/cas')
  },
  
  async getCA(id) {
    return request(`/cas/${id}`)
  },
  
  async createCA(data) {
    return request('/cas', {
      method: 'POST',
      body: JSON.stringify(data)
    })
  },
  
  async deleteCA(id) {
    return request(`/cas/${id}`, {
      method: 'DELETE'
    })
  },
  
  async exportCA(id, format = 'pem') {
    return request(`/cas/${id}/export?format=${format}`)
  },
  
  // ========== CERTIFICATES ==========
  
  async getCertificates(filters = {}) {
    const params = new URLSearchParams()
    if (filters.status) params.append('status', filters.status)
    if (filters.ca_id) params.append('ca_id', filters.ca_id)
    if (filters.search) params.append('search', filters.search)
    
    const query = params.toString()
    return request(`/certificates${query ? '?' + query : ''}`)
  },
  
  async getCertificate(id) {
    return request(`/certificates/${id}`)
  },
  
  async issueCertificate(data) {
    return request('/certificates', {
      method: 'POST',
      body: JSON.stringify(data)
    })
  },
  
  async revokeCertificate(id, reason) {
    return request(`/certificates/${id}/revoke`, {
      method: 'POST',
      body: JSON.stringify({ reason })
    })
  },
  
  async renewCertificate(id) {
    return request(`/certificates/${id}/renew`, {
      method: 'POST'
    })
  },
  
  async exportCertificate(id, format = 'pem') {
    return request(`/certificates/${id}/export?format=${format}`)
  },
  
  // ========== CSRs ==========
  
  async getCSRs() {
    return request('/csrs')
  },
  
  async uploadCSR(pem) {
    return request('/csrs', {
      method: 'POST',
      body: JSON.stringify({ csr_pem: pem })
    })
  },
  
  async signCSR(id, data) {
    return request(`/csrs/${id}/sign`, {
      method: 'POST',
      body: JSON.stringify(data)
    })
  },
  
  async deleteCSR(id) {
    return request(`/csrs/${id}`, {
      method: 'DELETE'
    })
  },
  
  // ========== USERS ==========
  
  async getUsers() {
    return request('/users')
  },
  
  async getUser(id) {
    return request(`/users/${id}`)
  },
  
  async createUser(data) {
    return request('/users', {
      method: 'POST',
      body: JSON.stringify(data)
    })
  },
  
  async updateUser(id, data) {
    return request(`/users/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    })
  },
  
  async deleteUser(id) {
    return request(`/users/${id}`, {
      method: 'DELETE'
    })
  },
  
  // ========== SETTINGS ==========
  
  async getSettings() {
    return request('/settings')
  },
  
  async updateSettings(category, data) {
    return request(`/settings/${category}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    })
  },
  
  async testEmailSettings() {
    return request('/settings/email/test', {
      method: 'POST'
    })
  },
  
  async testLDAPSettings() {
    return request('/settings/ldap/test', {
      method: 'POST'
    })
  },
  
  // ========== TEMPLATES ==========
  
  async getTemplates() {
    return request('/templates')
  },
  
  async getTemplate(id) {
    return request(`/templates/${id}`)
  },
  
  async createTemplate(data) {
    return request('/templates', {
      method: 'POST',
      body: JSON.stringify(data)
    })
  },
  
  // ========== CRL ==========
  
  async getCRLs() {
    return request('/crl')
  },
  
  async generateCRL(ca_id) {
    return request('/crl/generate', {
      method: 'POST',
      body: JSON.stringify({ ca_id })
    })
  },
  
  // ========== OCSP ==========
  
  async getOCSPStatus() {
    return request('/ocsp/status')
  },
  
  // ========== ACME ==========
  
  async getACMEAccounts() {
    return request('/acme/accounts')
  },
  
  async getACMEOrders() {
    return request('/acme/orders')
  },
  
  // ========== SCEP ==========
  
  async getSCEPClients() {
    return request('/scep/clients')
  }
}
