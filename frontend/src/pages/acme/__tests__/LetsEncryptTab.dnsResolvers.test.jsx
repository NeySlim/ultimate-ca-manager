import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../../hooks', () => ({
  useClipboard: () => ({ copy: vi.fn() }),
}))

vi.mock('../../../components/ui/ToggleSwitch', () => ({
  ToggleSwitch: () => null,
}))

vi.mock('../../../components', () => ({
  HelpCard: ({ children }) => <div>{children}</div>,
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Badge: ({ children }) => <span>{children}</span>,
  CompactSection: ({ title, children }) => <section><h2>{title}</h2>{children}</section>,
  Select: ({ label, value, onChange, options }) => (
    <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  ),
  Input: (props) => <input {...props} />,
  FilterSelect: ({ value, onChange, allLabel, options }) => (
    <select aria-label="status-filter" value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{allLabel}</option>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  ),
}))

import LetsEncryptTab from '../LetsEncryptTab'

const orders = [
  { id: 1, primary_domain: 'a.example.com', status: 'valid', environment: 'production' },
  { id: 2, primary_domain: 'b.example.com', status: 'pending', environment: 'production' },
]

const noop = vi.fn()
const renderTab = (props = {}) => render(
  <LetsEncryptTab
    clientOrders={orders}
    selectedClientOrder={null}
    onSelectOrder={noop}
    clientSettings={{}}
    localContactEmail=""
    onLocalContactEmailChange={noop}
    localProxyUpstreamUrl=""
    onLocalProxyUpstreamUrlChange={noop}
    localProxyEabKid=""
    onLocalProxyEabKidChange={noop}
    proxyEabHmacInput=""
    onProxyEabHmacInputChange={noop}
    proxyEmail=""
    onProxyEmailChange={noop}
    testingConnection={false}
    connectionResult={null}
    onBlurSave={noop}
    onBlurSaveInt={noop}
    localDnsTimeout="120"
    onLocalDnsTimeoutChange={noop}
    localDnsNameservers="10.0.0.53"
    onLocalDnsNameserversChange={noop}
    onUpdateClientSetting={noop}
    onRegisterProxy={noop}
    onUnregisterProxy={noop}
    onProxyAccountChange={noop}
    onResetProxyAccount={noop}
    onTestConnection={noop}
    onRequestCertificate={noop}
    onRefresh={noop}
    onCheckOrderStatus={noop}
    onVerifyChallenge={noop}
    onFinalizeOrder={noop}
    onViewCertificate={noop}
    onDownloadCertificate={noop}
    onRenewCertificate={noop}
    onDeleteOrder={noop}
    canWrite
    canDelete
    {...props}
  />
)

describe('LetsEncryptTab DNS-01 resolvers (#394)', () => {
  beforeEach(() => vi.clearAllMocks())

  const resolversInput = () => screen.queryByPlaceholderText('10.0.0.53, 127.0.0.1:5353')

  it('saves the mode from the select', () => {
    const onUpdateClientSetting = vi.fn()
    renderTab({ onUpdateClientSetting })
    fireEvent.change(screen.getByLabelText('acme.dnsResolverMode'), { target: { value: 'system' } })
    expect(onUpdateClientSetting).toHaveBeenCalledWith('dns01_resolver_mode', 'system')
  })

  it('saves the resolver list on blur', () => {
    const onBlurSave = vi.fn()
    const onLocalDnsNameserversChange = vi.fn()
    renderTab({ onBlurSave, onLocalDnsNameserversChange, clientSettings: { dns01_resolver_mode: 'custom' } })
    fireEvent.blur(resolversInput())
    expect(onBlurSave).toHaveBeenCalledWith('dns01_nameservers', '10.0.0.53', onLocalDnsNameserversChange)
  })

  it('hides the resolver list in system mode', () => {
    renderTab({ clientSettings: { dns01_resolver_mode: 'system' } })
    expect(resolversInput()).not.toBeInTheDocument()
    expect(screen.getByLabelText('acme.dnsResolverMode')).toHaveValue('system')
  })

  it('defaults to automatic', () => {
    renderTab()
    expect(screen.getByLabelText('acme.dnsResolverMode')).toHaveValue('auto')
    expect(resolversInput()).toBeInTheDocument()
  })
})
