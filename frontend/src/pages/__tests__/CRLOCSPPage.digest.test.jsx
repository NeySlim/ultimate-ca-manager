/**
 * The CRL digest select is offered only to a CA whose key takes a digest:
 * the API reports crl_digest null for ML-DSA and EdDSA CAs and refuses one.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, fallback) => (typeof fallback === 'string' ? fallback : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

const notify = {
  showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(),
  showConfirm: vi.fn(), showPrompt: vi.fn(),
}
vi.mock('../../contexts', () => ({
  useNotification: () => notify,
  useMobile: () => ({ isMobile: false, isTablet: false }),
}))

vi.mock('../../hooks', () => ({
  usePermission: () => ({ canWrite: () => true, canRead: () => true, canDelete: () => true, hasPermission: () => true }),
  useClipboard: () => ({ copy: vi.fn() }),
}))

vi.mock('../../components/CRLDeploySection', () => ({ CRLDeploySection: () => null }))

const CAS = vi.hoisted(() => [
  { id: 1, name: 'RSA Root', descr: 'RSA Root', common_name: 'RSA Root', has_private_key: true, crl_digest: 'sha256' },
  { id: 2, name: 'PQ Root', descr: 'PQ Root', common_name: 'PQ Root', has_private_key: true, crl_digest: null },
])

vi.mock('../../services', () => ({
  casService: { getAll: vi.fn().mockResolvedValue({ data: CAS }) },
  crlService: {
    getAll: vi.fn().mockResolvedValue({ data: [] }),
    getOcspStatus: vi.fn().mockResolvedValue({ data: { enabled: false, running: false } }),
    getOcspStats: vi.fn().mockResolvedValue({ data: { total_requests: 0, cache_hits: 0 } }),
    getForCA: vi.fn().mockResolvedValue({ data: null }),
    getOcspResponder: vi.fn().mockResolvedValue({ data: { responder: null } }),
    getEligibleResponders: vi.fn().mockResolvedValue({ data: [] }),
    configureCrl: vi.fn().mockResolvedValue({}),
  },
}))

import CRLOCSPPage from '../CRLOCSPPage'

async function selectCA(name) {
  render(<MemoryRouter><CRLOCSPPage /></MemoryRouter>)
  fireEvent.click((await screen.findAllByText(name))[0])
  await screen.findByLabelText('crlOcsp.crlValidity')
}

describe('CRL digest select', () => {
  it('is offered for a CA whose key takes a digest', async () => {
    await selectCA('RSA Root')
    expect(screen.getByLabelText('crlOcsp.crlDigest')).toHaveValue('sha256')
  })

  it('is absent for a CA that signs without a separate digest', async () => {
    await selectCA('PQ Root')
    await waitFor(() => expect(screen.queryByLabelText('crlOcsp.crlDigest')).toBeNull())
  })
})
