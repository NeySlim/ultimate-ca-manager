/**
 * History of a certificate: what its record keeps, and its entries of the audit log for
 * an account that may read it; the screen says which of the two it shows.
 */
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const env = vi.hoisted(() => ({ permissions: ['read:certificates', 'read:audit'] }))
const audit = vi.hoisted(() => ({ getLogs: vi.fn() }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (typeof opts === 'string' ? opts : opts?.count !== undefined ? `${key}:${opts.count}` : key),
    i18n: { language: 'en' },
  }),
}))
vi.mock('../../../../contexts/AuthContext', () => ({ useAuth: () => ({ permissions: env.permissions }) }))
vi.mock('../../../../services', () => ({ auditService: audit }))

import { CertificateHistory } from '../CertificateHistory'

const CERT = { id: 7, created_at: '2026-01-01T10:00:00Z', created_by: 'admin', source: 'manual' }
const log = (over) => ({ timestamp: '2026-02-01T09:00:00Z', username: 'ops', action: 'certificate_exported', resource_type: 'certificate', resource_id: '7', success: true, ...over })
const mount = () => render(<MemoryRouter><CertificateHistory certificate={CERT} /></MemoryRouter>)

describe('CertificateHistory', () => {
  beforeEach(() => {
    audit.getLogs.mockReset()
    env.permissions = ['read:certificates', 'read:audit']
  })

  it('keeps the audit entries of this certificate only, newest first, and says how far it read', async () => {
    audit.getLogs.mockResolvedValue({ data: [log({}), log({ resource_id: '8', action: 'certificate_revoked' }), log({ timestamp: '2026-03-01T09:00:00Z', action: 'certificate_renewed', success: false })], meta: { total_pages: 1 } })
    mount()
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('inspector.history.scope:3'))
    expect(audit.getLogs).toHaveBeenCalledWith({ resource_type: 'certificate', page: 1, per_page: 100 })
    const rows = [...screen.getByTestId('cert-history').querySelectorAll('li')]
    expect(rows.map((li) => li.querySelector('.insp-history-what').textContent)).toEqual([
      'certificate renewed (inspector.history.failed)', 'certificate exported', 'inspector.history.issued',
    ])
    expect(rows[0]).toHaveClass('is-bad')
    expect(rows[1].querySelector('.insp-history-who')).toHaveTextContent('ops')
    expect(screen.getByRole('link', { name: 'inspector.history.openAudit' })).toHaveAttribute('href', '/audit')
  })

  it('reads the following pages while the log has more, three at most', async () => {
    audit.getLogs.mockResolvedValue({ data: Array.from({ length: 100 }, () => log({ resource_id: '9' })), meta: { total_pages: 9 } })
    mount()
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('inspector.history.scope:300'))
    expect(audit.getLogs).toHaveBeenCalledTimes(3)
  })

  it('shows the record alone, and says so, for an account that cannot read the audit log', async () => {
    env.permissions = ['read:certificates']
    mount()
    expect(screen.getByRole('status')).toHaveTextContent('inspector.history.noAudit')
    expect(screen.getByTestId('cert-history')).toHaveTextContent('inspector.history.issued')
    expect(audit.getLogs).not.toHaveBeenCalled()
    expect(screen.queryByRole('link')).toBeNull()
  })

  it('shows the record alone, and says so, when the audit log cannot be read', async () => {
    audit.getLogs.mockRejectedValue(new Error('down'))
    mount()
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('inspector.history.loadFailed'))
    expect(screen.getByTestId('cert-history')).toHaveTextContent('inspector.history.issued')
  })
})
