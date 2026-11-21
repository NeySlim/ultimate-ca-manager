/**
 * The Certificates zone's inspector (the mockup's dockFrame() and inspector()): the certificates
 * open in the inspector as tabs, a certificate's heading, its actions menu (certMenu()), its
 * sections, and an authority or a trusted certificate opened in its own zone.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const env = vi.hoisted(() => ({ write: true, audit: true }))
const mocks = vi.hoisted(() => ({
  getById: vi.fn(), revoke: vi.fn(), getLogs: vi.fn(), cas: vi.fn(),
  notify: { showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showConfirm: vi.fn(), showPrompt: vi.fn() },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts && typeof opts === 'object' && (opts.name || opts.count !== undefined) ? `${key}:${opts.name ?? opts.count}` : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ i18nKey }) => i18nKey,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: false }) }))
vi.mock('../../../contexts/AuthContext', () => ({ useAuth: () => ({ isAuthenticated: true, permissions: ['*'] }) }))
vi.mock('../../../contexts/NotificationContext', () => ({ useNotification: () => mocks.notify }))
vi.mock('../../../hooks', async () => ({
  usePermission: () => ({
    canWrite: () => env.write, canDelete: () => env.write, canRead: () => true,
    hasPermission: (p) => (p === 'read:audit' ? env.audit : env.write),
  }),
}))
vi.mock('../../../services', () => ({
  certificatesService: { getById: (...a) => mocks.getById(...a), revoke: (...a) => mocks.revoke(...a), export: vi.fn() },
  casService: { getAll: (...a) => mocks.cas(...a), getById: vi.fn() },
  auditService: { getLogs: (...a) => mocks.getLogs(...a) },
  truststoreService: { addFromCA: vi.fn() },
  userCertificatesService: {}, approvalsService: {}, keyRecoveryService: {}, csrsService: {}, templatesService: {},
}))
vi.mock('../../../services/account.service', () => ({ accountService: { updatePreferences: vi.fn() } }))
vi.mock('../../../components/deploy/CertDeploySection', () => ({ CertDeploySection: () => <div data-testid="deploy" /> }))

import { InspectorProvider, useInspector } from '../../../contexts/InspectorContext'
import { Zone } from '../../../components/atelier'
import { CertificateInspector } from '../inspector/CertificateInspector'

const NOW = Date.now()
const iso = (days) => new Date(NOW + days * 86400000).toISOString()
const CERT = {
  id: 7, common_name: 'web.example.com', cn: 'web.example.com', descr: 'Front door', status: 'expiring', valid_from: iso(-345), valid_to: iso(20),
  issuer: 'CN=Issuing CA', issuer_name: 'Issuing CA', has_private_key: true, key_type: 'EC-P256', key_algorithm: 'EC-P256', signature_algorithm: 'sha256WithRSAEncryption',
  serial_number: '0A0B', source: 'manual', created_at: iso(-345), template_name: 'Serveur TLS', san_combined: 'web.example.com, www.example.com', pem: '-----BEGIN CERTIFICATE-----\nAA\n-----END CERTIFICATE-----',
  chain_status: { status: 'complete', chain: [{ name: 'Issuing CA', type: 'ca' }, { name: 'Root CA', type: 'ca' }] },
  extensions: { basic_constraints: { ca: false, critical: true } },
}
const OTHER = { ...CERT, id: 8, common_name: 'api.example.com', cn: 'api.example.com', revoked: true, status: 'revoked' }

function Opener() {
  const { openEntity } = useInspector()
  return (
    <>
      <button type="button" data-open="7" onClick={() => openEntity('certificate', 7)}>open-7</button>
      <button type="button" onClick={() => openEntity('certificate', 8)}>open-8</button>
      <button type="button" onClick={() => openEntity('truststore', 3)}>open-trusted</button>
    </>
  )
}
const Where = () => <output data-testid="where">{useLocation().pathname}</output>
const mount = () => render(
  <MemoryRouter initialEntries={['/certificates']}>
    <InspectorProvider>
      <Zone dock={<CertificateInspector />}><Opener /></Zone>
      <Where />
    </InspectorProvider>
  </MemoryRouter>,
)
const dock = () => document.getElementById('inspector')
const open = async (label, name) => {
  fireEvent.click(screen.getByText(label))
  if (name) await within(dock()).findByRole('heading', { name })
}

beforeEach(() => {
  window.localStorage.clear()
  Object.assign(env, { write: true, audit: true })
  mocks.getById.mockImplementation((id) => Promise.resolve({ data: id === 8 ? OTHER : CERT }))
  mocks.getLogs.mockReset()
  mocks.getLogs.mockResolvedValue({ data: [] })
  mocks.cas.mockResolvedValue({ data: [{ id: 3, refid: 'r3', common_name: 'Issuing CA', key_type: 'EC-P384' }] })
  Object.values(mocks.notify).forEach((f) => f.mockClear())
})

describe('the zone inspector frame (dockFrame)', () => {
  it('draws the mockup dock in the zone', async () => {
    mount()
    await open('open-7', 'web.example.com')
    expect(dock().closest('.atl')).not.toBeNull()
    expect(dock()).toHaveAttribute('aria-label', 'inspector.regionCertificate')
    expect(within(dock().querySelector('.open-tabs')).getByRole('button', { name: /web\.example\.com/, pressed: true })).toBeInTheDocument()
  })

  it('opens a second certificate as a tab, switches, and closes a tab by its own button', async () => {
    mount()
    await open('open-7', 'web.example.com')
    await open('open-8', 'api.example.com')
    const tabs = dock().querySelectorAll('.open-tab')
    expect(tabs).toHaveLength(2)
    fireEvent.click(tabs[0].querySelector('[data-active]'))
    await within(dock()).findByRole('heading', { name: 'web.example.com' })
    fireEvent.click(within(dock()).getByRole('button', { name: 'inspector.closeTab:api.example.com' }))
    await waitFor(() => expect(dock().querySelectorAll('.open-tab')).toHaveLength(1))
  })

  it('closes from its close button, the focus back on the row button', async () => {
    mount()
    screen.getByText('open-7').focus()
    await open('open-7', 'web.example.com')
    fireEvent.click(within(dock()).getByRole('button', { name: 'inspector.close' }))
    await waitFor(() => expect(dock()).toBeNull())
    await waitFor(() => expect(document.activeElement).toBe(screen.getByText('open-7')))
  })

  it('keeps its size in the user\'s inspector preference', async () => {
    mount()
    await open('open-7', 'web.example.com')
    fireEvent.click(within(dock()).getByRole('button', { name: 'inspector.grow' }))
    await waitFor(() => expect(JSON.parse(window.localStorage.getItem('ucm-inspector-prefs')).height).toBe(420))
    expect(dock().style.getPropertyValue('--dock')).toBe('420px')
  })

  it('sends a trusted certificate opened from here to the Trust Store, beside the open certificates', async () => {
    mount()
    await open('open-7', 'web.example.com')
    fireEvent.click(screen.getByText('open-trusted'))
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/truststore/3'))
    expect(dock().querySelectorAll('.open-tab')).toHaveLength(1)
  })
})

describe('a certificate in the inspector (inspector, certMenu)', () => {
  it('heads with the name, its state badge, Exporter, Renouveler and « ⋯ »', async () => {
    mount()
    await open('open-7', 'web.example.com')
    const heading = dock().querySelector('.dock-heading')
    expect(heading.querySelector('.badge.warn')).toHaveTextContent('certificates.views.expiring')
    const buttons = within(heading.querySelector('.actions')).getAllByRole('button')
    expect(buttons.map((b) => b.textContent || b.getAttribute('aria-label'))).toEqual(['export.title', 'common.renew', 'inspector.moreActions:web.example.com'])
    expect(buttons[0]).not.toHaveClass('primary')
    expect(buttons[1]).toHaveClass('btn', 'primary')
  })

  it('makes Exporter the main action of a revoked certificate, without Renouveler', async () => {
    mount()
    await open('open-8', 'api.example.com')
    const actions = dock().querySelector('.dock-heading .actions')
    expect(within(actions).queryByRole('button', { name: 'common.renew' })).toBeNull()
    expect(within(actions).getByRole('button', { name: 'export.title' })).toHaveClass('primary')
  })

  it('lists the mockup actions first, revoke in red, the product ones after, deletion last', async () => {
    mount()
    await open('open-7', 'web.example.com')
    fireEvent.click(within(dock()).getByRole('button', { name: 'inspector.moreActions:web.example.com' }))
    const dialog = await screen.findByTestId('inspector-actions-dialog')
    const items = within(dialog.querySelector('.columns-list')).getAllByRole('button')
    expect(items.slice(0, 3).map((b) => b.textContent)).toEqual(['inspector.cert.copyName', 'inspector.cert.viewActivity', 'inspector.cert.revokeAction'])
    expect(items[2]).toHaveClass('danger')
    expect(items.at(-1)).toHaveClass('danger')
    expect(items.at(-1)).toHaveTextContent('common.delete')
  })

  it('offers neither the activity without the audit right nor any write without the write right', async () => {
    env.audit = false
    env.write = false
    mount()
    await open('open-7', 'web.example.com')
    expect(within(dock()).queryByRole('button', { name: 'common.renew' })).toBeNull()
    fireEvent.click(within(dock()).getByRole('button', { name: 'inspector.moreActions:web.example.com' }))
    const dialog = await screen.findByTestId('inspector-actions-dialog')
    expect(within(dialog).queryByText('inspector.cert.viewActivity')).toBeNull()
    expect(within(dialog).queryByText('inspector.cert.revokeAction')).toBeNull()
    expect(within(dialog).queryByText('common.delete')).toBeNull()
  })

  it('says why a revoked certificate offers no renewal', async () => {
    mount()
    await open('open-8', 'api.example.com')
    fireEvent.click(within(dock()).getByRole('button', { name: 'inspector.moreActions:api.example.com' }))
    expect(await screen.findByText('inspector.cert.revokedMenuNote')).toBeInTheDocument()
  })

  it('revokes through the zone dialog: the reason goes to the server', async () => {
    mocks.revoke.mockResolvedValue({ data: {} })
    mount()
    await open('open-7', 'web.example.com')
    fireEvent.click(within(dock()).getByRole('button', { name: 'inspector.moreActions:web.example.com' }))
    fireEvent.click(within(await screen.findByTestId('inspector-actions-dialog')).getByText('inspector.cert.revokeAction'))
    const dialog = await screen.findByTestId('revoke-dialog')
    expect(dialog.querySelector('.notice.warn')).toHaveTextContent('revocation.notice')
    fireEvent.change(within(dialog).getByRole('combobox'), { target: { value: 'keyCompromise' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'revocation.confirm' }))
    await waitFor(() => expect(mocks.revoke).toHaveBeenCalledWith(7, 'keyCompromise', undefined))
  })

  it('goes through Aperçu, Chaîne, Extensions, Historique and PEM', async () => {
    mount()
    await open('open-7', 'web.example.com')
    const tabs = within(dock().querySelector('.detail-tabs')).getAllByRole('tab')
    expect(tabs.map((b) => b.id)).toEqual(['tab-overview', 'tab-chain', 'tab-extensions', 'tab-history', 'tab-pem'])
    const overview = dock().querySelector('.detail-overview')
    expect(overview.querySelectorAll(':scope > section')).toHaveLength(3)
    expect(overview.querySelector('.validity-head strong')).toHaveClass('warn')
    expect(overview.querySelector('.mini-notice')).toHaveTextContent('inspector.cert.renewSoon:20')
    expect(overview.querySelector('dl.props dd.mono')).toHaveTextContent('0A:0B')
    expect([...overview.querySelectorAll('.chain-mini li')].map((li) => li.textContent)).toEqual(['Root CA', 'Issuing CA', 'web.example.com'])
    fireEvent.click(tabs[1])
    expect(dock().querySelectorAll('.chain-box')).toHaveLength(3)
    expect(dock().querySelector('.chain-box.selected .badge.warn')).not.toBeNull()
    fireEvent.click(within(dock().querySelector('.detail-tabs')).getByRole('tab', { name: 'inspector.sections.extensions' }))
    expect(dock().querySelector('dl.extensions .extension')).toBeInTheDocument()
    fireEvent.click(within(dock().querySelector('.detail-tabs')).getByRole('tab', { name: 'inspector.sections.history' }))
    await waitFor(() => expect(dock().querySelector('ul.history-list li')).not.toBeNull())
    fireEvent.click(within(dock().querySelector('.detail-tabs')).getByRole('tab', { name: 'inspector.sections.pem' }))
    expect(dock().querySelector('pre.code-preview')).toHaveTextContent('BEGIN CERTIFICATE')
  })

  it('reads no journal without the audit right, and says so', async () => {
    env.audit = false
    mount()
    await open('open-7', 'web.example.com')
    fireEvent.click(within(dock().querySelector('.detail-tabs')).getByRole('tab', { name: 'inspector.sections.history' }))
    expect(await within(dock()).findByText('inspector.history.noAudit')).toBeInTheDocument()
    expect(mocks.getLogs).not.toHaveBeenCalled()
  })

  it('folds the product facts under « Plus de détails »', async () => {
    mount()
    await open('open-7', 'web.example.com')
    const toggle = within(dock()).getByRole('button', { name: /inspector\.cert\.moreDetails/ })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(document.getElementById(toggle.getAttribute('aria-controls'))).toHaveAttribute('hidden')
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    // The deployment section sits among the others, drawn as they are
    expect(screen.getByTestId('deploy').parentElement).toHaveClass('advanced-panel')
  })

  it('opens an authority of the chain in the authorities zone', async () => {
    mount()
    await open('open-7', 'web.example.com')
    fireEvent.click(within(dock().querySelector('.chain-mini')).getByRole('button', { name: 'Issuing CA' }))
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/cas/3'))
  })
})
