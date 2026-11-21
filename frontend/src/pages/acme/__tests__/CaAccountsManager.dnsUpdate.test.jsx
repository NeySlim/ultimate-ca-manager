/**
 * The DNS UPDATE keys tab of a CA account's dock: shown when the proxy is on,
 * or when the account still has keys (they can be revoked after the proxy is off).
 */
import { describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../../contexts', () => ({ useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn() }), useMobile: () => ({ isMobile: false }) }))

vi.mock('../DnsUpdateKeysPanel', () => ({
  default: ({ proxyActive }) => <div data-testid="keys-panel" data-proxy-active={String(proxyActive)} />,
}))

import CaAccountsManager from '../CaAccountsManager'
import { WithDockSlot } from '../../protocols/__tests__/withDockSlot'

const account = (extra = {}) => ({
  id: 1, label: 'Actalis', directory_url: 'https://ca.example/dir', email: 'a@example.com',
  account_key_algorithm: 'ES256', is_default: false, is_registered: true,
  proxy_enabled: true, proxy_slug: 'actalis', dns_update_key_count: 0, ...extra,
})

// The account opens its dock; the keys are a tab of it
const renderManager = (acct) => {
  render(<WithDockSlot><CaAccountsManager accounts={[acct]} canWrite canDelete /></WithDockSlot>)
  screen.getByRole('button', { name: 'Actalis' }).click()
}
const keysTab = () => within(screen.getByRole('complementary')).queryByRole('tab', { name: 'acme.dnsUpdate.title' })

describe('CaAccountsManager DNS UPDATE keys button', () => {
  it('shows the button for an account whose proxy is off and that has keys', async () => {
    const user = userEvent.setup()
    renderManager(account({ proxy_enabled: false, dns_update_key_count: 1 }))
    await user.click(await screen.findByRole('tab', { name: 'acme.dnsUpdate.title' }))
    expect(screen.getByTestId('keys-panel')).toHaveAttribute('data-proxy-active', 'false')
  })

  it('shows the button for an account whose proxy has no slug and that has keys', async () => {
    renderManager(account({ proxy_slug: null, dns_update_key_count: 2 }))
    expect(await screen.findByRole('tab', { name: 'acme.dnsUpdate.title' })).toBeInTheDocument()
  })

  it('hides the button for an account whose proxy is off and that has no keys', async () => {
    renderManager(account({ proxy_enabled: false, dns_update_key_count: 0 }))
    await screen.findByRole('complementary')
    expect(keysTab()).not.toBeInTheDocument()
  })

  it('hides the button when the count is missing and the proxy is off', async () => {
    renderManager(account({ proxy_enabled: false, dns_update_key_count: undefined }))
    await screen.findByRole('complementary')
    expect(keysTab()).not.toBeInTheDocument()
  })

  it('shows the button for an account whose proxy is on, without keys', async () => {
    const user = userEvent.setup()
    renderManager(account())
    await user.click(await screen.findByRole('tab', { name: 'acme.dnsUpdate.title' }))
    expect(screen.getByTestId('keys-panel')).toHaveAttribute('data-proxy-active', 'true')
  })
})
