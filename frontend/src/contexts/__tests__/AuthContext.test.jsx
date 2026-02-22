import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { AuthProvider, useAuth } from '../AuthContext'
import { authService } from '../../services/auth.service'

// Mock authService
vi.mock('../../services/auth.service', () => ({
  authService: {
    getCurrentUser: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
  }
}))

// Test component that uses the hook
function TestComponent({ onRender }) {
  const auth = useAuth()
  if (onRender) onRender(auth)
  return (
    <div>
      <span data-testid="authenticated">{auth.isAuthenticated.toString()}</span>
      <span data-testid="loading">{auth.loading.toString()}</span>
      <span data-testid="user">{auth.user?.username || 'none'}</span>
      <button onClick={() => auth.login('admin', 'password')}>Login</button>
      <button onClick={() => auth.logout()}>Logout</button>
    </div>
  )
}

describe('AuthContext', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Default: no session
    authService.getCurrentUser.mockRejectedValue(new Error('No session'))
    // Mock window.location
    Object.defineProperty(window, 'location', {
      value: { pathname: '/dashboard' },
      writable: true
    })
  })

  describe('AuthProvider', () => {
    it('provides auth context to children', async () => {
      render(
        <AuthProvider>
          <TestComponent />
        </AuthProvider>
      )

      await waitFor(() => {
        expect(screen.getByTestId('loading').textContent).toBe('false')
      })
      
      expect(screen.getByTestId('authenticated').textContent).toBe('false')
    })

    it('checks session on mount', async () => {
      authService.getCurrentUser.mockResolvedValue({
        data: { authenticated: true, user: { username: 'admin' }, permissions: ['read'], role: 'admin' }
      })

      render(
        <AuthProvider>
          <TestComponent />
        </AuthProvider>
      )

      await waitFor(() => {
        expect(screen.getByTestId('authenticated').textContent).toBe('true')
      })
      
      expect(screen.getByTestId('user').textContent).toBe('admin')
      expect(authService.getCurrentUser).toHaveBeenCalled()
    })

    it('always checks session even on login page', async () => {
      window.location.pathname = '/login'
      authService.getCurrentUser.mockRejectedValue(new Error('No session'))

      render(
        <AuthProvider>
          <TestComponent />
        </AuthProvider>
      )

      await waitFor(() => {
        expect(screen.getByTestId('loading').textContent).toBe('false')
      })
      
      // Session check is always called now (mTLS auto-login support)
      expect(authService.getCurrentUser).toHaveBeenCalled()
      expect(screen.getByTestId('authenticated').textContent).toBe('false')
    })

    it('handles session check failure gracefully', async () => {
      authService.getCurrentUser.mockRejectedValue(new Error('Unauthorized'))

      render(
        <AuthProvider>
          <TestComponent />
        </AuthProvider>
      )

      await waitFor(() => {
        expect(screen.getByTestId('loading').textContent).toBe('false')
      })
      
      expect(screen.getByTestId('authenticated').textContent).toBe('false')
      expect(screen.getByTestId('user').textContent).toBe('none')
    })
  })

  describe('login', () => {
    it('authenticates user with password', async () => {
      authService.getCurrentUser.mockRejectedValue(new Error('No session'))
      authService.login.mockResolvedValue({
        data: { user: { username: 'admin' }, permissions: ['read', 'write'], role: 'admin' }
      })

      let authContext
      render(
        <AuthProvider>
          <TestComponent onRender={(auth) => { authContext = auth }} />
        </AuthProvider>
      )

      await waitFor(() => {
        expect(screen.getByTestId('loading').textContent).toBe('false')
      })

      await act(async () => {
        await authContext.login('admin', 'password123')
      })

      expect(authService.login).toHaveBeenCalledWith('admin', 'password123')
      expect(screen.getByTestId('authenticated').textContent).toBe('true')
      expect(screen.getByTestId('user').textContent).toBe('admin')
    })

    it('handles login with preAuthData (mTLS/WebAuthn)', async () => {
      authService.getCurrentUser.mockRejectedValue(new Error('No session'))

      let authContext
      render(
        <AuthProvider>
          <TestComponent onRender={(auth) => { authContext = auth }} />
        </AuthProvider>
      )

      await waitFor(() => {
        expect(screen.getByTestId('loading').textContent).toBe('false')
      })

      const preAuthData = { user: { username: 'mtls-user' }, permissions: ['all'], role: 'admin' }
      
      await act(async () => {
        await authContext.login('mtls-user', null, preAuthData)
      })

      expect(authService.login).not.toHaveBeenCalled()
      expect(screen.getByTestId('authenticated').textContent).toBe('true')
      expect(screen.getByTestId('user').textContent).toBe('mtls-user')
    })

    it('throws error on login failure', async () => {
      authService.getCurrentUser.mockRejectedValue(new Error('No session'))
      authService.login.mockRejectedValue(new Error('Invalid credentials'))

      let authContext
      render(
        <AuthProvider>
          <TestComponent onRender={(auth) => { authContext = auth }} />
        </AuthProvider>
      )

      await waitFor(() => {
        expect(screen.getByTestId('loading').textContent).toBe('false')
      })

      await expect(act(async () => {
        await authContext.login('admin', 'wrong')
      })).rejects.toThrow('Invalid credentials')

      expect(screen.getByTestId('authenticated').textContent).toBe('false')
    })
  })

  describe('logout', () => {
    it('clears session on logout', async () => {
      authService.getCurrentUser.mockResolvedValue({
        data: { authenticated: true, user: { username: 'admin' }, permissions: [], role: 'admin' }
      })
      authService.logout.mockResolvedValue({})

      let authContext
      render(
        <AuthProvider>
          <TestComponent onRender={(auth) => { authContext = auth }} />
        </AuthProvider>
      )

      await waitFor(() => {
        expect(screen.getByTestId('authenticated').textContent).toBe('true')
      })

      await act(async () => {
        await authContext.logout()
      })

      expect(authService.logout).toHaveBeenCalled()
      expect(screen.getByTestId('authenticated').textContent).toBe('false')
      expect(screen.getByTestId('user').textContent).toBe('none')
    })

    it('clears local state even if API logout fails', async () => {
      authService.getCurrentUser.mockResolvedValue({
        data: { authenticated: true, user: { username: 'admin' }, permissions: [], role: 'admin' }
      })
      authService.logout.mockRejectedValue(new Error('Network error'))

      let authContext
      render(
        <AuthProvider>
          <TestComponent onRender={(auth) => { authContext = auth }} />
        </AuthProvider>
      )

      await waitFor(() => {
        expect(screen.getByTestId('authenticated').textContent).toBe('true')
      })

      await act(async () => {
        await authContext.logout()
      })

      // Still clears local state
      expect(screen.getByTestId('authenticated').textContent).toBe('false')
    })
  })

  describe('useAuth hook', () => {
    it('throws error when used outside AuthProvider', () => {
      const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
      
      expect(() => {
        render(<TestComponent />)
      }).toThrow('useAuth must be used within AuthProvider')
      
      consoleError.mockRestore()
    })
  })
})
