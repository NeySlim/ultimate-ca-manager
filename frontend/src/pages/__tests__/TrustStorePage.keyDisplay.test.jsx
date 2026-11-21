/**
 * TrustStorePage detail: a post-quantum key is named with its level, a classical
 * one with its size, and a key the API could not read is never shown as RSA.
 * Records carry the key fields TrustedCertificate.to_dict sends.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import en from '../../i18n/locales/en.json'

const i18n = vi.hoisted(() => ({ en: null }))
vi.mock('react-i18next', () => {
  const lookup = (key) => key.split('.').reduce((node, part) => (node == null ? node : node[part]), i18n.en)
  const t = (key, opts) => {
    const vars = typeof opts === 'object' && opts ? opts : {}
    const template = lookup(key)
    if (typeof template !== 'string') return key
    return template.replace(/\{\{(\w+)\}\}/g, (_m, name) => (vars[name] ?? `{{${name}}}`))
  }
  return {
    useTranslation: () => ({ t, i18n: { language: 'en' } }),
    Trans: ({ children }) => children,
    initReactI18next: { type: '3rdParty', init: () => {} },
  }
})
i18n.en = en

vi.mock('../../contexts', () => ({
  useNotification: () => ({
    showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(),
    showConfirm: vi.fn().mockResolvedValue(false),
  }),
  useMobile: () => ({ isMobile: true }),
  useInspector: () => ({ openEntity: vi.fn(), closeWindow: vi.fn(), windows: [] }),
}))
vi.mock('../../contexts/InspectorContext', () => ({
  useInspector: () => ({ openEntity: vi.fn(), closeWindow: vi.fn(), windows: [] }),
}))
vi.mock('../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: true }) }))
vi.mock('../../hooks', async () => {
  const modals = await vi.importActual('../../hooks/useCommon')
  const persisted = await vi.importActual('../../hooks/usePersistedState')
  return {
    useModals: modals.useModals,
    usePersistedState: persisted.usePersistedState,
    usePermission: () => ({
      canWrite: () => false, canDelete: () => false, hasPermission: () => true, canRead: () => true,
    }),
  }
})

const store = vi.hoisted(() => ({ cert: null }))
vi.mock('../../services', () => ({
  truststoreService: {
    getAll: () => Promise.resolve({ data: [store.cert] }),
    getById: () => Promise.resolve({ data: store.cert }),
    getStats: vi.fn().mockResolvedValue({ data: { total: 1, root_ca: 1, intermediate_ca: 0, expired: 0, valid: 1 } }),
  },
  casService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
}))
vi.mock('../../components/SmartImport', () => ({ SmartImportModal: () => null }))

import TrustStorePage from '../TrustStorePage'

const openDetail = async (cert) => {
  store.cert = { id: 3, name: 'Trusted root', subject: 'CN=Trusted root', not_after: '2035-01-01T00:00:00Z', ...cert }
  render(<MemoryRouter><TrustStorePage /></MemoryRouter>)
  fireEvent.click(await screen.findByRole('button', { name: 'Trusted root' }))
  // The key is in the dock's Détails tab
  fireEvent.click(await screen.findByRole('tab', { name: en.trustStore.module.sections.details }))
  await screen.findAllByText(en.common.keyType)
}

const MLDSA = {
  key_type: 'ML-DSA-65', key_algorithm: 'ML-DSA-65', key_size: null, security_level: 3,
  post_quantum: true, signature_algorithm: 'ML-DSA-65',
}
const RSA = {
  key_type: 'RSA 2048', key_algorithm: 'RSA', key_size: 2048, security_level: null,
  post_quantum: false, signature_algorithm: 'SHA256-RSA',
}
const UNREADABLE = {
  key_type: 'N/A', key_algorithm: 'Unknown', key_size: 0, security_level: null,
  post_quantum: false, signature_algorithm: 'N/A',
}

describe('TrustStorePage key display', () => {
  it('names an ML-DSA key as the Certificates zone does, without a level', async () => {
    await openDetail(MLDSA)
    // The key and the issuer's signature algorithm
    expect(screen.getAllByText('ML-DSA-65')).toHaveLength(2)
    expect(screen.queryByText(/level/)).toBeNull()
  })

  it('names an RSA key with its size and its signature algorithm', async () => {
    await openDetail(RSA)
    expect(screen.getAllByText('RSA 2048')).toHaveLength(1)
    expect(screen.getAllByText('SHA256-RSA').length).toBeGreaterThan(0)
  })

  it('never shows a key the API could not read as RSA', async () => {
    await openDetail(UNREADABLE)
    expect(screen.queryByText(/\bRSA\b/)).toBeNull()
  })
})
