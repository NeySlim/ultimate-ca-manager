/**
 * API Client - Centralized HTTP client with auth and error handling
 * Includes CSRF token management for security
 * 
 * Supported request options:
 *   method    - HTTP method (default: 'GET')
 *   headers   - Custom headers (merged with defaults)
 *   body      - Request body (auto-JSON stringified)
 *   responseType - Set to 'blob' for binary downloads
 * 
 * NOT supported (will be silently ignored):
 *   params    - Use buildQueryString() to append query params to the URL
 *   timeout   - Not implemented
 *   retry     - Not implemented
 */

import i18next from 'i18next'
import { loginUrl } from '../navigation/safeNext'
import { adoptSharedLock, adoptServerLock, SESSION_LOCKED_PROBLEM } from '../lib/sessionLock'

const API_BASE_URL = '/api/v2'

// Fired on window at each successful answer: a real-time socket the server refused tries again
export const API_ANSWERED_EVENT = 'ucm:api-answered'

function announceAnswered() {
  try {
    window.dispatchEvent(new CustomEvent(API_ANSWERED_EVENT))
  } catch {
    // a listener's failure never fails the call
  }
}

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
  413: 'The server or a proxy in front of it refused a request of this size.',
  415: 'Unsupported file type.',
  422: 'The data provided is invalid. Please check and try again.',
  429: 'Too many requests. Please wait a moment and try again.',
  500: 'An internal server error occurred. Please try again later.',
  502: 'The server is temporarily unavailable. Please try again later.',
  503: 'The service is currently unavailable. Please try again later.',
  504: 'The server took too long to respond. Please try again.',
}

// The server's answer to a write that met another one on SQLite (backend utils/sqlite_wait.BUSY_MESSAGE)
export const BUSY_MESSAGE = 'The database is busy with another write: retry shortly.'

export const isBusyRefusal = (status, data) => status === 503 && data?.detail === BUSY_MESSAGE

// Retry-After in seconds (RFC 9110 §10.2.3: delay or HTTP date), undefined when absent
export function parseRetryAfter(value) {
  if (!value) return undefined
  if (/^\d+$/.test(value.trim())) return Number(value.trim())
  const date = Date.parse(value)
  return Number.isNaN(date) ? undefined : Math.max(0, Math.ceil((date - Date.now()) / 1000))
}

/**
 * Build a user-friendly error message from an HTTP response.
 * Priority: backend message > status-code message > generic fallback.
 */
function buildErrorMessage(status, data, fallback = 'Request failed') {
  // Backend errors are an RFC 7807 problem document that also carries the
  // legacy keys: `message` (legacy) and `detail` (7807) hold the same text.
  // `data.error` is a boolean in that shape, so it must never be used as text.
  const backendMsg = (typeof data === 'object' && data !== null)
    ? (data.message || data.detail || (typeof data.error === 'string' ? data.error : null))
    : null
  return backendMsg || HTTP_ERROR_MESSAGES[status] || fallback
}

// One redirect for a burst of 401s: each navigation to /login can log in again with
// a client certificate, and calls sent while it loads would carry no cookie.
let loginRedirectPending = false

// A restore revokes every session, the page's own too: while held, a 401 leaves the
// report on screen and the sign-in follows its reload
let signOutHeld = false

export function holdSignOut(held = true) {
  signOutHeld = held
}

export function resetLoginRedirect() {
  loginRedirectPending = false
  signOutHeld = false
}

// The 401 of the server's authentication gate: refused before the route ran, so safe to send again
export const AUTHENTICATION_REQUIRED_PROBLEM = 'urn:ucm:problem:authentication-required'

// One check of the session for a burst of 401s: /auth/verify with the cookie held now, which a
// renewed identifier (TOTP, password, other sessions closed) replaced. False when it cannot tell.
let sessionCheck = null

function sessionStillOpen(client) {
  if (!sessionCheck) {
    sessionCheck = (async () => {
      try {
        const response = await fetch(`${client.baseURL}/auth/verify`, { method: 'GET', credentials: 'include' })
        const body = response.ok ? await response.json() : null
        if (body?.data?.authenticated !== true) return false
        client.setCsrfToken(body.data.csrf_token)
        return true
      } catch {
        return false
      }
    })().finally(() => { sessionCheck = null })
  }
  return sessionCheck
}

// A page restored from the back-forward cache keeps its module state: it sends again
if (typeof window !== 'undefined') {
  window.addEventListener('pageshow', (event) => {
    if (event.persisted) resetLoginRedirect()
  })
}

// POST through XMLHttpRequest, answering like the part of a fetch Response the client reads.
function xhrUpload(url, config, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', url)
    xhr.withCredentials = config.credentials === 'include'
    for (const [name, value] of Object.entries(config.headers || {})) xhr.setRequestHeader(name, value)
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded, event.total)
    }
    xhr.onload = () => resolve({
      ok: xhr.status >= 200 && xhr.status < 300,
      status: xhr.status,
      json: async () => JSON.parse(xhr.responseText),
    })
    xhr.onerror = () => reject(new TypeError('Network error'))
    xhr.send(config.body)
  })
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

  // `replayed`: this call already follows a 401 and a session check, its own 401 signs out
  async request(endpoint, options = {}, replayed = false) {
    if (import.meta.env.DEV && options.params) {
      console.warn(`⚠️ apiClient does not support 'params'. Use buildQueryString() to append query params to the URL. Called on: ${endpoint}`)
    }
    if (loginRedirectPending) {
      const error = new Error(HTTP_ERROR_MESSAGES[401])
      error.status = 401
      throw error
    }
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
      // Error bodies may be `application/problem+json` (RFC 7807) rather than
      // plain `application/json` -- both must be parsed as JSON.
      const contentType = response.headers.get('content-type')
      let data

      if (contentType && /application\/(problem\+)?json/.test(contentType)) {
        data = await response.json()
      } else if (options.responseType === 'blob') {
        data = await response.blob()
        const skipped = skippedCount(response.headers)
        if (skipped) data.skippedCount = skipped
        const exported = response.headers.get('x-exported-count')
        if (exported !== null && Number.isInteger(Number(exported))) data.exportedCount = Number(exported)
      } else {
        data = await response.text()
      }

      if (!response.ok) {
        const busy = isBusyRefusal(response.status, data)
        // Busy: nothing was written, the page's language says so and asks to send it again
        const msg = busy && i18next.isInitialized ? i18next.t('messages.errors.serverBusy') : buildErrorMessage(response.status, data)
        const error = new Error(msg)
        error.status = response.status
        if (busy) error.busy = true
        // What was asked, for a cause the page can show ("GET /api/v2/certificates")
        error.request = `${config.method} ${url.split('?')[0]}`
        error.data = data
        error.retryAfter = parseRetryAfter(response.headers.get('retry-after'))
        if (import.meta.env.DEV) {
          console.error(`❌ API error ${response.status}:`, error.message)
        }
        
        // Redirect to login on 401 (unless already on login page OR this is the login/verify request)
        const isLoginPage = window.location.pathname.includes('/login')
        const isAuthEndpoint = endpoint.includes('/auth/login') || endpoint.includes('/auth/verify')
          || endpoint.includes('/auth/unlock')
        if (response.status === 401 && signOutHeld) throw error

        // The server holds this session locked: its account's lock screen, without a session check
        if (response.status === 401 && data?.type === SESSION_LOCKED_PROBLEM) {
          if (!isLoginPage && !loginRedirectPending && !window.location.pathname?.includes('/login')) {
            loginRedirectPending = true
            if (!adoptServerLock(data.details)) adoptSharedLock()
            const { pathname = '/', search = '', hash = '' } = window.location
            window.location.href = loginUrl(pathname, search, hash)
          }
          throw error
        }

        // A 401 signs out only once the session is gone; the gate's refusal is sent again, once
        if (response.status === 401 && !isLoginPage && !isAuthEndpoint && !loginRedirectPending
            && !replayed && await sessionStillOpen(this)) {
          if (data?.type === AUTHENTICATION_REQUIRED_PROBLEM) return this.request(endpoint, options, true)
          throw error
        }
        // Read again after the session check: a route guard may have reached the sign-in page
        // meanwhile, and its ?next= already names the page asked for (one redirect, never nested)
        if (response.status === 401 && !isLoginPage && !isAuthEndpoint && !loginRedirectPending
            && !window.location.pathname?.includes('/login')) {
          console.warn('🚪 401 Unauthorized - redirecting to login')
          loginRedirectPending = true
          // A lock made in another tab of this account opens its lock screen, not the sign-in page
          adoptSharedLock()
          const { pathname = '/', search = '', hash = '' } = window.location
          window.location.href = loginUrl(pathname, search, hash)
        }
        
        throw error
      }

      if (import.meta.env.DEV) console.log(`✅ API response:`, data)
      announceAnswered()
      return data
    } catch (error) {
      // Network errors or fetch failures
      if (!error.status) {
        error.message = 'Network error. Please check your connection.'
        error.status = 0
        error.request = error.request || `${config.method} ${url.split('?')[0]}`
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

  // upload() and download() have neither the session check nor the single replay of the
  // gate's 401 that request() has: their 401 is thrown and never signs out.
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
    
    const { onProgress, ...fetchOptions } = options
    const config = {
      method: 'POST',
      body: formData,
      credentials: 'include',
      headers,
      // Don't set Content-Type - browser will set it with boundary for FormData
      ...fetchOptions,
    }

    if (import.meta.env.DEV) console.log(`📡 API UPLOAD ${url}`)

    try {
      // fetch reports no upload progress: a caller that wants it gets XHR, the same body.
      const response = onProgress
        ? await xhrUpload(url, config, onProgress)
        : await fetch(url, config)
      // A refusal from a proxy is an HTML page: its status still says what happened.
      let data = null
      try {
        data = await response.json()
      } catch (parseError) {
        if (response.ok) throw parseError
      }

      if (!response.ok) {
        const msg = buildErrorMessage(response.status, data, 'Upload failed')
        const error = new Error(msg)
        error.status = response.status
        error.data = data
        throw error
      }

      announceAnswered()
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

/** The rows a bulk export left out as unreadable (X-Skipped-*-Count), 0 when none. */
export function skippedCount(headers) {
  const raw = headers?.get?.('x-skipped-certificates-count') || headers?.get?.('x-skipped-cas-count')
  const n = Number(raw)
  return Number.isInteger(n) && n > 0 ? n : 0
}

/**
 * Build a URL query string from an object of params.
 * Skips null, undefined, and empty string values.
 * Use this instead of passing { params } to apiClient (not supported).
 * 
 * @param {Record<string, any>} params - Key-value pairs
 * @returns {string} Query string with leading '?' or empty string
 * 
 * @example
 * apiClient.get(`/certs${buildQueryString({ status: 'valid', search: '' })}`)
 * // → apiClient.get('/certs?status=valid')
 */
export function buildQueryString(params) {
  if (!params) return ''
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    // Array support: append each value separately for multi-select filters
    if (Array.isArray(value)) {
      value.forEach(v => {
        if (v !== undefined && v !== null && v !== '') {
          qs.append(key, String(v))
        }
      })
    } else {
      qs.append(key, String(value))
    }
  })
  const str = qs.toString()
  return str ? `?${str}` : ''
}

/**
 * Create a standard CRUD service for a given API endpoint.
 * Returns the five standard methods: getAll, getById, create, update, delete.
 * Spread the result and add any resource-specific methods on top.
 *
 * @param {string} endpoint - API path segment (e.g. 'templates', 'ssh/cas')
 * @returns {Object} Object with getAll, getById, create, update, delete
 *
 * @example
 * export const myService = {
 *   ...createCRUDService('my-resource'),
 *   customMethod: (id) => apiClient.post(`/my-resource/${id}/custom`)
 * }
 */
export function createCRUDService(endpoint) {
  return {
    getAll: (params) => apiClient.get(`/${endpoint}${buildQueryString(params)}`),
    getById: (id) => apiClient.get(`/${endpoint}/${id}`),
    create: (data) => apiClient.post(`/${endpoint}`, data),
    update: (id, data) => apiClient.put(`/${endpoint}/${id}`, data),
    delete: (id) => apiClient.delete(`/${endpoint}/${id}`),
  }
}
