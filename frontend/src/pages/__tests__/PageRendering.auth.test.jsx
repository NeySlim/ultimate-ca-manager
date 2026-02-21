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
    it('LoginPage renders without crashing', () => {
      const { container } = render(<TestWrapper route="/login"><LoginPage /></TestWrapper>)
      expect(container.firstChild).toBeTruthy()
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
