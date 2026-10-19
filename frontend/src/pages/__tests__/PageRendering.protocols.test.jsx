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

function TestWrapper({ children, route = '/' }) {
  return <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
}

describe('Page Rendering — Protocol pages', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('ACMEPage renders without crashing', () => {
    const { container } = render(<TestWrapper route="/acme"><ACMEPage /></TestWrapper>)
    expect(container.firstChild).toBeTruthy()
  })

  it('ACMEPage exposes a dedicated Let’s Encrypt orders tab', async () => {
    render(<TestWrapper route="/acme"><ACMEPage /></TestWrapper>)
    expect(await screen.findByText('acme.letsEncryptOrders')).toBeInTheDocument()
  })

  it('SCEPPage offers no CA identifier, which no SCEP exchange used', async () => {
    render(<TestWrapper route="/scep"><SCEPPage /></TestWrapper>)
    for (const tab of ['common.config', 'scep.info']) {
      fireEvent.click((await screen.findAllByText(tab))[0])
      expect(screen.queryByText('scep.caIdentifier')).toBeNull()
    }
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
