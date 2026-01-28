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

  // Check session on mount
  useEffect(() => {
    checkSession()
  }, [])

  const checkSession = async () => {
    try {
      console.log('🔍 Checking session...')
      const userData = await authService.getCurrentUser()
      console.log('✅ Session valid:', userData)
      setUser(userData.user || userData)
      setIsAuthenticated(true)
    } catch (error) {
      console.log('❌ Session check failed:', error.message)
      setUser(null)
      setIsAuthenticated(false)
    } finally {
      setLoading(false)
    }
  }

  const login = async (username, password) => {
    setLoading(true)
    try {
      console.log('🔐 Attempting login for:', username)
      const response = await authService.login(username, password)
      console.log('✅ Login response:', response)
      const userData = response.data?.user || response.user || { username }
      setUser(userData)
      setIsAuthenticated(true)
      console.log('✅ User authenticated:', userData)
      return response
    } catch (error) {
      console.error('❌ Login failed:', error.message)
      setUser(null)
      setIsAuthenticated(false)
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
      setLoading(false)
      console.log('🔓 Local session cleared')
    }
  }

  const value = {
    user,
    isAuthenticated,
    loading,
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
