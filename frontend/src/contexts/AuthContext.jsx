/**
 * Auth Context - Global authentication state
 * 
 * On mount, ALWAYS calls /auth/verify to check for active session.
 * This enables mTLS auto-login: the middleware creates the session
 * during the TLS handshake, and checkSession() picks it up.
 */
import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { authService } from '../services/auth.service'
import { apiClient } from '../services/apiClient'

const AuthContext = createContext()

const debug = import.meta.env.DEV ? console.log : () => {}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [loading, setLoading] = useState(true)
  const [sessionChecked, setSessionChecked] = useState(false)
  const [permissions, setPermissions] = useState([])
  const [role, setRole] = useState(null)
  const [forcePasswordChange, setForcePasswordChange] = useState(false)

  const checkSession = useCallback(async () => {
    try {
      debug('🔍 Checking session...')
      const response = await authService.getCurrentUser()

      const userData = response.data || response

      if (!userData.authenticated) {
        debug('ℹ️ Not authenticated')
        setUser(null)
        setIsAuthenticated(false)
        setPermissions([])
        setRole(null)
        return false
      }

      setUser(userData.user || userData)
      setIsAuthenticated(true)
      setPermissions(userData.permissions || [])
      setRole(userData.role || null)
      debug('✅ Session valid:', userData.user?.username)
      return true
    } catch (error) {
      debug('❌ Session check failed:', error.message)
      setUser(null)
      setIsAuthenticated(false)
      setPermissions([])
      setRole(null)
      return false
    } finally {
      setLoading(false)
      setSessionChecked(true)
    }
  }, [])

  // Always check session on mount — enables mTLS auto-login on /login too
  useEffect(() => {
    checkSession()
  }, [checkSession])

  const login = async (username, password, preAuthData = null) => {
    setLoading(true)
    try {
      debug('🔐 Login called:', { username, hasPreAuthData: !!preAuthData })
      
      let response
      if (preAuthData) {
        // Already authenticated via multi-method (mTLS, WebAuthn, etc.)
        response = { data: preAuthData }
        // Store CSRF token from pre-auth response
        const csrfToken = preAuthData.csrf_token
        if (csrfToken) {
          apiClient.setCsrfToken(csrfToken)
        }
      } else {
        // Legacy password auth
        debug('🔐 Attempting password login for:', username)
        response = await authService.login(username, password)
      }
      
      debug('✅ Login response:', response)
      const userData = response.data?.user || response.user || { username }
      setUser(userData)
      setIsAuthenticated(true)
      setPermissions(response.data?.permissions || response.permissions || [])
      setRole(response.data?.role || response.role || null)
      setForcePasswordChange(response.data?.force_password_change || false)
      debug('✅ User authenticated:', userData)
      return response
    } catch (error) {
      debug('❌ Login failed:', error.message)
      setUser(null)
      setIsAuthenticated(false)
      setPermissions([])
      setRole(null)
      throw error
    } finally {
      setLoading(false)
    }
  }

  const logout = async () => {
    setLoading(true)
    try {
      debug('🔓 Logging out...')
      await authService.logout()
      debug('✅ Logout successful')
    } catch (error) {
      debug('❌ Logout error:', error)
    } finally {
      // Always clear local state regardless of API success
      setUser(null)
      setIsAuthenticated(false)
      setPermissions([])
      setRole(null)
      setForcePasswordChange(false)
      setLoading(false)
      debug('🔓 Local session cleared')
    }
  }

  const clearForcePasswordChange = () => setForcePasswordChange(false)

  const value = {
    user,
    isAuthenticated,
    loading,
    sessionChecked,
    permissions,
    role,
    forcePasswordChange,
    login,
    logout,
    checkSession,
    clearForcePasswordChange,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}
