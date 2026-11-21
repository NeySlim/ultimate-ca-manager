/**
 * A user certificate with a post-quantum key: the export dialog of its dock greys out
 * PKCS#12 and JKS, on a computer as on a phone; an RSA key keeps them.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

const serviceMocks = vi.hoisted(() => ({
  getAll: vi.fn(), getStats: vi.fn(), getById: vi.fn(), export: vi.fn(), revoke: vi.fn(), delete: vi.fn(),
}))
const layout = vi.hoisted(() => ({ isMobile: false }))
// Stable across renders: t and showError are loader dependencies, a fresh one reloads in a loop
const stable = vi.hoisted(() => ({
  notify: {
    showSuccess: () => {}, showError: () => {}, showWarning: () => {},
    showConfirm: () => Promise.resolve(true), showPrompt: () => {},
  },
}))

vi.mock('react-i18next', () => {
  const translation = {
    t: (key, fallback) => (typeof fallback === 'string' ? fallback : key),
    i18n: { language: 'en', changeLanguage: () => {}, on: () => {}, off: () => {} },
  }
  return {
    useTranslation: () => translation,
    Trans: ({ children }) => children,
    initReactI18next: { type: '3rdParty', init: () => {} },
  }
})
vi.mock('../../contexts', () => ({
  useNotification: () => stable.notify,
  useMobile: () => ({ isMobile: layout.isMobile, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
}))
vi.mock('../../contexts/MobileContext', () => ({
  useMobile: () => ({ isMobile: layout.isMobile, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
}))
vi.mock('../../contexts/InspectorContext', () => ({
  useInspector: () => ({ openEntity: vi.fn(), closeWindow: vi.fn(), windows: [] }),
}))
vi.mock('../../hooks', async () => {
  const actual = await vi.importActual('../../hooks/usePersistedState')
  return {
    usePersistedState: actual.usePersistedState,
    usePermission: () => ({
      canWrite: () => true, canDelete: () => true, canRead: () => true, hasPermission: () => true,
    }),
  }
})
vi.mock('../../services', () => ({ userCertificatesService: serviceMocks }))

import UserCertificatesPage from '../UserCertificatesPage'

const row = (keyAlgorithm) => ({
  id: 21, name: 'pq-user@example.test', cert_subject: 'CN=pq-user@example.test', status: 'valid',
  has_private_key: true, key_algorithm: keyAlgorithm, valid_to: '2030-01-01T00:00:00Z',
})
const formatButton = (label) => screen.getByText(label).closest('label').querySelector('input')

function serve(keyAlgorithm) {
  serviceMocks.getAll.mockResolvedValue({ data: { items: [row(keyAlgorithm)], total: 1 } })
  serviceMocks.getStats.mockResolvedValue({ data: {} })
  serviceMocks.getById.mockResolvedValue({ data: row(keyAlgorithm) })
}

const openExport = async () => {
  render(<MemoryRouter><UserCertificatesPage /></MemoryRouter>)
  fireEvent.click((await screen.findAllByRole('button', { name: 'pq-user@example.test' }))[0])
  fireEvent.click(await screen.findByRole('button', { name: 'common.export' }))
  await screen.findByText('PEM')
}

describe('user certificate with a post-quantum key', () => {
  beforeEach(() => { layout.isMobile = false })

  it('greys out PKCS#12 and JKS in the export dialog', async () => {
    serve('ML-DSA-65')
    await openExport()
    expect(formatButton('PKCS#12')).toBeDisabled()
    expect(formatButton('JKS')).toBeDisabled()
    expect(formatButton('PEM')).toBeEnabled()
  })

  it.each([
    ['ML-DSA-65', false],
    ['RSA', true],
  ])('on a phone, a %s key offers PKCS#12: %s', async (keyAlgorithm, offered) => {
    layout.isMobile = true
    serve(keyAlgorithm)
    await openExport()
    expect(formatButton('PKCS#12').disabled).toBe(!offered)
  })
})
