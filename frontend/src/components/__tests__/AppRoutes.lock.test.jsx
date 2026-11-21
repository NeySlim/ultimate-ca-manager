/**
 * Once the session is locked (signed-out state), nothing of the console stays
 * mounted, and the sign-in page carries the page that was open.
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
  InspectorProvider: ({ children }) => children,
}))
vi.mock('../../hooks/useWebSocket', () => ({ WebSocketProvider: ({ children }) => children }))
vi.mock('../../components', async () => {
  const { Outlet } = await vi.importActual('react-router-dom')
  return {
    AppShell: () => <div>app-shell<input aria-label="shell-search" /><Outlet /></div>,
    ErrorBoundary: ({ children }) => children,
    LoadingSpinner: () => null,
    SessionWarning: () => null,
    ForcePasswordChange: () => null,
    ForceEnroll2FA: () => null,
    SafeModeOverlay: () => null,
  }
})
vi.mock('../../pages/LoginPage', () => ({ default: () => <div>login-page</div> }))
vi.mock('../../pages/CertificatesPage', () => ({ default: () => <button type="button">cert-secret-row</button> }))

import { AppRoutes } from '../../App'

function Where() {
  const l = useLocation()
  return <div data-testid="where">{l.pathname + l.search}</div>
}

describe('AppRoutes when the session locks', () => {
  it('unmounts the console and keeps the open page for the return', async () => {
    auth.value = { isAuthenticated: true, loading: false, sessionChecked: true, permissions: ['*'] }
    const view = render(<MemoryRouter initialEntries={['/certificates?status=expiring']}><AppRoutes /><Where /></MemoryRouter>)
    expect(await screen.findByText('cert-secret-row')).toBeInTheDocument()

    auth.value = { isAuthenticated: false, loading: false, sessionChecked: true, permissions: [] }
    view.rerender(<MemoryRouter initialEntries={['/certificates?status=expiring']}><AppRoutes /><Where /></MemoryRouter>)

    expect(await screen.findByText('login-page')).toBeInTheDocument()
    expect(screen.queryByText('cert-secret-row')).toBeNull()
    expect(screen.queryByText('app-shell')).toBeNull()
    expect(screen.queryByLabelText('shell-search')).toBeNull()
    expect(screen.getByTestId('where').textContent).toBe('/login?next=%2Fcertificates%3Fstatus%3Dexpiring')
  })
})
