/**
 * Auth Context - Global authentication state
 */
import { createContext, useContext, useState, useEffect } from 'react'
import { authService } from '../services/auth.service'

const AuthContext = createContext()

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [loading, setLoading] = useState(true)
  const [permissions, setPermissions] = useState([])
  const [role, setRole] = useState(null)

  // Check session on mount
  useEffect(() => {
    // Don't check session if already on login page (prevents redirect loop)
    if (window.location.pathname === '/login') {
      setLoading(false)
      return
    }
    
    checkSession()
  }, [])

  const checkSession = async () => {
    try {
      console.log('🔍 Checking session...')
      const userData = await authService.getCurrentUser()
      console.log('✅ Session valid:', userData)
      setUser(userData.user || userData)
      setIsAuthenticated(true)
      setPermissions(userData.permissions || [])
      setRole(userData.role || null)
    } catch (error) {
      console.log('❌ Session check failed:', error.message)
      setUser(null)
      setIsAuthenticated(false)
      setPermissions([])
      setRole(null)
    } finally {
      setLoading(false)
    }
  }

  const login = async (username, password, preAuthData = null) => {
    setLoading(true)
    try {
      console.log('🔐 Login called:', { username, hasPreAuthData: !!preAuthData })
      
      let response
      if (preAuthData) {
        // Already authenticated via multi-method (mTLS, WebAuthn, etc.)
        response = { data: preAuthData }
      } else {
        // Legacy password auth
        console.log('🔐 Attempting password login for:', username)
        response = await authService.login(username, password)
      }
      
      console.log('✅ Login response:', response)
      const userData = response.data?.user || response.user || { username }
      setUser(userData)
      setIsAuthenticated(true)
      setPermissions(response.data?.permissions || response.permissions || [])
      setRole(response.data?.role || response.role || null)
      console.log('✅ User authenticated:', userData)
      return response
    } catch (error) {
      console.error('❌ Login failed:', error.message)
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
      console.log('🔓 Logging out...')
      await authService.logout()
      console.log('✅ Logout successful')
    } catch (error) {
      console.error('❌ Logout error:', error)
    } finally {
      // Always clear local state regardless of API success
      setUser(null)
      setIsAuthenticated(false)
      setPermissions([])
      setRole(null)
      setLoading(false)
      console.log('🔓 Local session cleared')
    }
  }

  const value = {
    user,
    isAuthenticated,
    loading,
    permissions,
    role,
    login,
    logout,
    checkSession,
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
