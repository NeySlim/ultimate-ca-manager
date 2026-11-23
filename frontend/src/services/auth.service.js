/**
 * Authentication Service
 * Handles login, logout, and CSRF token management
 */
import { apiClient } from './apiClient'
import { clearUnconfirmedLock, readUnconfirmedLock } from '../lib/sessionLock'

let pendingLock = null

// A lock the server did not take (409, 5xx, network) is sent again after these delays; then the
// session is signed out, so none stays open behind the lock screen. A 401 is sent once more (a
// renewal may have just replaced the cookie), a second one means the session is gone.
// Until one of them is answered, the lock stays marked unconfirmed for the next load.
const LOCK_RETRY_DELAYS_MS = [500, 1000, 2000]
const wait = (ms) => new Promise(resolve => setTimeout(resolve, ms))

// The lock belongs to the account its unconfirmed mark named when it was sent: a sign-in or a
// sign-out since, in any tab, removes or replaces the mark, and nothing more is sent for it.
// Without a mark (storage blocked) there is nothing to tell them apart by.
const stillOwed = (owner) => !owner || readUnconfirmedLock()?.username === owner.username

function superseded(error) {
  return Object.assign(new Error('Lock superseded by a sign-in or sign-out'), { superseded: true, cause: error })
}

async function postLock(reason, owner) {
  let refused = false
  for (let attempt = 0; ; attempt += 1) {
    try {
      return await apiClient.post('/auth/lock', { reason })
    } catch (error) {
      if ((error?.status === 401 && refused) || attempt >= LOCK_RETRY_DELAYS_MS.length) throw error
      if (error?.status === 401) refused = true
      await wait(LOCK_RETRY_DELAYS_MS[attempt])
      if (!stillOwed(owner)) throw superseded(error)
      if (error?.status === 403) {
        // A CSRF token gone stale: the session check hands a fresh one
        try {
          const response = await apiClient.get('/auth/verify')
          if (response?.data?.csrf_token) apiClient.setCsrfToken(response.data.csrf_token)
        } catch { /* sent again with the token held */ }
      }
    }
  }
}

export const authService = {
  async login(username, password) {
    const response = await apiClient.post('/auth/login', { username, password })
    
    // Store CSRF token from login response
    if (response?.data?.csrf_token) {
      apiClient.setCsrfToken(response.data.csrf_token)
    }
    
    return response
  },

  async logout() {
    const response = await apiClient.post('/auth/logout')
    
    // Clear CSRF token on logout; a lock not confirmed has nothing left to lock
    apiClient.clearCsrfToken()
    clearUnconfirmedLock()
    
    return response
  },

  // Locks the session on the server, which keeps it until it is unlocked; `reason` is 'manual' or 'idle'
  lock(reason) {
    const owner = readUnconfirmedLock()
    // Only the mark this lock was sent under: without one there is nothing of its own to clear
    const clearOwnMark = () => { if (owner) clearUnconfirmedLock(owner.username) }
    const request = (async () => {
      // The CSRF token goes with the locked session, never one a sign-in set meanwhile
      let ownToken = true
      try {
        const answer = await postLock(reason, owner)
        ownToken = stillOwed(owner)
        clearOwnMark()
        return answer
      } catch (error) {
        if (error?.superseded || !stillOwed(owner)) {
          ownToken = false
          throw error?.superseded ? error : superseded(error)
        }
        if (error?.status === 401) {
          clearOwnMark()
        } else {
          try {
            await apiClient.post('/auth/logout')
            clearOwnMark()
          } catch (signOut) {
            if (signOut?.status === 401) clearOwnMark()
          }
        }
        throw error
      } finally {
        if (ownToken) apiClient.clearCsrfToken()
      }
    })()
    pendingLock = request.catch(() => {})
    return request
  },

  // Settled once the lock this tab sent has been answered: the lock screen reads the server after it
  whenLocked() {
    return pendingLock || Promise.resolve()
  },

  async getCurrentUser() {
    const response = await apiClient.get('/auth/verify')
    
    // Refresh CSRF token on verify
    if (response?.data?.csrf_token) {
      apiClient.setCsrfToken(response.data.csrf_token)
    }
    
    return response
  },

  async verifySession() {
    const response = await apiClient.get('/auth/verify')
    
    // Refresh CSRF token on verify
    if (response?.data?.csrf_token) {
      apiClient.setCsrfToken(response.data.csrf_token)
    }
    
    return response
  },

  async isEmailConfigured() {
    return apiClient.get('/auth/email-configured')
  },

  async ldapLogin(username, password, providerId) {
    return apiClient.post('/sso/ldap/login', { username, password, provider_id: providerId })
  },

  async getSsoProviders() {
    return apiClient.get('/sso/available')
  },

  async forgotPassword(email) {
    return apiClient.post('/auth/forgot-password', { email })
  },

  async resetPassword(token, password) {
    return apiClient.post('/auth/reset-password', { token, password })
  }
}
