/**
 * SSHCAsPage — the certificate count per SSH CA.
 *
 * The page read `certificate_count`; /api/v2/ssh/cas answers `cert_count`. Both the
 * column and the certificate total therefore sat on zero no matter how many
 * certificates a CA had signed.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import './pageRenderingSetup.jsx'
import { sshCasService } from '../../services'

import SSHCAsPage from '../SSHCAsPage'

const CAS = [
  {
    id: 1, descr: 'Users CA', name: 'Users CA', ca_type: 'user', key_type: 'ed25519',
    fingerprint: 'SHA256:aaa', cert_count: 7, created_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 2, descr: 'Hosts CA', name: 'Hosts CA', ca_type: 'host', key_type: 'ed25519',
    fingerprint: 'SHA256:bbb', cert_count: 5, created_at: '2026-01-02T00:00:00Z',
  },
]

const renderPage = () => render(<MemoryRouter><SSHCAsPage /></MemoryRouter>)

describe('SSHCAsPage — certificate counts', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
    sshCasService.getAll = vi.fn().mockResolvedValue({ data: CAS })
  })

  it('shows each CA count from the field the API actually sends', async () => {
    renderPage()
    await waitFor(() => expect(sshCasService.getAll).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByText('Users CA')).toBeInTheDocument())

    expect(screen.getByText('7')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
  })

  it('totals them beside the type chips', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText('Users CA')).toBeInTheDocument())

    expect(document.getElementById('ssh-cert-total')).toHaveTextContent('sshCas.certTotal 12')
  })
})
