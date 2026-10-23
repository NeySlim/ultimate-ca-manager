/**
 * While a forced password change or 2FA enrolment is pending, no page mounts
 * behind the prompt (the server refuses their requests), and a login URL is
 * left so a logout from the prompt does not land back on it.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'

const auth = vi.hoisted(() => ({ value: {} }))

vi.mock('../../contexts', () => ({
  useAuth: () => auth.value,
  AuthProvider: ({ children }) => children,
  ThemeProvider: ({ children }) => children,
  NotificationProvider: ({ children }) => children,
  MobileProvider: ({ children }) => children,
  WindowManagerProvider: ({ children }) => children,
}))
vi.mock('../../hooks/useWebSocket', () => ({ WebSocketProvider: ({ children }) => children }))
vi.mock('../../components', async () => {
  const { Outlet } = await vi.importActual('react-router-dom')
  return {
    AppShell: () => <div>app-shell<Outlet /></div>,
    ErrorBoundary: ({ children }) => children,
    LoadingSpinner: () => null,
    SessionWarning: () => null,
    ForcePasswordChange: () => <div>password-prompt</div>,
    ForceEnroll2FA: () => <div>enrol-prompt</div>,
    SafeModeOverlay: () => null,
    DetailWindowLayer: () => null,
  }
})
vi.mock('../../pages/LoginPage', () => ({ default: () => <div>login-page</div> }))
vi.mock('../../pages/DashboardPage', () => ({ default: () => <div>dashboard-page</div> }))

import { AppRoutes } from '../../App'

function Where() {
  return <div data-testid="where">{useLocation().pathname}</div>
}

function renderAt(path, state) {
  auth.value = { isAuthenticated: true, loading: false, sessionChecked: true, permissions: ['*'], ...state }
  return render(<MemoryRouter initialEntries={[path]}><AppRoutes /><Where /></MemoryRouter>)
}

describe('AppRoutes under the forced gates', () => {
  it.each([
    [{ forcePasswordChange: true }, 'password-prompt'],
    [{ mustEnroll2fa: true }, 'enrol-prompt'],
  ])('mounts no page under %o', async (gate, prompt) => {
    renderAt('/dashboard', gate)
    expect(await screen.findByText(prompt)).toBeTruthy()
    expect(screen.queryByText('app-shell')).toBeNull()
  })

  it('leaves a login URL while the prompt is up', async () => {
    renderAt('/login/sso-complete', { forcePasswordChange: true })
    expect((await screen.findByTestId('where')).textContent).toBe('/')
    expect(screen.queryByText('login-page')).toBeNull()
  })

  it('mounts the pages once nothing is pending', async () => {
    renderAt('/dashboard', {})
    expect(await screen.findByText('dashboard-page')).toBeTruthy()
  })
})
