/** The ACME client key type setting offers ML-DSA only where this server can use it. */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../../hooks', () => ({
  useClipboard: () => ({ copy: vi.fn() }),
}))

const getEffective = vi.fn()
vi.mock('../../../services', () => ({ policiesService: { getEffective: (...a) => getEffective(...a) } }))

vi.mock('../../../components/ui/ToggleSwitch', () => ({
  ToggleSwitch: () => null,
}))

vi.mock('../../../components', () => ({
  HelpCard: ({ children }) => <div>{children}</div>,
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Badge: ({ children }) => <span>{children}</span>,
  CompactSection: ({ title, children }) => <section><h2>{title}</h2>{children}</section>,
  Select: ({ label, options = [], value }) => (
    <select aria-label={label} value={value ?? ''} onChange={() => {}}>
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

const PQ = ['ML-DSA-44', 'ML-DSA-65', 'ML-DSA-87']
const offered = () => Array.from(screen.getByLabelText('acme.keyType').options).map(o => o.value)

describe('LetsEncryptTab certificate key type', () => {
  beforeEach(() => getEffective.mockReset())

  it('offers the three ML-DSA levels', async () => {
    getEffective.mockResolvedValue({ data: {} })
    renderTab()
    await waitFor(() => expect(getEffective).toHaveBeenCalled())
    expect(offered()).toEqual(expect.arrayContaining(PQ))
  })

  it.each([['in FIPS mode', { fips: true }], ['on a build without it', { ml_dsa: false }]])(
    'offers no ML-DSA %s', async (_name, effective) => {
      getEffective.mockResolvedValue({ data: effective })
      renderTab()
      await waitFor(() => expect(offered().filter(v => PQ.includes(v))).toEqual([]))
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
