/**
 * The certificate in the inspector: a heading with the state, Export, the main action and
 * a menu for the rest; Overview, Chain, Extensions, History and PEM; an Overview in three
 * columns under the page and in one beside it; nothing a permission hides.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const env = vi.hoisted(() => ({ permissions: ['*'] }))
const mocks = vi.hoisted(() => ({
  audit: { getLogs: vi.fn() },
  dashboard: { getQueue: vi.fn() },
  cas: { getAll: vi.fn() },
  truststore: { addFromCA: vi.fn() },
  certificates: { getById: vi.fn() },
  notify: { showSuccess: vi.fn(), showError: vi.fn() },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (typeof opts === 'string' ? opts : opts?.count !== undefined ? `${key}:${opts.count}` : key),
    i18n: { language: 'en' },
  }),
}))
vi.mock('../../../../contexts', () => ({ useNotification: () => mocks.notify }))
vi.mock('../../../../contexts/AuthContext', () => ({ useAuth: () => ({ permissions: env.permissions }) }))
vi.mock('../../../../services', () => ({
  auditService: mocks.audit,
  dashboardService: mocks.dashboard,
  casService: mocks.cas,
  truststoreService: mocks.truststore,
  certificatesService: mocks.certificates,
}))
vi.mock('../../../deploy/CertDeploySection', () => ({ CertDeploySection: () => <div data-testid="deployments" /> }))

import { CertificateDetail } from '../CertificateDetail'

const CERT = {
  id: 7, refid: 'cert-7', created_at: '2026-01-01T00:00:00Z', common_name: 'web.example.com', subject: 'CN=web.example.com,O=Example', issuer: 'CN=Issuing CA',
  caref: 'ca-2', status: 'valid', days_remaining: 120, valid_from: '2026-01-01T00:00:00Z', valid_to: '2027-01-01T00:00:00Z',
  source: 'acme', key_algorithm: 'RSA 2048', signature_algorithm: 'sha256WithRSAEncryption', serial_number: '255',
  has_private_key: true, pem: '-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----',
  extensions: {
    subject_alt_names: { entries: Array.from({ length: 8 }, (_, i) => ({ type: 'DNS', value: `n${i}.example.com` })), critical: false },
    key_usage: { usages: ['digital_signature'], critical: true },
  },
  chain_status: { status: 'complete', trust_source: 'managed_ca', trust_anchor: 'Root CA', chain: [{ name: 'Issuing CA', type: 'managed_ca' }, { name: 'Root CA', type: 'managed_ca' }] },
}
const action = (id, over = {}) => ({ id, label: `do-${id}`, visible: true, onClick: vi.fn(), ...over })
const ACTIONS = () => [
  action('export'), action('renew'), action('lint'), action('rename'), action('uploadKey', { visible: false }),
  action('revoke', { danger: true }), action('delete', { danger: true }),
]

const mount = (props = {}) => {
  const onOpen = vi.fn()
  const actions = props.actions || ACTIONS()
  render(
    <MemoryRouter>
      <CertificateDetail objectKey="certificate:7" certificate={CERT} title="web.example.com" actions={actions} onOpen={onOpen} {...props} />
    </MemoryRouter>)
  return { onOpen, actions }
}
const openMenu = () => {
  fireEvent.keyDown(screen.getByRole('button', { name: 'inspector.moreActions' }), { key: 'Enter' })
  return screen.getByRole('menu')
}

describe('CertificateDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    env.permissions = ['*']
    localStorage.clear()
    mocks.audit.getLogs.mockResolvedValue({ data: [], meta: { total_pages: 1 } })
    mocks.dashboard.getQueue.mockResolvedValue({ data: { items: [] } })
  })

  it('heads the object with its name, its state in words, Export and the main action', () => {
    const { actions } = mount()
    const heading = screen.getByRole('heading', { level: 2, name: 'web.example.com' }).closest('header')
    expect(heading.querySelector('.lv-pill')).toHaveTextContent('common.valid')
    const renew = within(heading).getByRole('button', { name: 'do-renew' })
    expect(renew).toHaveClass('is-primary')
    expect(within(heading).getByRole('button', { name: 'do-export' })).not.toHaveClass('is-primary')
    fireEvent.click(renew)
    expect(actions[1].onClick).toHaveBeenCalledTimes(1)
    fireEvent.click(within(heading).getByRole('button', { name: 'do-export' }))
    expect(actions[0].onClick).toHaveBeenCalledTimes(1)
  })

  it('makes Export the main action when the certificate cannot be renewed', () => {
    mount({ actions: [action('export'), action('renew', { visible: false })] })
    expect(screen.getByRole('button', { name: 'do-export' })).toHaveClass('is-primary')
    expect(screen.queryByRole('button', { name: 'do-renew' })).toBeNull()
  })

  it('keeps every other action in the menu, the destructive ones last, and runs it', () => {
    const { actions } = mount()
    const items = within(openMenu()).getAllByRole('menuitem').map((i) => i.textContent)
    expect(items).toEqual(['do-lint', 'do-rename', 'inspector.favorite', 'do-revoke', 'do-delete'])
    fireEvent.click(within(screen.getByRole('menu')).getByRole('menuitem', { name: 'do-revoke' }))
    expect(actions[5].onClick).toHaveBeenCalledTimes(1)
  })

  it('draws no action a permission hides', () => {
    mount({ actions: [action('export'), action('renew', { visible: false }), action('revoke', { visible: false, danger: true }), action('delete', { visible: false, danger: true })] })
    const items = within(openMenu()).getAllByRole('menuitem').map((i) => i.textContent)
    expect(items).toEqual(['inspector.favorite'])
  })

  it('adds the certificate to the favorites from the menu and takes it off', () => {
    mount()
    fireEvent.click(within(openMenu()).getByRole('menuitem', { name: 'inspector.favorite' }))
    expect(within(openMenu()).getByRole('menuitem', { name: 'inspector.unfavorite' })).toBeInTheDocument()
  })

  it('offers Overview, Chain, Extensions, History and PEM, switched by click and by arrow keys', async () => {
    mount()
    const tabs = screen.getAllByRole('tab')
    expect(tabs.map((tab) => tab.textContent)).toEqual([
      'inspector.sections.overview', 'inspector.sections.chain', 'inspector.sections.extensions',
      'inspector.sections.history', 'inspector.sections.pem',
    ])
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true')
    const panel = screen.getByRole('tabpanel')
    expect(panel).toHaveAttribute('aria-labelledby', tabs[0].id)
    expect(panel).toHaveAttribute('tabindex', '0')
    fireEvent.click(tabs[1])
    expect(screen.getByTestId('chain-canvas')).toBeInTheDocument()
    fireEvent.keyDown(screen.getAllByRole('tab')[1], { key: 'ArrowRight' })
    expect(screen.getByTestId('cert-extensions')).toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('tab')[3])
    expect(await screen.findByTestId('cert-history')).toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('tab')[4])
    expect(screen.getByText(/BEGIN CERTIFICATE/)).toBeInTheDocument()
  })

  it.each([['columns'], ['column']])('lays the Overview out as %s, the three parts in the order of the frame', (layout) => {
    mount({ layout })
    const overview = screen.getByTestId('cert-overview')
    expect(overview).toHaveAttribute('data-layout', layout)
    expect(screen.getByRole('tabpanel')).toHaveAttribute('data-layout', layout)
    expect([...overview.children].map((s) => s.querySelector('h3').textContent)).toEqual([
      'inspector.cert.validity', 'inspector.cert.identity', 'inspector.cert.trustChain',
    ])
    expect(within(overview.children[0]).getByText('inspector.cert.days:120')).toBeInTheDocument()
  })

  it('shows six alternative names and opens Extensions for the others', () => {
    mount()
    const overview = screen.getByTestId('cert-overview')
    expect(within(overview).getByText('n5.example.com')).toBeInTheDocument()
    expect(within(overview).queryByText('n6.example.com')).toBeNull()
    fireEvent.click(within(overview).getByRole('button', { name: 'inspector.cert.moreNames:2' }))
    expect(within(screen.getByTestId('cert-extensions')).getByText(/n7\.example\.com/)).toBeInTheDocument()
  })

  it('draws the chain root first and opens the issuing authority in the inspector', async () => {
    mocks.cas.getAll.mockResolvedValue({ data: [{ id: 31, refid: 'ca-1' }, { id: 32, refid: 'ca-2' }] })
    const { onOpen } = mount()
    const chain = screen.getByTestId('chain-mini')
    expect([...chain.querySelectorAll('li')].map((li) => li.textContent)).toEqual(['Root CA', 'Issuing CA', 'web.example.com'])
    fireEvent.click(within(chain).getByRole('button', { name: 'Issuing CA' }))
    await waitFor(() => expect(onOpen).toHaveBeenCalledWith('ca', 32))
  })

  it('names the issuing authority without a link for an account that cannot read authorities', () => {
    env.permissions = ['read:certificates']
    mount()
    expect(within(screen.getByTestId('chain-mini')).queryByRole('button')).toBeNull()
    expect(within(screen.getByTestId('chain-mini')).getByText('Issuing CA')).toBeInTheDocument()
  })

  it('offers to add the issuer to the trust store on an incomplete chain, to an account that may', async () => {
    const cert = { ...CERT, chain_status: { status: 'incomplete', chain: [] } }
    mocks.truststore.addFromCA.mockResolvedValue({})
    mocks.certificates.getById.mockResolvedValue({ data: { ...CERT, id: 7 } })
    const onChanged = vi.fn()
    mount({ certificate: cert, onChanged })
    fireEvent.click(screen.getAllByRole('tab')[1])
    fireEvent.click(screen.getByRole('button', { name: 'details.addIssuerToTrustStore' }))
    await waitFor(() => expect(mocks.truststore.addFromCA).toHaveBeenCalledWith('ca-2'))
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(expect.objectContaining({ id: 7 })))
  })

  it('does not offer the trust store to an account without write:truststore', () => {
    env.permissions = ['read:certificates', 'read:cas']
    mount({ certificate: { ...CERT, chain_status: { status: 'incomplete', chain: [] } } })
    fireEvent.click(screen.getAllByRole('tab')[1])
    expect(screen.getByTestId('chain-status')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'details.addIssuerToTrustStore' })).toBeNull()
  })

  it('shows the last ACME failure the work queue holds for one of its names', async () => {
    mocks.dashboard.getQueue.mockResolvedValue({ data: { items: [
      { kind: 'acme_order_failed', label: 'web.example.com', due_at: '2026-11-01T00:00:00Z', href_hint: '/acme?tab=history' },
    ] } })
    mount()
    const failure = await screen.findByTestId('last-failure')
    expect(mocks.dashboard.getQueue).toHaveBeenCalledWith(['acme_order_failed'])
    expect(failure).toHaveTextContent('inspector.failure.title')
    expect(failure).toHaveTextContent('overview.kind.acme_order_failed')
    expect(within(failure).getByRole('link', { name: 'inspector.failure.open' })).toHaveAttribute('href', '/acme?tab=history')
  })

  it('asks the queue nothing for a certificate that is not from ACME, nor without read:dashboard', async () => {
    mount({ certificate: { ...CERT, source: 'manual' } })
    env.permissions = ['read:certificates']
    mount()
    await waitFor(() => expect(screen.getAllByTestId('cert-overview')).toHaveLength(2))
    expect(mocks.dashboard.getQueue).not.toHaveBeenCalled()
    expect(screen.queryByTestId('last-failure')).toBeNull()
  })
})
