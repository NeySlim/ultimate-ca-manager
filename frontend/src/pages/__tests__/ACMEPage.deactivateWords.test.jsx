/**
 * Deactivating an ACME account asks the mockup's question ("Désactiver ce compte ACME ?")
 * and confirms with "Désactiver le compte", not a bare "Désactiver".
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { notificationSpies } from './pageRenderingSetup.jsx'
import { acmeService } from '../../services/acme.service'
// An operator who may deactivate an account at an upstream CA
vi.mock('../../hooks/usePermission', () => ({
  usePermission: () => ({ hasPermission: () => true, canRead: () => true, canWrite: () => true, canDelete: () => true, isAdmin: () => true }),
}))
import ACMEPage from '../ACMEPage'

const ok = (data) => vi.fn().mockResolvedValue({ data })
const ACCOUNT = { id: 5, account_id: 'acct-5', contact: ['mailto:ops@example.com'], status: 'valid', created_at: '2026-01-01T00:00:00Z' }

beforeEach(() => {
  vi.clearAllMocks()
  window.localStorage.clear()
  notificationSpies.showConfirm = vi.fn().mockResolvedValue(false)
  Object.assign(acmeService, {
    getSettings: ok({}), getHistory: vi.fn().mockResolvedValue({ data: [], meta: { total: 0 } }), getClientSettings: ok({}),
    getDnsProviders: ok([]), getDnsProviderTypes: ok([]), getDomains: ok([]), getLocalDomains: ok([]),
    getEabRequired: ok({ eab_required: false }), getCaAccounts: ok([]),
    getClientOrders: vi.fn().mockResolvedValue({ data: [], meta: { total: 0 } }),
    getAccounts: ok([ACCOUNT]), getAccountById: ok(ACCOUNT), getOrders: ok([]), getChallenges: ok([]),
  })
})

describe('ACME account deactivation', () => {
  it('asks to deactivate this ACME account and confirms with Deactivate account', async () => {
    render(<MemoryRouter initialEntries={['/acme?tab=accounts']}><ACMEPage /></MemoryRouter>)
    const tab = (await screen.findAllByText('acme.accounts'))[0]
    fireEvent.click(tab)
    fireEvent.click((await screen.findAllByText(/acct-5|ops@example\.com/))[0])
    await waitFor(() => expect(acmeService.getAccountById).toHaveBeenCalled())
    const button = await screen.findByRole('button', { name: /common\.deactivate$/ })
    fireEvent.click(button)
    await waitFor(() => expect(notificationSpies.showConfirm).toHaveBeenCalled())
    expect(notificationSpies.showConfirm.mock.calls[0][1]).toMatchObject({
      title: 'acme.deactivateAccountTitle', confirmText: 'common.deactivateAccount', variant: 'danger',
    })
  })

  it('asks the same question for an account at an upstream ACME CA', async () => {
    acmeService.getCaAccounts = ok([{ id: 9, name: 'Upstream', directory_url: 'https://ca.example/directory', is_registered: true, is_default: true }])
    render(<MemoryRouter initialEntries={['/acme?tab=letsencrypt']}><ACMEPage /></MemoryRouter>)
    fireEvent.click(await screen.findByRole('button', { name: 'acme.certificateAuthorities' }))
    const button = (await screen.findAllByRole('button', { name: /common\.deactivate$/ }))[0]
    fireEvent.click(button)
    await waitFor(() => expect(notificationSpies.showConfirm).toHaveBeenCalled())
    expect(notificationSpies.showConfirm.mock.calls[0][1]).toMatchObject({
      title: 'acme.deactivateAccountTitle', confirmText: 'common.deactivateAccount', variant: 'danger',
    })
  })
})
