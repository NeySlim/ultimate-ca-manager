/**
 * CASide, the mockup's caSide() on the API's data: sections, links that select, revocation summary
 * (no fictive OCSP check), issue reasons on the real states (a root that holds its key issues),
 * the chain download, « Autres actions » with the permissions of each action, the field switches.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { ca } from './caFixtures'
import { buildForest } from '../caTree'

const t = (key, opts) => (opts && typeof opts.count === 'number' ? `${key}:${opts.count}` : opts?.name ? `${key} ${opts.name}` : opts?.level ? `${key} ${opts.level}` : key)
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t, i18n: { language: 'en' } }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: () => {} },
}))

const notify = vi.hoisted(() => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showConfirm: vi.fn(), showPrompt: vi.fn() }))
vi.mock('../../../contexts', () => ({ useNotification: () => notify, useMobile: () => ({ isMobile: false }) }))
vi.mock('../../../contexts/NotificationContext', () => ({ useNotification: () => notify }))
let granted = new Set()
vi.mock('../../../contexts/AuthContext', () => ({ useAuth: () => ({ permissions: [...granted], user: { id: 1 } }) }))

const api = vi.hoisted(() => ({
  getById: vi.fn(), update: vi.fn(), exportCA: vi.fn(), getForCA: vi.fn(), certs: vi.fn(),
}))
vi.mock('../../../services', () => ({
  casService: {
    getById: (...a) => api.getById(...a), update: (...a) => api.update(...a), export: (...a) => api.exportCA(...a),
    getCrossCertificates: () => Promise.resolve({ data: [] }), getChainUsage: () => Promise.resolve({ data: null }),
  },
  crlService: { getForCA: (...a) => api.getForCA(...a) },
  certificatesService: { getAll: (...a) => api.certs(...a) },
  systemService: { getComplianceProfiles: () => Promise.resolve({ data: [] }) },
  userCertificatesService: {},
  templatesService: { getForCA: () => Promise.resolve({ data: [] }) },
}))
const downloadExport = vi.fn().mockResolvedValue(null)
vi.mock('../../../lib/exportDownload', () => ({ downloadExport: (...a) => downloadExport(...a), sanitizeFilename: (n) => n }))

import { CASide } from '../CASide'

const SOON = new Date(Date.now() + 3 * 3600 * 1000).toISOString()
const LATER = new Date(Date.now() + 5 * 86400 * 1000).toISOString()
const family = () => [
  ca(1, { name: 'Root', has_private_key: true, ocsp_enabled: true, key_type: 'RSA 4096', path_length: 1 }),
  ca(2, { name: 'Issuing', type: 'intermediate', parent_id: 1, has_private_key: true, certs: 12, key_type: 'EC secp384r1' }),
  ca(3, { name: 'Leaf CA', type: 'intermediate', parent_id: 2, has_private_key: true }),
]
const Where = () => <output data-testid="where">{useLocation().pathname}{useLocation().search}</output>

function renderSide(id = 2, { cas = family(), ocsp = { enabled: true }, crossLinks = [], ...props } = {}) {
  const forest = buildForest(cas)
  const onPick = vi.fn()
  const onIssue = vi.fn()
  const utils = render(
    <MemoryRouter initialEntries={['/cas']}>
      <CASide ca={forest.byId.get(id)} cas={cas} forest={forest} crossLinks={crossLinks} ocsp={ocsp} onPick={onPick} onIssue={onIssue} {...props} />
      <Where />
    </MemoryRouter>,
  )
  return { onPick, onIssue, ...utils }
}
// A fact's row (its value, its action, its help), or the value of a plain dl.props pair
const row = (label) => { const dt = screen.getByText(label, { selector: 'dt' }); return dt.closest('.row') || dt.nextElementSibling }

beforeEach(() => {
  granted = new Set(['*'])
  for (const fn of Object.values(api)) fn.mockReset()
  for (const fn of Object.values(notify)) fn.mockReset()
  api.getById.mockImplementation((id) => Promise.resolve({ data: family().find((c) => c.id === id) }))
  api.getForCA.mockResolvedValue({ data: { crl_number: 1842, this_update: '2026-11-08T06:00:00Z', next_update: LATER, revoked_count: 2 } })
  api.certs.mockResolvedValue({ data: [], meta: { total: 3 } })
  downloadExport.mockClear()
})

describe('CASide: the mockup caSide()', () => {
  it('draws the head and the four sections of the mockup', async () => {
    const { container } = renderSide(2)
    const aside = container.querySelector('aside.panel.ca-side')
    expect(aside).toHaveAttribute('aria-labelledby', 'ca-side-title')
    expect(aside.querySelector('header.ca-side-head h2#ca-side-title')).toHaveTextContent('Issuing')
    expect([...aside.querySelectorAll(':scope > .kvg > section.ca-side-section > h3.section-title')].map((h) => h.textContent).slice(0, 4))
      .toEqual(['cas.side.identity', 'cas.side.key', 'cas.side.issuance', 'cas.side.revocation'])
    expect(row('cas.side.typeLevel')).toHaveTextContent('cas.side.intermediate · cas.tree.level 2')
    expect(row('pathLen')).toHaveTextContent('cas.side.pathLenNone')
    expect(row('cas.side.issued')).toHaveTextContent('12')
    await waitFor(() => expect(row('cas.side.revokedOf')).toHaveTextContent('3'))
    expect(api.certs).toHaveBeenCalledWith({ ca_id: 2, status: 'revoked', per_page: 1 })
  })

  it('names the authority in Identité, its description below, and renames it in the head (#459)', async () => {
    const renamed = { ...family()[1], name: 'Gateway Issuing', descr: 'Gateway Issuing', description: 'VPN only' }
    // The announced change reloads the detail: the server then answers with the renamed authority
    api.update.mockImplementation(async () => { api.getById.mockResolvedValue({ data: renamed }); return { data: renamed } })
    renderSide(2)
    const identity = screen.getByText('cas.side.identity').closest('section')
    expect(within(identity).getByText('cas.label.displayName', { selector: 'dt' }).nextElementSibling).toHaveTextContent('Issuing')
    expect(within(identity).getByText('cas.label.description', { selector: 'dt' })).toBeInTheDocument()
    fireEvent.click(within(row('cas.label.displayName')).getByRole('button', { name: 'cas.label.edit' }))
    const dialog = screen.getByRole('dialog')
    fireEvent.change(within(dialog).getByRole('textbox', { name: 'cas.label.displayName' }), { target: { value: 'Gateway Issuing' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'common.save' }))
    await waitFor(() => expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Gateway Issuing'))
    expect(api.update).toHaveBeenCalledWith(2, { name: 'Gateway Issuing', description: '' })
    expect(row('cas.label.description')).toHaveTextContent('VPN only')
  })

  it('selects the issuer and the sub-authorities from their links', () => {
    const { onPick } = renderSide(2)
    fireEvent.click(within(row('cas.side.issuer')).getByRole('button', { name: 'Root' }))
    expect(onPick).toHaveBeenCalledWith(1)
    fireEvent.click(within(row('cas.side.subAuthorities')).getByRole('button', { name: 'Leaf CA' }))
    expect(onPick).toHaveBeenCalledWith(3)
  })

  it('says a root is self-signed, and names who cross-certified it', () => {
    renderSide(1, { crossLinks: [{ from: 2, to: 1 }] })
    expect(row('cas.side.issuer')).toHaveTextContent('cas.side.selfSigned')
    expect(row('cas.side.issuer')).toHaveTextContent('cas.side.crossIssuedBy Issuing')
  })

  it('names the cross-certificates an authority issued', () => {
    const { onPick } = renderSide(2, { crossLinks: [{ from: 2, to: 1 }] })
    fireEvent.click(within(row('cas.side.crossIssued')).getByRole('button', { name: 'Root' }))
    expect(onPick).toHaveBeenCalledWith(1)
  })
})

describe('CASide: revocation', () => {
  it('reads the CRL of the authority and the configured responder, with no fictive last check', async () => {
    renderSide(1)
    await waitFor(() => expect(row('cas.side.crlNumber')).toHaveTextContent('1842'))
    expect(row('cas.side.ocsp').querySelector('.badge.good')).toHaveTextContent('cas.side.ocspActive')
    expect(screen.queryByText(/contrôle|lastCheck/i)).toBeNull()
    expect(screen.queryByText('cas.side.crlDue')).toBeNull()
  })

  it('calls the responder inactive when the authority or the service has it off', async () => {
    renderSide(2)
    expect(row('cas.side.ocsp').querySelector('.badge.muted')).toHaveTextContent('cas.side.ocspInactive')
    document.body.innerHTML = ''
    renderSide(1, { ocsp: { enabled: false } })
    expect(row('cas.side.ocsp').querySelector('.badge.muted')).toBeInTheDocument()
  })

  it('warns a day ahead of the next update, not only once the CRL is stale', async () => {
    api.getForCA.mockResolvedValue({ data: { crl_number: 7, this_update: '2026-11-08T06:00:00Z', next_update: SOON } })
    const { container } = renderSide(1)
    await waitFor(() => expect(container.querySelector('.notice.warn.crl-due')).toHaveTextContent('cas.side.crlDue'))
  })

  it('keeps the CRL published by a revoked authority without the warning', async () => {
    api.getForCA.mockResolvedValue({ data: { crl_number: 7, this_update: '2026-11-08T06:00:00Z', next_update: SOON } })
    const cas = family().map((c) => (c.id === 2 ? { ...c, status: 'Revoked', revoked: true } : c))
    api.getById.mockImplementation((id) => Promise.resolve({ data: cas.find((c) => c.id === id) }))
    const { container } = renderSide(2, { cas })
    await waitFor(() => expect(row('cas.side.crlNumber')).toHaveTextContent('7'))
    expect(container.querySelector('.crl-due')).toBeNull()
  })

  it('hides the section and the counts the reader may not read', () => {
    granted = new Set(['read:cas'])
    renderSide(2)
    expect(screen.queryByText('cas.side.revocation')).toBeNull()
    expect(api.getForCA).not.toHaveBeenCalled()
    expect(screen.queryByText('cas.side.revokedOf')).toBeNull()
    expect(screen.queryByRole('button', { name: 'cas.side.viewCertificates' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'cas.side.issueWith' })).toBeNull()
  })
})

describe('CASide: actions', () => {
  it('opens the certificates of the authority', () => {
    renderSide(2)
    fireEvent.click(screen.getByRole('button', { name: 'cas.side.viewCertificates' }))
    expect(screen.getByTestId('where').textContent).toBe('/certificates?ca_id=2')
  })

  it('lets a root that holds its key issue: roots are not always offline', () => {
    const { onIssue } = renderSide(1)
    const issue = screen.getByRole('button', { name: 'cas.side.issueWith' })
    expect(issue).toBeEnabled()
    fireEvent.click(issue)
    expect(onIssue).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }))
  })

  it.each([
    ['offline', { offline: true }, 'cas.side.blocked.offline'],
    ['without its key', { has_private_key: false }, 'cas.side.blocked.noKey'],
    ['revoked', { status: 'Revoked', revoked: true }, 'cas.side.blocked.revoked'],
    ['expired', { status: 'Expired', valid_to: '2020-01-01T00:00:00Z' }, 'cas.side.blocked.expired'],
    ['awaiting its certificate', { status: 'Pending', pending: true }, 'cas.side.blocked.pending'],
  ])('says why an authority %s cannot issue', (_name, over, reason) => {
    const cas = family().map((c) => (c.id === 2 ? { ...c, ...over } : c))
    api.getById.mockImplementation((id) => Promise.resolve({ data: cas.find((c) => c.id === id) }))
    renderSide(2, { cas })
    const issue = screen.getByRole('button', { name: 'cas.side.issueWith' })
    expect(issue).toBeDisabled()
    expect(issue).toHaveAttribute('aria-describedby', 'issue-blocked')
    expect(document.getElementById('issue-blocked')).toHaveTextContent(reason)
  })

  it('downloads the chain of the authority', async () => {
    api.exportCA.mockReturnValue('blob')
    renderSide(2)
    fireEvent.click(screen.getByRole('button', { name: 'cas.side.downloadChain' }))
    expect(api.exportCA).toHaveBeenCalledWith(2, 'pem', { includeChain: true })
    await waitFor(() => expect(downloadExport).toHaveBeenCalledWith('blob', { format: 'pem', name: 'Issuing-chain' }))
  })

  const menu = () => {
    fireEvent.click(screen.getByRole('button', { name: 'cas.side.moreActions' }))
    return screen.getByTestId('ca-actions-dialog')
  }

  it('gathers the other actions in the authority menu, revocation and deletion as dangers', () => {
    renderSide(2)
    const dialog = menu()
    const ids = within(dialog).getAllByRole('button').map((b) => b.dataset.action).filter(Boolean)
    expect(ids).toEqual(expect.arrayContaining(['export', 'pins', 'revoke', 'offline', 'delete']))
    expect(within(dialog).getByText('Issuing')).toBeInTheDocument()
    expect(dialog.querySelector('[data-action="delete"]')).toHaveClass('btn', 'danger')
    expect(dialog.querySelector('[data-action="export"]')).not.toHaveAttribute('data-write')
    expect(dialog.querySelector('[data-action="offline"]')).toHaveAttribute('data-write')
  })

  it('offers no revocation of a root (its parent revokes an authority)', () => {
    renderSide(1)
    expect(menu().querySelector('[data-action="revoke"]')).toBeNull()
  })

  it.each([
    [['read:cas', 'write:cas'], false],
    [['read:cas', 'write:templates'], false],
    [['read:cas', 'write:cas', 'write:templates'], true],
  ])('offers template pins with %j: %s', (scopes, shown) => {
    granted = new Set(scopes)
    renderSide(2)
    expect(!!menu().querySelector('[data-action="pins"]')).toBe(shown)
  })

  it('offers the deletion only with delete:cas', () => {
    granted = new Set(['read:cas', 'write:cas'])
    renderSide(2)
    expect(menu().querySelector('[data-action="delete"]')).toBeNull()
  })
})

describe('CASide: facts of the panel', () => {
  it('names the signature by its hash, as a certificate\'s, and the sections share one term column', async () => {
    api.getById.mockImplementation((id) => Promise.resolve({ data: { ...family().find((c) => c.id === id), signature_algorithm: 'sha256WithRSAEncryption' } }))
    const { container } = renderSide(2)
    await waitFor(() => expect(row('cas.side.signature').querySelector('dd.v')).toHaveTextContent(/^SHA-256$/))
    expect(container.querySelectorAll('.ca-side > .kvg > section.ca-side-section > dl.kv')).toHaveLength(4)
  })

  it('puts each switch apart from its value, folds the help, writes an absence and a state apart from a value', () => {
    renderSide(2)
    const pickers = row('cas.issuancePickers')
    expect(pickers.querySelector('dd.v')).toHaveTextContent(/^cas.issuanceListedState$/)
    expect(within(pickers.querySelector('dd.act')).getByRole('button', { name: 'cas.hideFromIssuance' })).toHaveAttribute('data-write', '')
    const unique = row('cas.uniqueSubject')
    expect(unique.querySelector('dd.v .badge.muted')).toHaveTextContent('cas.uniqueSubjectNotEnforced')
    expect(unique.querySelector('dd.help')).not.toBeVisible()
    expect(row('cas.complianceProfile').querySelector('dd.absent')).toHaveTextContent('cas.complianceProfileNone')
    expect(row('cas.side.ocsp').querySelector('dd.v .badge.muted')).toHaveTextContent('cas.side.ocspInactive')
  })

  it('copies the distribution point whole from its chip', async () => {
    const url = 'http://pki.example.org/cdp/7c1e2a40-55b3-4d9e-a1f6-0b8d3e9f2c11.crl'
    api.getById.mockImplementation((id) => Promise.resolve({ data: { ...family().find((c) => c.id === id), cdp_enabled: true, cdp_url: url } }))
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true })
    renderSide(2)
    const cdp = await waitFor(() => row('cas.side.cdp'))
    expect(cdp).toHaveClass('long', 'wide')
    fireEvent.click(within(cdp).getByRole('button', { name: 'protocols.copyValue cas.side.cdp' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(url))
  })
})

describe('CASide: switches of the product, as rows of the mockup', () => {
  it('switches an RSA authority to PSS after the confirmation', async () => {
    notify.showConfirm.mockResolvedValue(true)
    const pss = { ...family()[0], signature_scheme: 'pss' }
    api.update.mockImplementation(() => {
      api.getById.mockResolvedValue({ data: pss })
      return Promise.resolve({ data: pss })
    })
    renderSide(1)
    const scheme = row('cas.signatureScheme')
    expect(scheme).toHaveTextContent('cas.signatureSchemePkcs1v15')
    fireEvent.click(within(scheme).getByRole('button', { name: 'cas.signatureSchemeUsePss' }))
    await waitFor(() => expect(api.update).toHaveBeenCalledWith(1, { signatureScheme: 'pss' }))
    await waitFor(() => expect(row('cas.signatureScheme')).toHaveTextContent('cas.signatureSchemePss'))
  })

  it('changes nothing when the confirmation is declined', async () => {
    notify.showConfirm.mockResolvedValue(false)
    renderSide(1)
    fireEvent.click(within(row('cas.signatureScheme')).getByRole('button', { name: 'cas.signatureSchemeUsePss' }))
    await waitFor(() => expect(notify.showConfirm).toHaveBeenCalled())
    expect(api.update).not.toHaveBeenCalled()
  })

  it('offers no switch without write:cas, nor PSS on a key that cannot sign it', () => {
    granted = new Set(['read:cas'])
    renderSide(1)
    expect(within(row('cas.signatureScheme')).queryByRole('button')).toBeNull()
    document.body.innerHTML = ''
    granted = new Set(['*'])
    const cas = family().map((c) => (c.id === 1 ? { ...c, uses_hsm: true, hsm_provider_type: 'azure' } : c))
    api.getById.mockImplementation((id) => Promise.resolve({ data: cas.find((c) => c.id === id) }))
    renderSide(1, { cas })
    expect(within(row('cas.signatureScheme')).queryByRole('button')).toBeNull()
  })

  it('hides the authority from the issuance pickers', async () => {
    api.update.mockResolvedValue({ data: { ...family()[1], issuance_hidden: true } })
    renderSide(2)
    fireEvent.click(within(row('cas.issuancePickers')).getByRole('button', { name: 'cas.hideFromIssuance' }))
    await waitFor(() => expect(api.update).toHaveBeenCalledWith(2, { issuanceHidden: true }))
  })

  it('imports the missing key from the notice that says it is missing', () => {
    const cas = family().map((c) => (c.id === 2 ? { ...c, has_private_key: false, certificate_only: true } : c))
    api.getById.mockImplementation((id) => Promise.resolve({ data: cas.find((c) => c.id === id) }))
    const { container } = renderSide(2, { cas })
    const notice = [...container.querySelectorAll('.ca-side > p.notice')].find((p) => p.textContent.includes('cas.certificateOnlyBanner'))
    expect(within(notice).getByRole('button', { name: 'cas.importPrivateKey' })).toHaveAttribute('data-write')
  })
})
