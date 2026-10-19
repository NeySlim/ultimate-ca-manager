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
  Select: () => null,
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
    localRenewalDays="30"
    onLocalRenewalDaysChange={noop}
    onLocalDnsTimeoutChange={noop}
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

describe('LetsEncryptTab settings view', () => {
  beforeEach(() => vi.clearAllMocks())

  it('keeps orders out of the settings tab', () => {
    renderTab()
    expect(screen.queryByText('a.example.com')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('status-filter')).not.toBeInTheDocument()
  })

  it('opens the certificate request flow', () => {
    const onRequestCertificate = vi.fn()
    renderTab({ onRequestCertificate })
    fireEvent.click(screen.getByText('acme.requestCertificate'))
    expect(onRequestCertificate).toHaveBeenCalledOnce()
  })

  it('refreshes client settings', () => {
    const onRefresh = vi.fn()
    renderTab({ onRefresh })
    fireEvent.click(screen.getByText('common.refresh'))
    expect(onRefresh).toHaveBeenCalledOnce()
  })
})

describe('LetsEncryptTab renewal threshold', () => {
  it('saves the days before expiry the scheduled renewal reads', () => {
    const onBlurSaveInt = vi.fn()
    renderTab({ onBlurSaveInt, localRenewalDays: '45' })
    const field = screen.getByDisplayValue('45')
    fireEvent.blur(field)
    expect(onBlurSaveInt).toHaveBeenCalledWith('renewal_days', '45', expect.any(Function), { min: 1, max: 60, fallback: 30 })
  })
})
