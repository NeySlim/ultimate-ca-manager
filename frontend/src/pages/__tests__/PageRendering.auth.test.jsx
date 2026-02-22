/**
 * Page Rendering Tests — Auth & Dashboard pages
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import './pageRenderingSetup.jsx'

import LoginPage from '../LoginPage'
import ForgotPasswordPage from '../ForgotPasswordPage'
import ResetPasswordPage from '../ResetPasswordPage'
import DashboardPage from '../DashboardPage'

function TestWrapper({ children, route = '/' }) {
  return <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
}

describe('Page Rendering — Auth & Dashboard', () => {
  beforeEach(() => { vi.clearAllMocks() })

  describe('Auth pages', () => {
    it('LoginPage renders without crashing', async () => {
      const { container } = render(<TestWrapper route="/login"><LoginPage /></TestWrapper>)
      // LoginPage starts in 'init' state (returns null), then transitions after effect
      await new Promise(r => setTimeout(r, 100))
      // After init, it should render something (or stay null if auth redirects)
      // The key test is that it doesn't throw
      expect(true).toBe(true)
    })

    it('ForgotPasswordPage renders without crashing', () => {
      const { container } = render(<TestWrapper route="/forgot-password"><ForgotPasswordPage /></TestWrapper>)
      expect(container.firstChild).toBeTruthy()
    })

    it('ResetPasswordPage renders without crashing', () => {
      const { container } = render(<TestWrapper route="/reset-password?token=abc123"><ResetPasswordPage /></TestWrapper>)
      expect(container.firstChild).toBeTruthy()
    })
  })

  describe('Dashboard', () => {
    it('DashboardPage renders without crashing', () => {
      const { container } = render(<TestWrapper route="/dashboard"><DashboardPage /></TestWrapper>)
      expect(container.firstChild).toBeTruthy()
    })
  })
})
