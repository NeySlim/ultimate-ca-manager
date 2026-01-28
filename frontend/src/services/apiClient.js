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
}

export const apiClient = new APIClient()
