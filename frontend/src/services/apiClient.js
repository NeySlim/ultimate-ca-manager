/**
 * API Client - Centralized HTTP client with auth and error handling
 * Includes CSRF token management for security
 */

const API_BASE_URL = '/api/v2'

// CSRF token storage key
const CSRF_TOKEN_KEY = 'ucm_csrf_token'

// Human-readable error messages for HTTP status codes
const HTTP_ERROR_MESSAGES = {
  400: 'Invalid request. Please check your input and try again.',
  401: 'Your session has expired. Please log in again.',
  403: 'You do not have permission to perform this action.',
  404: 'The requested resource was not found.',
  405: 'This operation is not supported.',
  408: 'The request timed out. Please try again.',
  409: 'Conflict: this resource already exists or is in use.',
  413: 'The file is too large. Maximum upload size is 10 MB.',
  415: 'Unsupported file type.',
  422: 'The data provided is invalid. Please check and try again.',
  429: 'Too many requests. Please wait a moment and try again.',
  500: 'An internal server error occurred. Please try again later.',
  502: 'The server is temporarily unavailable. Please try again later.',
  503: 'The service is currently unavailable. Please try again later.',
  504: 'The server took too long to respond. Please try again.',
}

/**
 * Build a user-friendly error message from an HTTP response.
 * Priority: backend message > status-code message > generic fallback.
 */
function buildErrorMessage(status, data, fallback = 'Request failed') {
  const backendMsg = (typeof data === 'object' && data !== null)
    ? (data.message || data.error)
    : null
  return backendMsg || HTTP_ERROR_MESSAGES[status] || fallback
}

class APIClient {
  constructor() {
    this.baseURL = API_BASE_URL
  }

  /**
   * Get stored CSRF token
   */
  getCsrfToken() {
    return sessionStorage.getItem(CSRF_TOKEN_KEY)
  }

  /**
   * Store CSRF token (called after login/verify)
   */
  setCsrfToken(token) {
    if (token) {
      sessionStorage.setItem(CSRF_TOKEN_KEY, token)
    }
  }

  /**
   * Clear CSRF token (called on logout)
   */
  clearCsrfToken() {
    sessionStorage.removeItem(CSRF_TOKEN_KEY)
  }

  async request(endpoint, options = {}) {
    const url = `${this.baseURL}${endpoint}`
    
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    }

    // Add CSRF token for state-changing methods
    const method = options.method || 'GET'
    if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
      const csrfToken = this.getCsrfToken()
      if (csrfToken) {
        headers['X-CSRF-Token'] = csrfToken
      }
    }

    const config = {
      method,
      headers,
      credentials: 'include', // Important pour les cookies de session
      ...options,
    }

    // Add body if present
    if (options.body && typeof options.body === 'object') {
      config.body = JSON.stringify(options.body)
    }

    if (import.meta.env.DEV) console.log(`📡 API ${config.method} ${url}`, config.credentials)

    try {
      const response = await fetch(url, config)
      
      // Handle different response types
      const contentType = response.headers.get('content-type')
      let data
      
      if (contentType && contentType.includes('application/json')) {
        data = await response.json()
      } else if (options.responseType === 'blob') {
        data = await response.blob()
      } else {
        data = await response.text()
      }

      if (!response.ok) {
        const msg = buildErrorMessage(response.status, data)
        const error = new Error(msg)
        error.status = response.status
        error.data = data
        console.error(`❌ API error ${response.status}:`, error.message)
        
        // Redirect to login on 401 (unless already on login page OR this is the login/verify request)
        const isLoginPage = window.location.pathname.includes('/login')
        const isAuthEndpoint = endpoint.includes('/auth/login') || endpoint.includes('/auth/verify')
        
        if (response.status === 401 && !isLoginPage && !isAuthEndpoint) {
          console.warn('🚪 401 Unauthorized - redirecting to login')
          window.location.href = '/login'
        }
        
        throw error
      }

      if (import.meta.env.DEV) console.log(`✅ API response:`, data)
      return data
    } catch (error) {
      // Network errors or fetch failures
      if (!error.status) {
        error.message = 'Network error. Please check your connection.'
        error.status = 0
      }
      throw error
    }
  }

  get(endpoint, options = {}) {
    return this.request(endpoint, { ...options, method: 'GET' })
  }

  post(endpoint, body, options = {}) {
    return this.request(endpoint, { ...options, method: 'POST', body })
  }

  put(endpoint, body, options = {}) {
    return this.request(endpoint, { ...options, method: 'PUT', body })
  }

  delete(endpoint, options = {}) {
    return this.request(endpoint, { ...options, method: 'DELETE' })
  }

  patch(endpoint, body, options = {}) {
    return this.request(endpoint, { ...options, method: 'PATCH', body })
  }

  /**
   * Upload FormData (multipart/form-data)
   * @param {string} endpoint - API endpoint
   * @param {FormData} formData - Form data to upload
   * @param {object} options - Additional options
   */
  async upload(endpoint, formData, options = {}) {
    const url = `${this.baseURL}${endpoint}`
    
    // Build headers with CSRF token
    const headers = { ...options.headers }
    const csrfToken = this.getCsrfToken()
    if (csrfToken) {
      headers['X-CSRF-Token'] = csrfToken
    }
    
    const config = {
      method: 'POST',
      body: formData,
      credentials: 'include',
      headers,
      // Don't set Content-Type - browser will set it with boundary for FormData
      ...options,
    }

    if (import.meta.env.DEV) console.log(`📡 API UPLOAD ${url}`)

    try {
      const response = await fetch(url, config)
      const data = await response.json()

      if (!response.ok) {
        const msg = buildErrorMessage(response.status, data, 'Upload failed')
        const error = new Error(msg)
        error.status = response.status
        error.data = data
        throw error
      }

      return data
    } catch (error) {
      if (!error.status) {
        error.message = 'Network error. Please check your connection.'
        error.status = 0
      }
      throw error
    }
  }

  /**
   * Download file as blob
   * @param {string} endpoint - API endpoint
   * @param {object} options - Additional options
   */
  async download(endpoint, options = {}) {
    const url = `${this.baseURL}${endpoint}`
    
    const config = {
      method: 'GET',
      credentials: 'include',
      ...options,
    }

    const response = await fetch(url, config)
    
    if (!response.ok) {
      const msg = HTTP_ERROR_MESSAGES[response.status] || 'Download failed'
      throw new Error(msg)
    }
    
    return response.blob()
  }
}

export const apiClient = new APIClient()
