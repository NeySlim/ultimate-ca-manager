/**
 * DUP-FE-012. CADetails read `ca.days_remaining`, which the CA serializer never
 * emits: backend/models/ca.py to_dict() carries valid_from/valid_to and
 * crl_validity_days, but no days_remaining — only Certificate.to_dict() has one.
 *
 * The consequences were all silent:
 *   - `undefined !== null` is true, so the badge block rendered;
 *   - every `undefined <= N` comparison is false, so it rendered with no colour;
 *   - `undefined <= 0` is false too, so it took the "days remaining" branch and
 *     interpolated a count of undefined;
 *   - and the `<= 30` test in getStatus() could never be true, so a CA could
 *     never be shown as expiring at all.
 *
 * It now derives the value from `valid_to`, which the serializer does emit,
 * rounding the way the server rounds its own days_remaining (floor).
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => {
  const t = (key, opts) => (opts && 'count' in opts ? `${key}:${opts.count}` : key)
  return {
    useTranslation: () => ({ t, i18n: { language: 'en' } }),
    Trans: ({ children }) => children,
    initReactI18next: { type: '3rdParty', init: vi.fn() },
  }
})
vi.mock('../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showConfirm: vi.fn() }),
  useAuth: () => ({ user: { role: 'admin' }, isAuthenticated: true, permissions: ['*'] }),
}))
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ user: { role: 'admin' }, isAuthenticated: true, permissions: ['*'] }),
}))
vi.mock('../cas/CACrlSection', () => ({ CACrlSection: () => null }))

const { CADetails } = await import('../CADetails')

const NOW = new Date('2026-06-01T12:00:00Z')

afterEach(() => vi.useRealTimers())

function renderCA(extra) {
  vi.useFakeTimers()
  vi.setSystemTime(NOW)
  const ca = {
    id: 1,
    descr: 'Test CA',
    subject: 'CN=Test CA',
    status: 'Active',
    is_root: true,
    has_private_key: true,
    valid_from: '2020-01-01T00:00:00Z',
    ...extra,
  }
  const utils = render(<CADetails ca={ca} showActions={false} />)
  return utils
}

describe('CADetails — days remaining', () => {
  it('shows a real count for a CA that expires in 45 days', () => {
    renderCA({ valid_to: '2026-07-16T12:00:00Z' })
    expect(screen.getByText('details.daysRemaining:45')).toBeInTheDocument()
  })

  it('never interpolates an undefined count', () => {
    renderCA({ valid_to: '2026-07-16T12:00:00Z' })
    expect(screen.queryByText(/daysRemaining:undefined/)).toBeNull()
    expect(screen.queryByText(/NaN/)).toBeNull()
  })

  it('uses the expired wording, with a positive number, once past valid_to', () => {
    renderCA({ valid_to: '2026-05-20T12:00:00Z' })
    expect(screen.getByText('details.expiredDaysAgo:12')).toBeInTheDocument()
  })

  it('colours the band instead of leaving it unstyled', () => {
    renderCA({ valid_to: '2026-06-20T12:00:00Z' }) // 19 days → warning band
    const band = screen.getByText('details.daysRemaining:19').closest('div')
    expect(band.className).toMatch(/status-warning/)
  })

  it('renders nothing at all when valid_to is missing', () => {
    renderCA({ valid_to: null })
    expect(screen.queryByText(/details\.daysRemaining/)).toBeNull()
    expect(screen.queryByText(/details\.expiredDaysAgo/)).toBeNull()
  })

  it('marks a CA inside the 30-day window as expiring', () => {
    renderCA({ valid_to: '2026-06-20T12:00:00Z' })
    // statusConfig.expiring carries the common.detailsExpiring label; before the
    // fix getStatus() could never reach it, so the CA always read as active.
    expect(screen.getByText('common.detailsExpiring')).toBeInTheDocument()
    expect(screen.queryByText('common.active')).toBeNull()
  })
})
