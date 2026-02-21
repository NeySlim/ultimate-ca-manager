/**
 * Page Rendering Tests — Protocol pages (ACME, SCEP, CRL/OCSP)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import './pageRenderingSetup.jsx'

import ACMEPage from '../ACMEPage'
import SCEPPage from '../SCEPPage'
import CRLOCSPPage from '../CRLOCSPPage'

function TestWrapper({ children, route = '/' }) {
  return <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
}

describe('Page Rendering — Protocol pages', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('ACMEPage renders without crashing', () => {
    const { container } = render(<TestWrapper route="/acme"><ACMEPage /></TestWrapper>)
    expect(container.firstChild).toBeTruthy()
  })

  it('SCEPPage renders without crashing', () => {
    const { container } = render(<TestWrapper route="/scep"><SCEPPage /></TestWrapper>)
    expect(container.firstChild).toBeTruthy()
  })

  it('CRLOCSPPage renders without crashing', () => {
    const { container } = render(<TestWrapper route="/crl-ocsp"><CRLOCSPPage /></TestWrapper>)
    expect(container.firstChild).toBeTruthy()
  })
})
