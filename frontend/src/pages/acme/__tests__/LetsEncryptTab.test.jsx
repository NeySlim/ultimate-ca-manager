/**
 * The ACME client settings as the mockup's settingsView(): one draft saved in one request with
 * only what changed, the server's bounds checked first, the DNS-01 resolvers, the certificate key
 * type offered where this server can use it, and the proxy's own actions.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'en' } }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
const notify = vi.hoisted(() => ({ showSuccess: vi.fn(), showError: vi.fn() }))
vi.mock('../../../contexts', () => ({ useNotification: () => notify, useMobile: () => ({ isMobile: false }) }))
vi.mock('../../../hooks', () => ({ useClipboard: () => ({ copy: vi.fn() }) }))

const getEffective = vi.fn()
const updateClientSettings = vi.fn()
vi.mock('../../../services', () => ({
  policiesService: { getEffective: (...a) => getEffective(...a) },
  acmeService: { updateClientSettings: (...a) => updateClientSettings(...a) },
}))

import LetsEncryptTab from '../LetsEncryptTab'

const noop = vi.fn()
const renderTab = (props = {}) => render(
  <div className="atl">
    <LetsEncryptTab clientSettings={{ environment: 'staging', renewal_days: 30 }} caAccounts={[]} canWrite onSaved={noop}
      onSaveDnsUpdatePort={noop} onRegisterProxy={noop} onUnregisterProxy={noop} onResetProxyAccount={noop}
      onTestConnection={noop} testingConnection={false} connectionResult={null} {...props} />
  </div>,
)
const save = () => fireEvent.click(document.getElementById('settings-save'))

beforeEach(() => {
  vi.clearAllMocks()
  getEffective.mockResolvedValue({ data: {} })
  updateClientSettings.mockResolvedValue({})
})

describe('LetsEncryptTab settings', () => {
  it('saves only what changed, in one request, the days as a number', async () => {
    const onSaved = vi.fn()
    renderTab({ onSaved })
    fireEvent.change(screen.getByRole('textbox', { name: 'acme.renewalDays' }), { target: { value: '45' } })
    fireEvent.change(screen.getByRole('combobox', { name: 'acme.defaultEnvironment' }), { target: { value: 'production' } })
    save()
    await waitFor(() => expect(updateClientSettings).toHaveBeenCalledWith({ renewal_days: 45, environment: 'production' }))
    expect(onSaved).toHaveBeenCalled()
  })

  it.each([['acme.renewalDays', '61'], ['acme.dnsPropagationDelay', '301'], ['acme.dnsPropagationTimeout', '-1'], ['acme.tlsAlpnPort', '0']])(
    'refuses %s at %s before any request', (label, value) => {
      renderTab()
      const input = screen.getByRole('textbox', { name: label })
      fireEvent.change(input, { target: { value } })
      save()
      expect(input).toHaveAttribute('aria-invalid', 'true')
      expect(updateClientSettings).not.toHaveBeenCalled()
    })

  it('puts the draft back on reset', () => {
    renderTab()
    const days = screen.getByRole('textbox', { name: 'acme.renewalDays' })
    fireEvent.change(days, { target: { value: '45' } })
    fireEvent.click(screen.getByRole('button', { name: 'sectioned.undo' }))
    expect(days).toHaveValue('30')
  })

  it('has no global proxy switch and always shows the proxy settings', () => {
    renderTab({ clientSettings: {} })
    expect(screen.queryByText('acme.enableAcmeProxy')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'acme.testConnection' })).toBeDisabled()
  })
})

describe('LetsEncryptTab DNS-01 resolvers', () => {
  const resolvers = () => screen.queryByRole('textbox', { name: 'acme.dnsResolvers' })
  it('defaults to automatic, with the resolver list', () => {
    renderTab()
    expect(screen.getByRole('combobox', { name: 'acme.dnsResolverMode' })).toHaveValue('auto')
    expect(resolvers()).toBeInTheDocument()
  })

  it('hides the resolver list in system mode, and saves the mode', async () => {
    renderTab()
    fireEvent.change(screen.getByRole('combobox', { name: 'acme.dnsResolverMode' }), { target: { value: 'system' } })
    expect(resolvers()).not.toBeInTheDocument()
    save()
    await waitFor(() => expect(updateClientSettings).toHaveBeenCalledWith({ dns01_resolver_mode: 'system' }))
  })
})

describe('LetsEncryptTab certificate key type', () => {
  const PQ = ['ML-DSA-44', 'ML-DSA-65', 'ML-DSA-87']
  const offered = () => Array.from(screen.getByRole('combobox', { name: 'acme.keyType' }).options).map((o) => o.value)

  it('offers the three ML-DSA levels', async () => {
    renderTab()
    await waitFor(() => expect(getEffective).toHaveBeenCalled())
    expect(offered()).toEqual(expect.arrayContaining(PQ))
  })

  it.each([['in FIPS mode', { fips: true }], ['on a build without it', { ml_dsa: false }]])('offers no ML-DSA %s', async (_n, effective) => {
    getEffective.mockResolvedValue({ data: effective })
    renderTab()
    await waitFor(() => expect(offered().filter((v) => PQ.includes(v))).toEqual([]))
    expect(offered()).toContain('EC-P256')
  })

  it.each([
    ['ML-DSA-65', { fips: true }, true], ['EC-BP256', { fips: true }, true],
    ['ML-DSA-65', { ml_dsa: false }, true], ['ML-DSA-65', {}, false], ['EC-P256', { fips: true }, false],
  ])('flags a saved %s the server no longer offers (%o): %s', async (keyType, effective, flagged) => {
    getEffective.mockResolvedValue({ data: effective })
    renderTab({ clientSettings: { key_type: keyType } })
    await waitFor(() => expect(getEffective).toHaveBeenCalled())
    if (flagged) expect(await screen.findByText('acme.keyTypeUnavailable')).toBeInTheDocument()
    else {
      await new Promise((r) => setTimeout(r, 20))
      expect(screen.queryByText('acme.keyTypeUnavailable')).toBeNull()
    }
  })
})

describe('LetsEncryptTab proxy', () => {
  const ACCOUNTS = [{ id: 3, label: 'Actalis', email: 'ops@example.com', directory_url: 'https://ca.example/dir', is_registered: false }]
  it('registers the selected upstream account with the typed address', () => {
    const onRegisterProxy = vi.fn()
    renderTab({ clientSettings: { proxy_acme_account_id: 3 }, caAccounts: ACCOUNTS, onRegisterProxy })
    fireEvent.change(screen.getByLabelText('common.emailAddress'), { target: { value: 'me@example.com' } })
    fireEvent.click(screen.getByRole('button', { name: 'acme.registerAccount' }))
    expect(onRegisterProxy).toHaveBeenCalledWith('me@example.com')
  })

  it('offers reset and unregister once the account is registered, nothing without write', () => {
    const accounts = [{ ...ACCOUNTS[0], is_registered: true }]
    const { unmount } = renderTab({ clientSettings: { proxy_acme_account_id: 3 }, caAccounts: accounts })
    expect(screen.getByRole('button', { name: 'acme.resetAccount' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'acme.unregisterProxy' })).toBeInTheDocument()
    unmount()
    renderTab({ clientSettings: { proxy_acme_account_id: 3 }, caAccounts: accounts, canWrite: false })
    expect(screen.queryByRole('button', { name: 'acme.resetAccount' })).toBeNull()
    expect(screen.getByRole('combobox', { name: 'acme.defaultEnvironment' })).toBeDisabled()
  })
})
