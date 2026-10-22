/** The lint modal offers the ETSI profile and passes it to the server. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import '../../pages/__tests__/pageRenderingSetup.jsx'

const lint = vi.fn()
vi.mock('../../services', async (orig) => {
  const mod = await orig()
  return { ...mod, certificatesService: { ...mod.certificatesService, lint: (...a) => lint(...a) } }
})

import { CertificateLintModal } from '../CertificateLintModal'

describe('CertificateLintModal, etsi profile', () => {
  beforeEach(() => lint.mockReset().mockResolvedValue({ data: { findings: [], summary: {}, linters: ['pkilint'] } }))

  it('runs the etsi profile when selected', async () => {
    render(<CertificateLintModal certId={7} certName="c" open onClose={() => {}} />)
    await waitFor(() => expect(lint).toHaveBeenCalledWith(7, 'rfc5280'))
    fireEvent.click(await screen.findByText('lint.profile_etsi'))
    await waitFor(() => expect(lint).toHaveBeenCalledWith(7, 'etsi'))
  })
})
