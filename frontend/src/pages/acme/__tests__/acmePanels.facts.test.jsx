/**
 * The ACME docks as typed rows (KV-3): a URL or an identifier in a copyable chip that copies it whole,
 * a serial in hex lines, a rule as a pill, a missing value muted, and the edit of a value apart from it.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'en' } }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showConfirm: vi.fn() }),
  useMobile: () => ({ isMobile: false }),
}))
vi.mock('../../../hooks', async () => ({
  usePersistedState: (await vi.importActual('../../../hooks/usePersistedState')).usePersistedState,
  useClipboard: () => ({ copy: vi.fn() }),
  usePermission: () => ({ hasPermission: () => true }),
}))
vi.mock('../../../services', () => ({
  apiClient: { patch: vi.fn() },
  policiesService: { getEffective: vi.fn().mockResolvedValue({ data: {} }) },
  acmeService: { updateClientSettings: vi.fn() },
}))
vi.mock('../../../stores/timezoneStore', () => ({ getAppTimezone: () => 'UTC' }))
vi.mock('../DnsUpdateKeysPanel', () => ({ default: () => null }))

import OrderDetailPanel from '../OrderDetailPanel'
import AccountDetailPanel from '../AccountDetailPanel'
import CaAccountsManager from '../CaAccountsManager'
import DomainsTab from '../DomainsTab'
import DnsProvidersTab from '../DnsProvidersTab'
import HistoryTab from '../HistoryTab'
import LetsEncryptTab from '../LetsEncryptTab'
import { WithDockSlot } from '../../protocols/__tests__/withDockSlot'
import { renderAtUrl } from '../../../test/dockUrl'

let writeText
beforeEach(() => {
  writeText = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
  Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true })
})

const row = (term) => {
  const found = [...document.querySelectorAll('dl.kv > div.row')].find((r) => r.querySelector('dt').textContent === term)
  if (!found) throw new Error(`no row ${term}`)
  return found
}
const noop = () => {}

describe('an ACME order', () => {
  const URL = 'http://www.example.com/.well-known/acme-challenge/tok-123'
  const order = (extra = {}) => ({
    id: 1, domains: ['www.example.com'], environment: 'production', status: 'pending', challenge_type: 'http-01',
    challenges: { 'www.example.com': { token: 'tok-123', key_authorization: 'tok-123.thumbprint' } }, ...extra,
  })
  const renderOrder = (o) => render(<OrderDetailPanel order={o} onClose={noop} onDownloadCert={noop} onViewCertificate={noop} canWrite
    onRenewCertificate={noop} onVerifyChallenge={noop} onFinalizeOrder={noop} onDeleteOrder={noop} />)

  it('shows the HTTP-01 URL cut in its middle, whole in its title and on a copy', async () => {
    renderOrder(order())
    const url = row('acme.http01Url')
    expect(url).toHaveClass('long')
    expect(url.querySelector('dd.v').querySelector('.code-value.url .val')).toHaveAttribute('title', URL)
    fireEvent.click(url.querySelector('dd.v').querySelector('.code-value .cp'))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(URL))
    expect(row('acme.http01FileContent').querySelector('dd.v .code-value')).toHaveTextContent('tok-123.thumbprint')
  })

  it('copies the DNS-01 record name and value whole', async () => {
    renderOrder(order({ challenge_type: 'dns-01', challenges: { 'www.example.com': { dns_txt_name: '_acme-challenge.www.example.com', dns_txt_value: 'Zm9vYmFy' } } }))
    fireEvent.click(row('acme.dnsRecordValue').querySelector('.code-value .cp'))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('Zm9vYmFy'))
    expect(row('acme.dnsRecordName').querySelector('.code-value')).toHaveTextContent('_acme-challenge.www.example.com')
  })

  it('writes a missing method muted and the state as a pill', () => {
    renderOrder(order({ challenge_type: null, challenges: null }))
    expect(row('acme.method').querySelector('dd')).toHaveClass('absent')
    expect(row('atelier.state').querySelector('dd.v .badge')).not.toBeNull()
  })
})

describe('an ACME account', () => {
  const account = { id: 7, account_id: 'acme-1234567890abcdef', status: 'valid', contact: ['mailto:old@example.com'], key_type: 'EC-P256', created_at: null }
  const renderAccount = (a = account) => render(<AccountDetailPanel account={a} orders={[]} challenges={[]} section="account"
    onSection={vi.fn()} onClose={vi.fn()} onDeactivate={vi.fn()} onDelete={vi.fn()} />)

  it('puts the email edit apart from the contact, a write button', () => {
    renderAccount()
    const contact = row('acme.contact')
    expect(contact.querySelector('dd.v')).toHaveTextContent(/^mailto:old@example.com$/)
    const edit = screen.getByRole('button', { name: 'acme.editEmail' })
    expect(edit.closest('dd')).toHaveClass('act')
    expect(edit).toHaveAttribute('data-write', '')
  })

  it('copies the identifier and writes a missing contact or date muted', async () => {
    renderAccount({ ...account, contact: [] })
    fireEvent.click(row('acme.identifier').querySelector('.code-value .cp'))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('acme-1234567890abcdef'))
    expect(row('acme.contact').querySelector('dd')).toHaveClass('absent')
    expect(row('acme.createdOn').querySelector('dd')).toHaveClass('absent')
  })
})

describe('an upstream CA account', () => {
  const acct = { id: 1, label: 'Actalis', directory_url: 'https://acme-api.actalis.com/acme/directory', email: '', account_key_algorithm: 'ES384',
    is_default: false, is_registered: true, account_url: 'https://acme-api.actalis.com/acme/acct/123456789' }

  it('shows its URLs as chips, the default as a word and no EAB muted', async () => {
    render(<WithDockSlot><CaAccountsManager accounts={[acct]} canWrite canDelete onUpdate={vi.fn()} /></WithDockSlot>)
    fireEvent.click(screen.getByRole('button', { name: 'Actalis' }))
    await screen.findByText('acme.caTimingSettings')
    expect(row('acme.directoryUrl').querySelector('.code-value.url .val')).toHaveAttribute('title', acct.directory_url)
    expect(row('acme.accountUrl').querySelector('.code-value.url .val')).toHaveAttribute('title', acct.account_url)
    expect(row('common.default').querySelector('dd.v')).toHaveTextContent(/^common.no$/)
    expect(row('common.default').querySelector('.flag')).toBeNull()
    expect(row('EAB').querySelector('dd')).toHaveClass('absent')
    expect(row('acme.contactEmail').querySelector('dd')).toHaveClass('absent')
  })
})

describe('an ACME domain', () => {
  it('shows the wildcard rule as a pill', async () => {
    const domains = [{ id: 1, domain: 'example.test', dns_provider_name: 'cf', issuing_ca_name: null, is_wildcard_allowed: false, auto_approve: false }]
    const r = renderAtUrl(<WithDockSlot><DomainsTab acmeDomains={domains} onAdd={noop} onEdit={noop} onDelete={noop} onTest={noop} canWrite canDelete /></WithDockSlot>, '/acme?tab=domains&item=1')
    await r.dock()
    const wildcard = row('acme.wildcard')
    expect(wildcard.querySelector('dd.v .badge.muted')).toHaveTextContent('common.no')
    expect(wildcard.querySelector('.flag')).toBeNull()
  })
})

describe('a DNS provider', () => {
  it('writes no credential muted', async () => {
    const providers = [{ id: 1, name: 'cf', provider_type: 'cloudflare', is_default: true, credential_keys: [] }]
    const r = renderAtUrl(<WithDockSlot><DnsProvidersTab dnsProviders={providers} onAddProvider={noop} onEditProvider={noop} onTestProvider={noop} onDeleteProvider={noop} canWrite canDelete /></WithDockSlot>, '/acme?tab=dns&item=1')
    await r.dock()
    expect(row('acme.credentials').querySelector('dd')).toHaveClass('absent')
  })
})

describe('a certificate in the ACME history', () => {
  it('shows its serial in hex lines that copy whole', async () => {
    const serial = '4A:3F:00:11:22:33:44:55:66:77:88:99:AA:BB:CC:DD'
    const cert = { id: 3, common_name: 'www.example.com', serial, issuer: 'CA', source: 'acme', created_at: null, order: { order_id: 'ord-42' } }
    render(<WithDockSlot><HistoryTab history={[cert]} total={1} page={1} perPage={25} onPageChange={noop} onPerPageChange={noop} search="" onSearchChange={noop}
      caOptions={[]} filterStatus={[]} onFilterStatusChange={noop} onFilterCAChange={noop} onFilterSourceChange={noop} selectedCert={cert} onSelectCert={noop} /></WithDockSlot>)
    const hex = row('common.serialNumber').querySelector('.code-value.hex')
    expect(hex.querySelectorAll('.line')).toHaveLength(2)
    fireEvent.click(hex.querySelector('.cp'))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(serial))
    expect(row('acme.orderId').querySelector('.code-value')).toHaveTextContent('ord-42')
    expect(row('common.issued').querySelector('dd')).toHaveClass('absent')
  })
})

describe('the ACME proxy URLs', () => {
  it('are chips that copy the whole URL', async () => {
    render(<div className="atl"><LetsEncryptTab clientSettings={{ environment: 'staging', renewal_days: 30 }} caAccounts={[]} canWrite onSaved={noop}
      onSaveDnsUpdatePort={noop} onRegisterProxy={noop} onUnregisterProxy={noop} onResetProxyAccount={noop}
      onTestConnection={noop} testingConnection={false} connectionResult={null} /></div>)
    const proxy = row('acme.proxyPathUrl')
    const whole = proxy.querySelector('.code-value .val').getAttribute('title') || proxy.querySelector('.code-value .val').textContent
    expect(whole).toMatch(/\/acme\/proxy\/directory$/)
    fireEvent.click(proxy.querySelector('.code-value .cp'))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(whole))
  })
})
