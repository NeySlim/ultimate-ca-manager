/**
 * Page Rendering Tests — PKI pages
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import './pageRenderingSetup.jsx'

import CertificatesPage from '../CertificatesPage'
import CAsPage from '../CAsPage'
import CSRsPage from '../CSRsPage'
import TemplatesPage from '../TemplatesPage'
import TrustStorePage from '../TrustStorePage'

function TestWrapper({ children, route = '/' }) {
  return <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
}

describe('Page Rendering — PKI pages', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('CertificatesPage renders without crashing', () => {
    const { container } = render(<TestWrapper route="/certificates"><CertificatesPage /></TestWrapper>)
    expect(container.firstChild).toBeTruthy()
  })

  it('CAsPage renders without crashing', () => {
    const { container } = render(<TestWrapper route="/cas"><CAsPage /></TestWrapper>)
    expect(container.firstChild).toBeTruthy()
  })

  it('CSRsPage renders without crashing', () => {
    const { container } = render(<TestWrapper route="/csrs"><CSRsPage /></TestWrapper>)
    expect(container.firstChild).toBeTruthy()
  })

  it('TemplatesPage renders without crashing', () => {
    const { container } = render(<TestWrapper route="/templates"><TemplatesPage /></TestWrapper>)
    expect(container.firstChild).toBeTruthy()
  })

  it('TrustStorePage renders without crashing', () => {
    const { container } = render(<TestWrapper route="/truststore"><TrustStorePage /></TestWrapper>)
    expect(container.firstChild).toBeTruthy()
  })
})
