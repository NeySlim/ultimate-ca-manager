/**
 * Page Rendering Tests — Protocol pages (ACME, SCEP, CRL/OCSP)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import './pageRenderingSetup.jsx'

import ACMEPage from '../ACMEPage'
import SCEPPage from '../SCEPPage'
import CRLOCSPPage from '../CRLOCSPPage'
import { scepService } from '../../services/scep.service'

function TestWrapper({ children, route = '/' }) {
  return <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
}

describe('Page Rendering — Protocol pages', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('ACMEPage renders without crashing', () => {
    const { container } = render(<TestWrapper route="/acme"><ACMEPage /></TestWrapper>)
    expect(container.firstChild).toBeTruthy()
  })

  it('ACMEPage exposes a dedicated Let’s Encrypt orders view', async () => {
    render(<TestWrapper route="/acme"><ACMEPage /></TestWrapper>)
    expect(await screen.findByRole('tab', { name: /^acme\.views\.letsencryptorders/ })).toBeInTheDocument()
  })

  it('SCEPPage offers no CA identifier, which no SCEP exchange used', async () => {
    Object.assign(scepService, {
      getRequests: vi.fn().mockResolvedValue({ data: [] }), getStats: vi.fn().mockResolvedValue({ data: {} }),
      getProfiles: vi.fn().mockResolvedValue({ data: [] }),
    })
    render(<TestWrapper route="/scep-config?tab=config"><SCEPPage /></TestWrapper>)
    await screen.findByText('scep.supportedOperations', { selector: 'legend' })
    expect(screen.queryByText('scep.caIdentifier')).toBeNull()
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
