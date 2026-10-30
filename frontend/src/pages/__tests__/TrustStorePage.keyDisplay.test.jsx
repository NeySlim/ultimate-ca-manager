/**
 * TrustStorePage detail: a post-quantum key is named with its level, and a
 * certificate whose key type the API does not send is never shown as RSA.
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
  useWindowManager: () => ({ openWindow: vi.fn(), closeWindow: vi.fn(), windows: [] }),
}))
vi.mock('../../contexts/WindowManagerContext', () => ({
  useWindowManager: () => ({ openWindow: vi.fn(), closeWindow: vi.fn(), windows: [] }),
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
vi.mock('../../components/ui/responsive', () => ({
  ResponsiveLayout: ({ children, slideOverContent }) => <div>{children}<div>{slideOverContent}</div></div>,
  ResponsiveDataTable: ({ data, onRowClick }) => (
    <div>{data.map(row => <button key={row.id} onClick={() => onRowClick(row)}>open-{row.id}</button>)}</div>
  ),
}))
vi.mock('../../components/SmartImport', () => ({ SmartImportModal: () => null }))

import TrustStorePage from '../TrustStorePage'

const openDetail = async (cert) => {
  store.cert = { id: 3, name: 'Trusted root', subject: 'CN=Trusted root', not_after: '2035-01-01T00:00:00Z', ...cert }
  render(<MemoryRouter><TrustStorePage /></MemoryRouter>)
  fireEvent.click(await screen.findByText('open-3'))
  await screen.findAllByText(en.common.keyType)
}

describe('TrustStorePage key display', () => {
  it('names an ML-DSA key with its level', async () => {
    await openDetail({ key_type: 'ML-DSA-65', security_level: 3 })
    // Quick stats and key section
    expect(screen.getAllByText('ML-DSA-65 (level 3)')).toHaveLength(2)
    expect(screen.queryByText('ML-DSA-65')).toBeNull()
  })

  it('shows a key type the API does not send as a dash, never RSA', async () => {
    await openDetail({ key_type: undefined })
    expect(screen.queryByText(/\bRSA\b/)).toBeNull()
  })
})
