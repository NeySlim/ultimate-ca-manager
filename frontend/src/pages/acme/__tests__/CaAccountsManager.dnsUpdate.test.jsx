/**
 * The "DNS UPDATE keys" button of a CA account: shown when the proxy is on,
 * or when the account still has keys (they can be revoked after the proxy is off).
 */
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../DnsUpdateKeysPanel', () => ({
  default: ({ proxyActive }) => <div data-testid="keys-panel" data-proxy-active={String(proxyActive)} />,
}))

import CaAccountsManager from '../CaAccountsManager'

const account = (extra = {}) => ({
  id: 1, label: 'Actalis', directory_url: 'https://ca.example/dir', email: 'a@example.com',
  account_key_algorithm: 'ES256', is_default: false, is_registered: true,
  proxy_enabled: true, proxy_slug: 'actalis', dns_update_key_count: 0, ...extra,
})

const renderManager = (acct) => render(
  <CaAccountsManager accounts={[acct]} canWrite canDelete />,
)

describe('CaAccountsManager DNS UPDATE keys button', () => {
  it('shows the button for an account whose proxy is off and that has keys', async () => {
    const user = userEvent.setup()
    renderManager(account({ proxy_enabled: false, dns_update_key_count: 1 }))
    await user.click(screen.getByRole('button', { name: /acme.dnsUpdate.manage/ }))
    expect(screen.getByTestId('keys-panel')).toHaveAttribute('data-proxy-active', 'false')
  })

  it('shows the button for an account whose proxy has no slug and that has keys', () => {
    renderManager(account({ proxy_slug: null, dns_update_key_count: 2 }))
    expect(screen.getByRole('button', { name: /acme.dnsUpdate.manage/ })).toBeInTheDocument()
  })

  it('hides the button for an account whose proxy is off and that has no keys', () => {
    renderManager(account({ proxy_enabled: false, dns_update_key_count: 0 }))
    expect(screen.queryByRole('button', { name: /acme.dnsUpdate.manage/ })).not.toBeInTheDocument()
  })

  it('hides the button when the count is missing and the proxy is off', () => {
    renderManager(account({ proxy_enabled: false, dns_update_key_count: undefined }))
    expect(screen.queryByRole('button', { name: /acme.dnsUpdate.manage/ })).not.toBeInTheDocument()
  })

  it('shows the button for an account whose proxy is on, without keys', async () => {
    const user = userEvent.setup()
    renderManager(account())
    await user.click(screen.getByRole('button', { name: /acme.dnsUpdate.manage/ }))
    expect(screen.getByTestId('keys-panel')).toHaveAttribute('data-proxy-active', 'true')
  })
})
