/** The CA header keeps the cross-signed count (#400), the HSM badge and the pending/offline/revoked state. */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => {
  const t = (key, opts) => (opts && 'count' in opts ? `${key}:${opts.count}` : key)
  return {
    useTranslation: () => ({ t, i18n: { language: 'en' } }),
    Trans: ({ children }) => children,
    initReactI18next: { type: '3rdParty', init: vi.fn() },
  }
})
vi.mock('../../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showConfirm: vi.fn() }),
  useAuth: () => ({ user: { role: 'admin' }, isAuthenticated: true, permissions: ['*'] }),
}))
vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => ({ user: { role: 'admin' }, isAuthenticated: true, permissions: ['*'] }),
}))
vi.mock('../../cas/CACrlSection', () => ({ CACrlSection: () => null }))
vi.mock('../../cas/CrossCertificatesSection', () => ({ CrossCertificatesSection: () => null }))

const { CAPanel } = await import('../CAPanel')

const base = { id: 1, descr: 'CA', status: 'Active', is_root: false, has_private_key: true, valid_from: '2020-01-01T00:00:00Z' }
const show = (extra, props) => render(<CAPanel ca={{ ...base, ...extra }} {...props} />)

describe('CAPanel header', () => {
  it('shows the cross-signed count only when there are some', () => {
    show({ cross_certificate_count: 2 })
    expect(screen.getByTestId('cross-badge')).toHaveTextContent('crossCerts.badge:2')
  })

  it('shows no cross badge without cross certificates', () => {
    show({ cross_certificate_count: 0 })
    expect(screen.queryByTestId('cross-badge')).toBeNull()
  })

  it('flags an HSM-backed CA with provider and key label in the tooltip', () => {
    show({ uses_hsm: true, hsm_provider_name: 'Vault', hsm_key_label: 'ca-key' })
    expect(screen.getByText('cas.detail.hsmBacked')).toHaveAttribute('title', 'Vault / ca-key')
  })

  it.each([
    [{ pending: true }, 'cas.awaitingCertificate'],
    [{ offline: true }, 'cas.offline'],
    [{ revoked: true }, 'common.revoked'],
  ])('states %j in the header', (extra, label) => {
    show(extra)
    expect(screen.getAllByText(label).length).toBeGreaterThan(0)
    expect(screen.queryByText('common.active')).toBeNull()
  })
})
