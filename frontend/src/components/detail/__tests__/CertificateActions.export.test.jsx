/**
 * The export dialog opened from the shared action bar: it offers what the
 * entity's key and hybrid pairing allow.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import en from '../../../i18n/locales/en.json'

const lookup = (key) => key.split('.').reduce((node, part) => (node == null ? node : node[part]), en)
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, opts) => lookup(key) ?? (typeof opts === 'string' ? opts : key) }),
  initReactI18next: { type: '3rdParty', init: () => {} },
  Trans: ({ children }) => children,
}))
vi.mock('../../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showConfirm: vi.fn(), showPrompt: vi.fn() }),
  useMobile: () => ({ isMobile: false, isTablet: false }),
}))
vi.mock('../../../contexts/AuthContext', () => ({ useAuth: () => ({ permissions: ['*'] }) }))

import { ActionsHarness } from './ActionsHarness'

const ALLOW = { canWrite: () => true, canDelete: () => true, hasPermission: () => true }
const base = {
  id: 11, common_name: 'pair.example.com', subject: 'CN=pair.example.com', serial_number: '42',
  valid_to: '2030-01-01T00:00:00Z', has_private_key: true, status: 'valid',
  key_algorithm: 'EC-P256', key_type: 'EC-P256', signature_algorithm: 'ecdsa-with-SHA256',
}
const openExport = () => fireEvent.click(screen.getAllByRole('button', { name: /export/i })[0])

describe('export dialog of the action bar', () => {
  it('offers no PKCS#12 or JKS export for an ML-DSA key', () => {
    const mldsa = { ...base, key_algorithm: 'ML-DSA-65', key_type: 'ML-DSA-65', security_level: 3, post_quantum: true }
    render(<ActionsHarness entity={mldsa} permissions={ALLOW} />)
    openExport()
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText('P12 / PKCS#12').closest('button')).toBeDisabled()
    expect(within(dialog).getByText('JKS').closest('button')).toBeDisabled()
    expect(within(dialog).getByText('PEM').closest('button')).toBeEnabled()
  })

  it('offers the hybrid bundle for a pair member only', () => {
    const { unmount } = render(
      <ActionsHarness entity={{ ...base, related_certificate_id: 12, hybrid_role: 'classical' }} permissions={ALLOW} />)
    openExport()
    expect(screen.getByText(en.export.formats.hybridBundle)).toBeInTheDocument()
    unmount()

    render(<ActionsHarness entity={{ ...base, related_certificate_id: null }} permissions={ALLOW} />)
    openExport()
    expect(screen.queryByText(en.export.formats.hybridBundle)).toBeNull()
  })
})
