/**
 * API Client - Centralized HTTP client with auth and error handling
 */

const API_BASE_URL = '/api/v2'

class APIClient {
  constructor() {
    this.baseURL = API_BASE_URL
  }

  async request(endpoint, options = {}) {
    const url = `${this.baseURL}${endpoint}`
    
    const config = {
      method: options.method || 'GET',
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      credentials: 'include', // Important pour les cookies de session
      ...options,
    }

    // Add body if present
    if (options.body && typeof options.body === 'object') {
      config.body = JSON.stringify(options.body)
    }

    console.log(`📡 API ${config.method} ${url}`, config.credentials)

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
        const error = new Error(data.message || data.error || 'Request failed')
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

      console.log(`✅ API response:`, data)
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
    
    const config = {
      method: 'POST',
      body: formData,
      credentials: 'include',
      // Don't set Content-Type - browser will set it with boundary for FormData
      ...options,
    }

    console.log(`📡 API UPLOAD ${url}`)

    try {
      const response = await fetch(url, config)
      const data = await response.json()

      if (!response.ok) {
        const error = new Error(data.message || data.error || 'Upload failed')
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
      throw new Error('Download failed')
    }
    
    return response.blob()
  }
}

export const apiClient = new APIClient()
