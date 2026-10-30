/**
 * A user certificate with a post-quantum key: its export dialog greys out
 * PKCS#12 and JKS, and the mobile panel offers no PKCS#12 shortcut.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const serviceMocks = vi.hoisted(() => ({
  getAll: vi.fn(), getStats: vi.fn(), getById: vi.fn(), export: vi.fn(), revoke: vi.fn(), delete: vi.fn(),
}))
const layout = vi.hoisted(() => ({ isMobile: false }))

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
  useNotification: () => ({
    showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(),
    showConfirm: vi.fn().mockResolvedValue(true), showPrompt: vi.fn(),
  }),
  useMobile: () => ({ isMobile: layout.isMobile, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
}))
vi.mock('../../contexts/WindowManagerContext', () => ({
  useWindowManager: () => ({ openWindow: vi.fn(), closeWindow: vi.fn(), windows: [] }),
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
const formatButton = (label) => screen.getByText(label).closest('button')

function serve(keyAlgorithm) {
  serviceMocks.getAll.mockResolvedValue({ data: { items: [row(keyAlgorithm)], total: 1 } })
  serviceMocks.getStats.mockResolvedValue({ data: {} })
  serviceMocks.getById.mockResolvedValue({ data: row(keyAlgorithm) })
}

describe('user certificate with a post-quantum key', () => {
  beforeEach(() => { layout.isMobile = false })

  it('greys out PKCS#12 and JKS in the export dialog', async () => {
    serve('ML-DSA-65')
    render(<UserCertificatesPage />)
    fireEvent.click(await screen.findByTitle('common.export'))
    await screen.findByText('PEM')
    expect(formatButton('P12 / PKCS#12')).toBeDisabled()
    expect(formatButton('JKS')).toBeDisabled()
    expect(formatButton('PEM')).toBeEnabled()
  })

  it.each([
    ['ML-DSA-65', false],
    ['RSA', true],
  ])('mobile panel for a %s key offers the PKCS#12 shortcut: %s', async (keyAlgorithm, offered) => {
    layout.isMobile = true
    serve(keyAlgorithm)
    render(<UserCertificatesPage />)
    fireEvent.click((await screen.findAllByText('pq-user@example.test'))[0])
    await screen.findByText('userCertificates.actions.exportPEM')
    expect(!!screen.queryByText('userCertificates.actions.exportPKCS12')).toBe(offered)
  })
})
