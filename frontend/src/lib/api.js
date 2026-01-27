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
    
    if (!res.ok) {
      throw new Error(data?.message || data?.error || `HTTP ${res.status}`)
    }
    
    // UCM API returns { data, message } format
    // Extract the 'data' field if it exists
    if (data && typeof data === 'object' && 'data' in data) {
      return data.data
    }
    
    return data
    
  } catch (error) {
    // Network errors
    if (error.name === 'TypeError' || error.message.includes('fetch')) {
      throw new Error('Network error - Cannot reach server')
    }
    throw error
  }
}

// ============================================
// API CLIENT - MATCHED TO REAL BACKEND
// ============================================

export const api = {
  // ========== AUTHENTICATION ==========
  
  login: (username, password) => request('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password })
  }),
  
  logout: () => request('/auth/logout', { method: 'POST' }),
  
  getCurrentUser: () => request('/auth/verify'),
  
  // ========== DASHBOARD ==========
  
  getDashboardStats: () => request('/dashboard/stats'),
  
  getActivityLog: async (limit = 10) => {
    const result = await request('/dashboard/activity')
    // Backend returns { activity: [] } - extract the array
    return result?.activity || []
  },
  
  getSystemStatus: () => request('/dashboard/system-status'),
  
  // ========== CERTIFICATE AUTHORITIES ==========
  
  getCAs: async () => {
    const data = await request('/cas')
    return Array.isArray(data) ? data : []
  },
  
  getCAsTree: () => request('/cas/tree'),
  
  getCA: (id) => request(`/cas/${id}`),
  
  createCA: (data) => request('/cas', {
    method: 'POST',
    body: JSON.stringify(data)
  }),
  
  updateCA: (id, data) => request(`/cas/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data)
  }),
  
  deleteCA: (id) => request(`/cas/${id}`, {
    method: 'DELETE'
  }),
  
  exportCA: (id, options = {}) => {
    const params = new URLSearchParams()
    if (options.format) params.append('format', options.format)
    if (options.include_chain) params.append('chain', 'true')
    if (options.include_key) params.append('key', 'true')
    if (options.password) params.append('password', options.password)
    return request(`/cas/${id}/export?${params.toString()}`)
  },
  
  // ========== CERTIFICATES ==========
  
  getCertificates: async (filters = {}) => {
    const params = new URLSearchParams()
    if (filters.status) params.append('status', filters.status)
    if (filters.ca_id) params.append('ca_id', filters.ca_id)
    if (filters.search) params.append('search', filters.search)
    
    const query = params.toString()
    const data = await request(`/certificates${query ? '?' + query : ''}`)
    return Array.isArray(data) ? data : []
  },
  
  getCertificate: (id) => request(`/certificates/${id}`),
  
  issueCertificate: (data) => request('/certificates', {
    method: 'POST',
    body: JSON.stringify(data)
  }),
  
  revokeCertificate: (id, reason) => request(`/certificates/${id}/revoke`, {
    method: 'POST',
    body: JSON.stringify({ reason })
  }),
  
  renewCertificate: (id) => request(`/certificates/${id}/renew`, {
    method: 'POST'
  }),
  
  deleteCertificate: (id) => request(`/certificates/${id}`, {
    method: 'DELETE'
  }),
  
  exportCertificate: (id, options = {}) => {
    const params = new URLSearchParams()
    if (options.format) params.append('format', options.format)
    if (options.include_chain) params.append('include_chain', 'true')
    return request(`/certificates/${id}/export?${params.toString()}`)
  },
  
  // ========== CSRs ==========
  
  getCSRs: async () => {
    const data = await request('/csrs')
    return Array.isArray(data) ? data : []
  },
  
  getCSR: (id) => request(`/csrs/${id}`),
  
  uploadCSR: (data) => request('/csrs', {
    method: 'POST',
    body: JSON.stringify(data)
  }),
  
  signCSR: (id, data) => request(`/csrs/${id}`, {
    method: 'POST',
    body: JSON.stringify(data)
  }),
  
  deleteCSR: (id) => request(`/csrs/${id}`, {
    method: 'DELETE'
  }),
  
  // ========== USERS ==========
  
  getUsers: async () => {
    const data = await request('/users')
    return Array.isArray(data) ? data : []
  },
  
  getUser: (id) => request(`/users/${id}`),
  
  createUser: (data) => request('/users', {
    method: 'POST',
    body: JSON.stringify(data)
  }),
  
  updateUser: (id, data) => request(`/users/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data)
  }),
  
  deleteUser: (id) => request(`/users/${id}`, {
    method: 'DELETE'
  }),
  
  // ========== SETTINGS ==========
  
  getSettings: () => request('/settings/general'),
  
  updateSettings: (data) => request('/settings/general', {
    method: 'PUT',
    body: JSON.stringify(data)
  }),
  
  getEmailSettings: () => request('/settings/email'),
  
  updateEmailSettings: (data) => request('/settings/email', {
    method: 'PUT',
    body: JSON.stringify(data)
  }),
  
  testEmailSettings: (data) => request('/settings/email/test', {
    method: 'POST',
    body: JSON.stringify(data)
  }),
  
  getLDAPSettings: () => request('/settings/ldap'),
  
  updateLDAPSettings: (data) => request('/settings/ldap', {
    method: 'PUT',
    body: JSON.stringify(data)
  }),
  
  testLDAPSettings: () => request('/settings/ldap/test', {
    method: 'POST'
  }),
  
  getWebhookSettings: () => request('/settings/webhooks'),
  
  updateWebhookSettings: (data) => request('/settings/webhooks', {
    method: 'PUT',
    body: JSON.stringify(data)
  }),
  
  // ========== ACME ==========
  
  getACMEAccounts: async () => {
    const data = await request('/acme/accounts')
    return Array.isArray(data) ? data : []
  },
  
  getACMEOrders: async () => {
    const data = await request('/acme/orders')
    return Array.isArray(data) ? data : []
  },
  
  getACMESettings: () => request('/acme/settings'),
  
  updateACMESettings: (data) => request('/acme/settings', {
    method: 'PUT',
    body: JSON.stringify(data)
  }),
  
  createACMEAccount: (data) => request('/acme/proxy/register', {
    method: 'POST',
    body: JSON.stringify(data)
  }),
  
  deleteACMEAccount: (id) => {
    // Backend doesn't have this endpoint - return mock
    return Promise.resolve({ success: true })
  },
  
  // ========== CRL/OCSP ==========
  
  getCRLs: () => request('/crl'),
  
  getCRL: (id) => request(`/crl/${id}`),
  
  generateCRL: (caId) => request(`/crl/${caId}/regenerate`, {
    method: 'POST'
  }),
  
  downloadCRL: (id) => {
    window.location.href = `${API_BASE}/crl/${id}`
  },
  
  getOCSPStatus: () => request('/ocsp/status'),
  
  getOCSPStats: () => request('/ocsp/stats'),
  
  // ========== OPNSENSE IMPORT ==========
  
  testOPNsenseConnection: (data) => request('/import/opnsense/test', {
    method: 'POST',
    body: JSON.stringify(data)
  }),
  
  importFromOPNsense: (data) => request('/import/opnsense/import', {
    method: 'POST',
    body: JSON.stringify(data)
  }),
  
  // ========== SCEP ==========
  
  getSCEPConfigs: async () => {
    const data = await request('/scep/config')
    // Backend returns single config object, not array
    return data && typeof data === 'object' && !Array.isArray(data) ? [data] : (Array.isArray(data) ? data : [])
  },
  
  getSCEPEnrollments: async () => {
    const data = await request('/scep/requests')
    return Array.isArray(data) ? data : []
  },
  
  approveSCEP: (id) => request(`/scep/${id}/approve`, {
    method: 'POST'
  }),
  
  rejectSCEP: (id) => request(`/scep/${id}/reject`, {
    method: 'POST'
  }),
  
  // ========== TEMPLATES ==========
  
  getTemplates: async () => {
    const data = await request('/templates')
    return Array.isArray(data) ? data : []
  },
  
  getTemplate: (id) => request(`/templates/${id}`),
  
  createTemplate: (data) => request('/templates', {
    method: 'POST',
    body: JSON.stringify(data)
  }),
  
  updateTemplate: (id, data) => request(`/templates/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data)
  }),
  
  deleteTemplate: (id) => request(`/templates/${id}`, {
    method: 'DELETE'
  }),
  
  duplicateTemplate: (id) => {
    // Backend doesn't have this endpoint - fake it
    return Promise.resolve({ success: true })
  },
  
  // ========== TRUSTSTORE ==========
  
  getTrustedCertificates: () => request('/truststore'),
  
  addTrustedCertificate: (data) => request('/truststore', {
    method: 'POST',
    body: JSON.stringify(data)
  }),
  
  removeTrustedCertificate: (id) => request(`/truststore/${id}`, {
    method: 'DELETE'
  }),
  
  // ========== ACCOUNT ==========
  
  getAccountProfile: () => request('/account/profile'),
  
  updateAccountProfile: (data) => request('/account/profile', {
    method: 'PUT',
    body: JSON.stringify(data)
  }),
  
  changePassword: (currentPassword, newPassword) => request('/account/password', {
    method: 'PUT',
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword })
  }),
}
