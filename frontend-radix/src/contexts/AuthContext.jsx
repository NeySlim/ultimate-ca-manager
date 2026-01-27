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
      const userData = await authService.getCurrentUser()
      setUser(userData)
      setIsAuthenticated(true)
    } catch (error) {
      setUser(null)
      setIsAuthenticated(false)
    } finally {
      setLoading(false)
    }
  }

  const login = async (username, password) => {
    setLoading(true)
    try {
      const response = await authService.login(username, password)
      setUser(response.user || { username })
      setIsAuthenticated(true)
      return response
    } catch (error) {
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
      await authService.logout()
    } catch (error) {
      console.error('Logout error:', error)
    } finally {
      setUser(null)
      setIsAuthenticated(false)
      setLoading(false)
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
