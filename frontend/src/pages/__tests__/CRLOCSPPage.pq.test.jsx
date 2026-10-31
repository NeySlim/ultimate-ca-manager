/**
 * CRL digest select for a post-quantum CA: hidden when the registry says its
 * key takes no digest, even if the API still reports one (a CA pending on its CSR).
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { GROUP_PQ, KEY_ALGORITHMS } from '../../lib/keyAlgorithms'

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
  { id: 1, name: 'RSA Root', descr: 'RSA Root', common_name: 'RSA Root', has_private_key: true, key_type: 'RSA 2048', crl_digest: 'sha256' },
  { id: 2, name: 'PQ Pending', descr: 'PQ Pending', common_name: 'PQ Pending', has_private_key: true, key_type: 'ML-DSA-65', crl_digest: 'sha256' },
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

describe('CRL digest select for an ML-DSA CA', () => {
  it('has ML-DSA rows that take no digest', () => {
    const pq = KEY_ALGORITHMS.filter(a => a.group === GROUP_PQ)
    expect(pq.map(a => a.label)).toContain('ML-DSA-65')
    expect(pq.every(a => a.digest === null)).toBe(true)
  })

  it('is offered for an RSA CA', async () => {
    await selectCA('RSA Root')
    expect(screen.getByLabelText('crlOcsp.crlDigest')).toHaveValue('sha256')
  })

  it('is absent when the CA key is ML-DSA, whatever the API reports', async () => {
    await selectCA('PQ Pending')
    await waitFor(() => expect(screen.queryByLabelText('crlOcsp.crlDigest')).toBeNull())
  })
})
