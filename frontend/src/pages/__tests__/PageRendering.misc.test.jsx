/**
 * Page Rendering Tests — Utility & Governance pages
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import './pageRenderingSetup.jsx'

import CertificateToolsPage from '../CertificateToolsPage'
import AccountPage from '../AccountPage'
import PoliciesPage from '../PoliciesPage'
import ApprovalsPage from '../ApprovalsPage'
import ReportsPage from '../ReportsPage'

function TestWrapper({ children, route = '/' }) {
  return <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
}

describe('Page Rendering — Utility & Governance', () => {
  beforeEach(() => { vi.clearAllMocks() })

  describe('Utility pages', () => {
    it('CertificateToolsPage renders without crashing', () => {
      const { container } = render(<TestWrapper route="/tools"><CertificateToolsPage /></TestWrapper>)
      expect(container.firstChild).toBeTruthy()
    })

    it('AccountPage renders without crashing', () => {
      const { container } = render(<TestWrapper route="/account"><AccountPage /></TestWrapper>)
      expect(container.firstChild).toBeTruthy()
    })
  })

  describe('Governance pages', () => {
    it('PoliciesPage renders without crashing', () => {
      const { container } = render(<TestWrapper route="/policies"><PoliciesPage /></TestWrapper>)
      expect(container.firstChild).toBeTruthy()
    })

    it('ApprovalsPage renders without crashing', () => {
      const { container } = render(<TestWrapper route="/approvals"><ApprovalsPage /></TestWrapper>)
      expect(container.firstChild).toBeTruthy()
    })

    it('ReportsPage renders without crashing', () => {
      const { container } = render(<TestWrapper route="/reports"><ReportsPage /></TestWrapper>)
      expect(container.firstChild).toBeTruthy()
    })
  })
})
