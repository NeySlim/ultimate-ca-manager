/**
 * UserCertificatesPage on the mockup's module list template: the state chips counted by the
 * server's statistics and filtering on the server, the columns, the dock and its menu, the link to
 * the certificate in the Certificates zone, the read error.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'

vi.mock('react-i18next', async () => {
  const { enI18n } = await import('../../test/enT')
  return { useTranslation: () => enI18n, Trans: ({ children }) => children, initReactI18next: { type: '3rdParty', init: () => {} } }
})

const perms = vi.hoisted(() => ({ certs: true }))
const stable = vi.hoisted(() => ({
  notify: { showSuccess: () => {}, showError: () => {}, showWarning: () => {}, showConfirm: () => Promise.resolve(false), showPrompt: () => {} },
}))
vi.mock('../../contexts', () => ({ useNotification: () => stable.notify, useMobile: () => ({ isMobile: false }) }))
vi.mock('../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: false }) }))
vi.mock('../../hooks', async () => {
  const { useState } = await vi.importActual('react')
  return {
    usePersistedState: (_key, initial) => useState(initial),
    usePermission: () => ({
      canWrite: () => true, canDelete: () => true, canRead: () => true,
      hasPermission: (p) => (p === 'read:certificates' ? perms.certs : true),
    }),
  }
})
const getAll = vi.fn()
vi.mock('../../services', () => ({
  userCertificatesService: {
    getAll: (...a) => getAll(...a),
    getStats: () => Promise.resolve({ data: { total: 4, valid: 3, expiring: 0, expired: 1, revoked: 0 } }),
    getById: (id) => Promise.resolve({ data: ROWS.find((r) => r.id === id) }),
    export: vi.fn(), revoke: vi.fn(), delete: vi.fn(),
  },
}))

import UserCertificatesPage from '../UserCertificatesPage'

const ROWS = [
  { id: 4, cert_id: 97, name: 'admin@mtls', description: 'mTLS certificate for admin', owner: 'admin', status: 'valid',
    valid_to: '2027-06-02T22:57:27Z', has_private_key: true, key_type: 'RSA 2048', cert_issuer: 'CN=Issuing CA', serial_number: '255' },
]
const Where = () => <span data-testid="where">{useLocation().pathname + useLocation().search}</span>
const renderPage = () => render(
  <MemoryRouter initialEntries={['/user-certificates']}>
    <Routes><Route path="*" element={<><UserCertificatesPage /><Where /></>} /></Routes>
  </MemoryRouter>,
)

beforeEach(() => {
  perms.certs = true
  getAll.mockReset().mockResolvedValue({ data: { items: ROWS, total: 4 } })
})

describe('User certificates list', () => {
  it('counts the chips from the statistics and shows the module list columns', async () => {
    const { container } = renderPage()
    const row = (await screen.findByRole('button', { name: 'admin@mtls' })).closest('tr')
    expect(container.querySelector('.page-head .total')).toHaveTextContent('4 certificates')
    expect([...container.querySelectorAll('.views .view-btn')].map((b) => b.textContent)).toEqual(['All4', 'Valid3', 'To renew0', 'Expired1', 'Revoked0'])
    expect([...container.querySelectorAll('thead th')].map((th) => th.textContent).slice(0, 5)).toEqual(['Name', 'Description', 'Owner', 'Expiry', 'State'])
    expect(row).toHaveTextContent('mTLS certificate for admin')
    expect(row.querySelector('.badge.good')).toHaveTextContent('Valid')
  })

  it('filters on the server from a chip, back on the first page', async () => {
    const { container } = renderPage()
    await screen.findByRole('button', { name: 'admin@mtls' })
    fireEvent.click(container.querySelector('[data-status="expired"]'))
    await waitFor(() => expect(getAll).toHaveBeenLastCalledWith(expect.objectContaining({ status: ['expired'], page: 1 })))
    fireEvent.click(container.querySelector('[data-status=""]'))
    await waitFor(() => expect(getAll.mock.calls.at(-1)[0].status).toBeUndefined())
  })

  it('says why the read failed and retries it', async () => {
    getAll.mockReset().mockRejectedValueOnce(Object.assign(new Error('boom'), { status: 500 })).mockResolvedValue({ data: { items: ROWS, total: 1 } })
    const { container } = renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent('Failed to load certificates')
    fireEvent.click(container.querySelector('#retry-user-certificates'))
    expect(await screen.findByRole('button', { name: 'admin@mtls' })).toBeTruthy()
  })
})

describe('User certificate dock', () => {
  it('opens the enrolment, its certificate in the Certificates zone, and its menu', async () => {
    const { container } = renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'admin@mtls' }))
    const dock = await waitFor(() => { const d = container.querySelector('#inspector'); expect(d).toBeTruthy(); return d })
    expect(dock).toHaveTextContent('CN=Issuing CA')
    expect(dock).toHaveTextContent('FF')
    fireEvent.click(within(dock).getByRole('button', { name: /Other actions/ }))
    const menu = await screen.findByTestId('inspector-actions-dialog')
    expect([...menu.querySelectorAll('.columns-list button')].map((b) => b.textContent)).toEqual(['Lint', 'Recover key', 'Revoke', 'Delete'])
    fireEvent.click(menu.querySelector('.modal-head button'))
    fireEvent.click(within(dock).getByRole('button', { name: 'Inspect the certificate' }))
    expect(screen.getByTestId('where').textContent).toBe('/certificates?id=97')
  })

  it('offers no link to the certificate without read:certificates', async () => {
    perms.certs = false
    const { container } = renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'admin@mtls' }))
    const dock = await waitFor(() => { const d = container.querySelector('#inspector'); expect(d).toBeTruthy(); return d })
    expect(within(dock).queryByRole('button', { name: 'Inspect the certificate' })).toBeNull()
  })
})
