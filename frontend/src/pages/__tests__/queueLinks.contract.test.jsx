/**
 * Every work-queue link that carries an object opens that object on its page.
 * The table is contracts/queue_links.json; the backend test holds the server's hrefs to it.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, configure } from '@testing-library/react'
import { MemoryRouter, useNavigate } from 'react-router-dom'
import { act } from 'react'
import contract from '../../../../contracts/queue_links.json'

const api = vi.hoisted(() => ({ get: vi.fn() }))
const notify = vi.hoisted(() => ({
  showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(),
  showConfirm: vi.fn(), showPrompt: vi.fn(),
}))

const i18n = vi.hoisted(() => {
  const t = (key) => key
  return { t, i18n: { language: 'en', changeLanguage: () => {}, on: () => {}, off: () => {} } }
})
vi.mock('react-i18next', () => ({
  useTranslation: () => i18n,
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: () => {} },
}))
vi.mock('../../contexts', () => ({
  useNotification: () => notify,
  useMobile: () => ({ isMobile: false, isTablet: false, screenWidth: 1280, sidebarOpen: true, setSidebarOpen: () => {} }),
  useInspector: () => ({ openEntity: () => {}, windows: [], prefs: {}, updatePrefs: () => {} }),
}))
vi.mock('../../hooks', () => ({
  usePermission: () => ({ canWrite: () => true, canRead: () => true, canDelete: () => true, hasPermission: () => true }),
  useClipboard: () => ({ copy: () => {} }),
}))
vi.mock('../../hooks/useOpenEntity', () => ({ useOpenEntity: () => () => {} }))
vi.mock('../../components/CRLDeploySection', () => ({ CRLDeploySection: () => null }))
vi.mock('../../services/apiClient', async (importActual) => ({
  ...(await importActual()),
  apiClient: { get: api.get, post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}))

import ApprovalsPage from '../ApprovalsPage'
import SCEPPage from '../SCEPPage'
import KeyRecoveryPage from '../KeyRecoveryPage'
import CRLOCSPPage from '../CRLOCSPPage'
import ACMEPage from '../ACMEPage'

// A loaded machine slows the first render past the default second
configure({ asyncUtilTimeout: 5000 })

const ID = 7
const PAGES = {
  '/approvals': ApprovalsPage, '/scep-config': SCEPPage, '/key-recovery': KeyRecoveryPage,
  '/crl-ocsp': CRLOCSPPage, '/acme': ACMEPage,
}

// What the API holds for object 7, by the path the page must ask for, and what the open page then shows
const OBJECTS = {
  approval_pending: { path: '/approvals/7', body: { id: ID, request_type: 'certificate', status: 'pending', requester_username: 'linked-requester' }, shows: 'linked-requester' },
  scep_request_pending: { path: '/scep/requests/7', body: { id: ID, status: 'pending', subject: 'CN=linked-scep', transaction_id: 'txn-linked' }, shows: 'txn-linked' },
  key_recovery_pending: { path: '/key-recovery/7', body: { id: ID, status: 'pending', cert_cn: 'linked-escrow.example.com', reason: 'r' }, shows: 'linked-escrow.example.com' },
  acme_order_failed: { path: '/acme/orders/7', body: { id: ID, domain: 'linked-local.example.com', status: 'Invalid', account: 'a', method: 'DNS', expires: '2026-01-01' }, shows: 'linked-local.example.com' },
  acme_client_renewal_failed: { path: '/acme/client/orders/7', body: { id: ID, primary_domain: 'linked-client.example.com', status: 'valid', renewal_failures: 2 }, shows: 'linked-client.example.com' },
  crl_due: { path: null, label: 'crlOcsp.crlValidity' },
  crl_missing: { path: null, label: 'crlOcsp.crlValidity' },
}
const CA = { id: ID, name: 'linked-ca-name', descr: 'linked-ca-name', common_name: 'linked-ca-name', has_private_key: true }

function answer(url) {
  const path = url.split('?')[0]
  for (const o of Object.values(OBJECTS)) if (o.path === path) return { data: o.body }
  if (path === '/cas') return { data: [CA] }
  if (path === '/acme/orders') return { data: { items: [], meta: { page: 1, per_page: 50, total: 0 } } }
  if (path === '/key-recovery') return { data: { requests: [], dual_control: true } }
  if (path === '/approvals/stats' || path === '/scep/stats') return { data: { pending: 0, approved: 0, rejected: 0, total: 0 } }
  if (path === '/acme/settings' || path === '/acme/client/settings' || path === '/scep/config') return { data: {} }
  return { data: [] }
}

const linked = contract.links.filter((l) => l.param)

describe('work-queue links open their object', () => {
  beforeEach(() => { vi.clearAllMocks(); api.get.mockReset(); api.get.mockImplementation(async (url) => answer(url)) })

  it('covers every kind that carries an object on a page of this table', () => {
    for (const l of linked) expect(PAGES[l.route], l.kind).toBeTruthy()
  })

  it.each(linked.map((l) => [l.kind, l]))('%s', async (kind, link) => {
    const target = OBJECTS[kind]
    const Page = PAGES[link.route]
    render(<MemoryRouter initialEntries={[link.template.replace('{id}', String(ID))]}><Page /></MemoryRouter>)
    if (target.path) await waitFor(() => expect(api.get.mock.calls.some(([u]) => u.split('?')[0] === target.path)).toBe(true))
    if (target.label) expect(await screen.findByLabelText(target.label)).toBeInTheDocument()
    else expect((await screen.findAllByText(target.shows)).length).toBeGreaterThan(0)
  })

  it('keeps the e-mail link /approvals?id=N working', async () => {
    render(<MemoryRouter initialEntries={['/approvals?id=7']}><ApprovalsPage /></MemoryRouter>)
    expect((await screen.findAllByText('linked-requester')).length).toBeGreaterThan(0)
  })

  it.each([
    ['/approvals', ApprovalsPage, '/approvals/7', '?request=7'],
    ['/scep-config', SCEPPage, '/scep/requests/7', '?request=7'],
    ['/key-recovery', KeyRecoveryPage, '/key-recovery/7', '?request=7'],
    ['/acme', ACMEPage, '/acme/orders/7', '?tab=localorders&order=7'],
  ])('%s says an object that is gone is gone', async (route, Page, path, query) => {
    api.get.mockImplementation(async (url) => {
      if (url.split('?')[0] === path) throw Object.assign(new Error('not found'), { status: 404 })
      return answer(url)
    })
    render(<MemoryRouter initialEntries={[route + query]}><Page /></MemoryRouter>)
    await waitFor(() => expect(notify.showInfo).toHaveBeenCalledWith('overview.link.gone'))
  })

  it('says a request already handled is, and still shows it', async () => {
    const done = { ...OBJECTS.approval_pending.body, status: 'approved' }
    api.get.mockImplementation(async (url) => (url === '/approvals/7' ? { data: done } : answer(url)))
    render(<MemoryRouter initialEntries={['/approvals?request=7']}><ApprovalsPage /></MemoryRouter>)
    expect((await screen.findAllByText('linked-requester')).length).toBeGreaterThan(0)
    expect(notify.showInfo).toHaveBeenCalledWith('overview.link.handled')
  })

  it.each([
    ['acme_order_failed', '?tab=localorders&order=7'],
    ['acme_client_renewal_failed', '?tab=letsencryptorders&order=7'],
  ])('%s opens its tab when followed from the open /acme page', async (kind, query) => {
    let go
    const Nav = () => { go = useNavigate(); return null }
    render(<MemoryRouter initialEntries={['/acme']}><Nav /><ACMEPage /></MemoryRouter>)
    await waitFor(() => expect(go).toBeTruthy())
    await act(async () => { go('/acme' + query) })
    expect((await screen.findAllByText(OBJECTS[kind].shows)).length).toBeGreaterThan(0)
  })
})
