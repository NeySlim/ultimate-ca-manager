/**
 * Certificate in the inspector: heading buttons and « ⋯ » menu, the five sections,
 * three columns under the list and one beside it, history and ACME failure by permission.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, opts) => (opts && typeof opts === 'object' && opts.count !== undefined ? `${key}:${opts.count}` : key), i18n: { language: 'en' } }),
  initReactI18next: { type: '3rdParty', init: () => {} },
  Trans: ({ children }) => children,
}))
const perm = vi.hoisted(() => ({ scopes: ['*'] }))
const fav = vi.hoisted(() => ({ toggle: vi.fn(), on: false }))
const svc = vi.hoisted(() => ({ logs: vi.fn(), orders: vi.fn(), cas: vi.fn(), addFromCA: vi.fn(), getById: vi.fn() }))
vi.mock('../../../../hooks', () => ({
  usePermission: () => ({
    hasPermission: (s) => perm.scopes.includes('*') || perm.scopes.includes(s),
    canWrite: (r) => perm.scopes.includes('*') || perm.scopes.includes(`write:${r}`),
  }),
}))
vi.mock('../../../../hooks/useFavorites', () => ({
  useFavorites: () => ({ isFavorite: () => fav.on, toggleFavorite: fav.toggle }),
}))
vi.mock('../../../../contexts', () => ({ useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn() }) }))
vi.mock('../../../../services', () => ({
  auditService: { getLogs: (...a) => svc.logs(...a) },
  casService: { getAll: (...a) => svc.cas(...a) },
  truststoreService: { addFromCA: (...a) => svc.addFromCA(...a) },
  certificatesService: { getById: (...a) => svc.getById(...a) },
}))
vi.mock('../../../../services/acme.service', () => ({ acmeService: { getClientOrders: (...a) => svc.orders(...a) } }))
vi.mock('../../../deploy/CertDeploySection', () => ({ CertDeploySection: () => null }))

import { CertificateDetail } from '../CertificateDetail'
import { DockPlacementContext } from '../../placement'

const DAY = 86400000
const at = (d) => new Date(Date.now() + d * DAY).toISOString()
const CERT = {
  id: 7, common_name: 'web.example.com', descr: 'Front door', status: 'valid', revoked: false, source: 'acme_client',
  valid_from: at(-100), valid_to: at(200), key_type: 'EC secp256r1', key_algorithm: 'EC', signature_algorithm: 'sha256WithRSAEncryption',
  serial_number: '0A:0B', has_private_key: true, caref: 'ca-1', issuer: 'CN=Issuing CA', created_at: at(-100),
  compliance: { grade: 'A', score: 90 },
  extensions: { subject_alt_names: { entries: [{ type: 'DNS', value: 'web.example.com' }] }, basic_constraints: { ca: false, critical: true } },
  chain_status: { status: 'complete', chain: [{ name: 'Issuing CA', type: 'managed_ca' }, { name: 'Root CA', type: 'managed_ca' }], trust_anchor: 'Root CA' },
  pem: '-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----',
}

const act = (id, extra = {}) => ({ id, label: `action.${id}`, onClick: vi.fn(), visible: true, ...extra })
const ACTIONS = () => [act('export'), act('rename'), act('renew'), act('uploadKey'), act('lint'), act('revoke', { danger: true }), act('delete', { danger: true }), act('hidden', { visible: false })]

function Harness({ placement = 'bottom', cert = CERT, actions = ACTIONS(), onOpenCa }) {
  const [section, setSection] = useState('overview')
  return (
    <MemoryRouter initialEntries={['/certificates']}>
      <Routes>
        <Route path="/certificates" element={(
          <DockPlacementContext.Provider value={placement}>
            <CertificateDetail cert={cert} objectKey="certificate:7" title={cert.common_name} actions={actions}
              section={section} onSection={setSection} onOpenCa={onOpenCa} />
          </DockPlacementContext.Provider>
        )} />
        <Route path="/audit" element={<AuditProbe />} />
      </Routes>
    </MemoryRouter>
  )
}

function AuditProbe() {
  const { search } = useLocation()
  return <p data-testid="audit-page">{search}</p>
}

const openMenu = () => {
  fireEvent.click(screen.getByTestId('inspector-more-actions'))
  return screen.getByRole('dialog', { name: 'inspector.cert.actionsTitle' })
}

beforeEach(() => {
  perm.scopes = ['*']
  fav.on = false
  fav.toggle.mockReset()
  svc.logs.mockReset().mockResolvedValue({ data: [] })
  svc.orders.mockReset().mockResolvedValue({ data: [] })
  svc.cas.mockReset().mockResolvedValue({ data: [{ id: 3, refid: 'ca-1', descr: 'Issuing CA' }, { id: 1, refid: 'ca-0', descr: 'Root CA' }] })
})

describe('CertificateDetail: heading', () => {
  it('shows the name, the state, Export and Renew as the main action', () => {
    const actions = ACTIONS()
    render(<Harness actions={actions} />)
    expect(screen.getByRole('heading', { level: 2, name: 'web.example.com' })).toBeInTheDocument()
    expect(screen.getByText('common.valid')).toBeInTheDocument()
    const exp = screen.getByRole('button', { name: 'action.export' })
    const renew = screen.getByRole('button', { name: 'action.renew' })
    expect(renew).toHaveClass('is-primary')
    expect(exp).not.toHaveClass('is-primary')
    fireEvent.click(renew)
    expect(actions[2].onClick).toHaveBeenCalled()
  })

  it('makes Export the main action when there is nothing to renew', () => {
    render(<Harness actions={ACTIONS().filter((a) => a.id !== 'renew')} />)
    expect(screen.getByRole('button', { name: 'action.export' })).toHaveClass('is-primary')
    expect(screen.queryByRole('button', { name: 'action.renew' })).toBeNull()
  })

  it('lists the mockup actions first, then the product ones, deletion last, in a dialog', () => {
    const actions = ACTIONS()
    render(<Harness actions={actions} />)
    const trigger = screen.getByTestId('inspector-more-actions')
    expect(trigger).toHaveAttribute('aria-haspopup', 'dialog')
    const dialog = openMenu()
    const items = within(dialog).getAllByRole('button').filter((b) => !b.closest('.lv-dialog-head')).map((i) => i.textContent)
    expect(items).toEqual(['inspector.cert.copyName', 'inspector.cert.viewActivity', 'inspector.cert.revokeAction',
      'action.lint', 'action.uploadKey', 'action.rename', 'inspector.cert.favorite', 'action.delete'])
    expect(within(dialog).getByRole('button', { name: 'inspector.cert.revokeAction' })).toHaveClass('is-danger')
    expect(within(dialog).getByRole('button', { name: 'action.delete' })).toHaveClass('is-danger')
    fireEvent.click(within(dialog).getByRole('button', { name: 'inspector.cert.revokeAction' }))
    expect(actions[5].onClick).toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('toggles the favorite from the dialog', () => {
    fav.on = true
    render(<Harness />)
    fireEvent.click(within(openMenu()).getByRole('button', { name: 'inspector.cert.unfavorite' }))
    expect(fav.toggle).toHaveBeenCalledWith(expect.objectContaining({ id: 7, name: 'web.example.com' }))
  })

  it('copies the common name', async () => {
    const writeText = vi.fn().mockResolvedValue()
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    render(<Harness />)
    fireEvent.click(within(openMenu()).getByRole('button', { name: 'inspector.cert.copyName' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('web.example.com'))
  })

  it('opens the audit log on this certificate, for a user who may read it', () => {
    render(<Harness />)
    fireEvent.click(within(openMenu()).getByRole('button', { name: 'inspector.cert.viewActivity' }))
    expect(screen.getByTestId('audit-page')).toHaveTextContent('?search=web.example.com')
  })

  it('offers no activity without read:audit, and no revoke the actions do not give', () => {
    perm.scopes = ['read:certificates']
    render(<Harness actions={ACTIONS().filter((a) => a.id !== 'revoke')} />)
    const dialog = openMenu()
    expect(within(dialog).queryByRole('button', { name: 'inspector.cert.viewActivity' })).toBeNull()
    expect(within(dialog).queryByRole('button', { name: 'inspector.cert.revokeAction' })).toBeNull()
  })

  it('offers to trust the issuing CA of an incomplete chain, before deletion', () => {
    render(<Harness cert={{ ...CERT, chain_status: { status: 'incomplete', chain: [{ name: 'Issuing CA', type: 'managed_ca' }] } }} />)
    const items = within(openMenu()).getAllByRole('button').map((i) => i.textContent)
    expect(items.slice(-2)).toEqual(['details.addIssuerToTrustStore', 'action.delete'])
  })
})

describe('CertificateDetail: sections', () => {
  it('has Overview, Chain, Extensions, History and PEM as tabs, PEM last', () => {
    render(<Harness />)
    const tabs = screen.getAllByRole('tab').map((t) => t.textContent)
    expect(tabs).toEqual(['inspector.sections.overview', 'inspector.sections.chain', 'inspector.sections.extensions', 'inspector.sections.history', 'inspector.sections.pem'])
    expect(screen.getByRole('tab', { name: 'inspector.sections.overview' })).toHaveAttribute('aria-selected', 'true')
  })

  it('lays the overview out in three columns under the list and one beside it', () => {
    const { unmount } = render(<Harness placement="bottom" />)
    expect(screen.getByTestId('certificate-overview')).toHaveAttribute('data-columns', '3')
    unmount()
    render(<Harness placement="right" />)
    expect(screen.getByTestId('certificate-overview')).toHaveAttribute('data-columns', '1')
  })

  it('shows the validity, the identity and the chain mini-tree', () => {
    render(<Harness />)
    const overview = screen.getByTestId('certificate-overview')
    expect(overview).toHaveTextContent('inspector.cert.days:200')
    expect(overview).toHaveTextContent('ECDSA P-256')
    expect(overview).toHaveTextContent('0A:0B')
    const tree = overview.querySelector('.ins-chain-mini')
    expect([...tree.querySelectorAll('li')].map((li) => li.textContent)).toEqual(['Root CA', 'Issuing CA', 'web.example.com'])
  })

  it('opens the issuing CA from the chain when the user may read the CAs', async () => {
    const onOpenCa = vi.fn()
    render(<Harness onOpenCa={onOpenCa} />)
    fireEvent.click(screen.getByRole('button', { name: 'Issuing CA' }))
    await waitFor(() => expect(onOpenCa).toHaveBeenCalledWith(3))
  })

  it('shows plain names to a user who cannot read the CAs', () => {
    perm.scopes = ['read:certificates']
    render(<Harness onOpenCa={vi.fn()} />)
    expect(screen.queryByRole('button', { name: 'Issuing CA' })).toBeNull()
    expect(screen.getByText('Issuing CA')).toBeInTheDocument()
  })

  it('shows the chain boxes, the extensions and the PEM in their tabs', () => {
    render(<Harness />)
    fireEvent.click(screen.getByRole('tab', { name: 'inspector.sections.chain' }))
    expect(screen.getByTestId('certificate-chain').querySelectorAll('.ins-chain-box')).toHaveLength(3)
    fireEvent.click(screen.getByRole('tab', { name: 'inspector.sections.extensions' }))
    expect(screen.getByText('DNS: web.example.com')).toBeInTheDocument()
    expect(screen.getByText(/2\.5\.29\.19/)).toHaveTextContent('inspector.cert.critical')
    fireEvent.click(screen.getByRole('tab', { name: 'inspector.sections.pem' }))
    expect(screen.getByText(/BEGIN CERTIFICATE/)).toBeInTheDocument()
  })
})

describe('CertificateDetail: history', () => {
  it('reads the audit entries of this certificate for a user who may', async () => {
    svc.logs.mockResolvedValue({ data: [
      { id: 1, resource_id: 7, resource_type: 'certificate', action: 'certificate_exported', timestamp: at(-2), username: 'ops' },
      { id: 2, resource_id: 9, resource_type: 'certificate', action: 'certificate_deleted', timestamp: at(-1), username: 'x' },
    ] })
    render(<Harness />)
    fireEvent.click(screen.getByRole('tab', { name: 'inspector.sections.history' }))
    const history = screen.getByTestId('certificate-history')
    // One sentence per action, never the raw action name
    await waitFor(() => expect(history).toHaveTextContent('inspector.history.exported'))
    expect(history).not.toHaveTextContent('certificate_exported')
    expect(history).not.toHaveTextContent('inspector.history.deleted')
    expect(history).toHaveTextContent('inspector.history.issued')
    expect(history).toHaveTextContent('inspector.history.scope:100')
    expect(svc.logs).toHaveBeenCalledWith({ resource_type: 'certificate', per_page: 100 })
  })

  it('says the audit log is out of reach, and keeps the record dates, without read:audit', () => {
    perm.scopes = ['read:certificates']
    render(<Harness />)
    fireEvent.click(screen.getByRole('tab', { name: 'inspector.sections.history' }))
    const history = screen.getByTestId('certificate-history')
    expect(history).toHaveTextContent('inspector.history.noAudit')
    expect(history).toHaveTextContent('inspector.history.issued')
    expect(svc.logs).not.toHaveBeenCalled()
  })
})

describe('CertificateDetail: ACME', () => {
  it('shows the last failure of UCM\'s ACME client for this certificate', async () => {
    svc.orders.mockResolvedValue({ data: [{ id: 12, certificate_id: 7, status: 'invalid', error_message: 'DNS problem: NXDOMAIN', last_error_at: at(-1), primary_domain: 'web.example.com' }] })
    render(<Harness />)
    const failure = await screen.findByTestId('acme-last-failure')
    expect(failure).toHaveTextContent('inspector.cert.lastFailure')
    expect(failure).toHaveTextContent('DNS problem: NXDOMAIN')
  })

  it('words the order as the mockup: its number, the challenge in capitals, the short time ago', async () => {
    svc.orders.mockResolvedValue({ data: [{ id: 4097, certificate_id: 7, status: 'invalid', error_message: 'DNS problem', last_error_at: at(-0.3), primary_domain: 'web.example.com', challenge_type: 'dns-01' }] })
    render(<Harness />)
    const failure = await screen.findByTestId('acme-last-failure')
    expect(failure.querySelector('.ins-muted')).toHaveTextContent(/^inspector\.cert\.order · web\.example\.com · DNS-01 · time\.compact\.hoursAgo:7$/)
  })

  it('asks nothing for a certificate of another source, or without read:acme', () => {
    render(<Harness cert={{ ...CERT, source: 'manual' }} />)
    expect(svc.orders).not.toHaveBeenCalled()
    perm.scopes = ['read:certificates']
    render(<Harness />)
    expect(svc.orders).not.toHaveBeenCalled()
    expect(screen.queryByTestId('acme-last-failure')).toBeNull()
  })
})

describe('CertificateDetail: validity of an expired or revoked certificate', () => {
  const validity = () => screen.getByRole('heading', { name: 'inspector.cert.validity' }).closest('section')

  it('says Expired in amber over an amber bar, with no notice', () => {
    render(<Harness cert={{ ...CERT, status: 'expired', valid_from: at(-400), valid_to: at(-40) }} />)
    const figure = within(validity()).getByText('common.expired')
    expect(figure).toHaveClass('is-warn')
    expect(figure).not.toHaveClass('is-bad')
    expect(validity().querySelector('.ins-progress')).toHaveClass('is-warn')
    expect(validity().querySelector('.ins-notice')).toBeNull()
  })

  it('says Revoked in the text colour while it has time left, with the amber notice and no icon', () => {
    render(<Harness cert={{ ...CERT, revoked: true, status: 'revoked', revoked_at: at(-3), revoke_reason: 'keyCompromise' }} />)
    const figure = within(validity()).getByText('common.revoked')
    expect(figure.className).toBe('')
    const notice = validity().querySelector('.ins-notice')
    expect(notice).toHaveTextContent(/^inspector\.cert\.revokedNotice$/)
    expect(notice).not.toHaveClass('is-bad')
    expect(notice.querySelector('svg')).toBeNull()
  })

  it('keeps the revocation date and reason under More details', () => {
    render(<Harness cert={{ ...CERT, revoked: true, status: 'revoked', revoked_at: at(-3), revoke_reason: 'keyCompromise' }} />)
    const more = document.querySelector('.ins-more')
    expect(within(more).getByText('details.revokedAt')).toBeInTheDocument()
    expect(within(more).getByText('revocation.reasonLabel').nextElementSibling).toHaveTextContent('revocation.reasons.keyCompromise')
  })
})
