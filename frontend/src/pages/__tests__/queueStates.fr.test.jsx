/**
 * The queue pages show request states in the user's language, and an unknown state as sent.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, configure } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import fr from '../../i18n/locales/fr.json'

// A loaded machine slows the first render past the default second
configure({ asyncUtilTimeout: 5000 })

const api = vi.hoisted(() => ({ get: vi.fn() }))
const lookup = (key) => key.split('.').reduce((node, part) => (node == null ? node : node[part]), fr)
// One translator and one notifier for every render: the pages reload when either changes
const stable = vi.hoisted(() => ({
  tr: null,
  i18n: { language: 'fr', changeLanguage: () => {}, on: () => {}, off: () => {} },
  notify: { showSuccess: () => {}, showError: () => {}, showInfo: () => {}, showWarning: () => {}, showConfirm: () => {}, showPrompt: () => {} },
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: stable.tr, i18n: stable.i18n }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: () => {} },
}))
stable.tr = (key, arg) => {
  const opts = typeof arg === 'object' && arg ? arg : {}
  const found = lookup(key)
  const text = typeof found === 'string' ? found : (typeof arg === 'string' ? arg : (opts.defaultValue ?? key))
  return text.replace(/\{\{(\w+)\}\}/g, (_, name) => opts[name])
}
vi.mock('../../contexts', () => ({
  useNotification: () => stable.notify,
  useMobile: () => ({ isMobile: false, isTablet: false, screenWidth: 1280, sidebarOpen: true, setSidebarOpen: () => {} }),
  useInspector: () => ({ openEntity: () => {}, windows: [], prefs: {}, updatePrefs: () => {} }),
}))
vi.mock('../../hooks', () => ({
  usePermission: () => ({ canWrite: () => true, canRead: () => true, canDelete: () => true, hasPermission: () => true }),
  useClipboard: () => ({ copy: () => {} }),
}))
vi.mock('../../hooks/useOpenEntity', () => ({ useOpenEntity: () => () => {} }))
vi.mock('../../services/apiClient', async (importActual) => ({
  ...(await importActual()),
  apiClient: { get: api.get, post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}))

import ApprovalsPage from '../ApprovalsPage'
import SCEPPage from '../SCEPPage'
import KeyRecoveryPage from '../KeyRecoveryPage'

const leaves = () => {
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
  const texts = []
  for (let node = walker.nextNode(); node; node = walker.nextNode()) texts.push(node.textContent)
  return texts
}
const ENGLISH = /\b(pending|approved|rejected|expired|issued|recovered|cancelled)\b/
const englishStates = () => leaves().filter((text) => ENGLISH.test(text))
const STATUSES = ['pending', 'approved', 'rejected', 'expired']

const approvals = STATUSES.map((status, i) => ({ id: i + 1, request_type: 'certificate', status, requester_username: `user${i}`, created_at: '2026-01-01T00:00:00Z' }))
const scep = [...STATUSES.slice(0, 3), 'issued'].map((status, i) => ({ id: i + 1, status, subject: `CN=dev${i}`, transaction_id: `txn${i}`, created_at: '2026-01-01T00:00:00Z' }))
const recoveries = ['pending', 'approved', 'rejected', 'recovered', 'cancelled', 'quarantined'].map((status, i) => ({ id: i + 1, status, cert_cn: `escrow${i}.example.com`, reason: 'r', requested_by: 'u', requested_at: '2026-01-01T00:00:00Z' }))

function answer(url) {
  const path = url.split('?')[0]
  if (path === '/approvals') return { data: approvals }
  if (path === '/approvals/stats' || path === '/scep/stats') return { data: { pending: 1, approved: 1, rejected: 1, total: 4 } }
  if (path === '/approvals/1') return { data: approvals[0] }
  if (path === '/scep/requests') return { data: scep }
  if (path === '/scep/requests/1') return { data: scep[0] }
  if (path === '/key-recovery') return { data: { requests: recoveries, dual_control: true } }
  if (path === '/scep/config') return { data: {} }
  return { data: [] }
}

beforeEach(() => { api.get.mockReset(); api.get.mockImplementation(async (url) => answer(url)) })

describe('request states in French', () => {
  it('approvals queue and history', async () => {
    render(<MemoryRouter initialEntries={['/approvals?request=1']}><ApprovalsPage /></MemoryRouter>)
    await screen.findByText('Traitées récemment')
    await waitFor(() => expect(leaves()).toEqual(expect.arrayContaining(['Refusée', 'Approuvée', 'Expirée'])))
    expect(englishStates()).toEqual([])
  })

  it('SCEP requests list and detail', async () => {
    render(<MemoryRouter initialEntries={['/scep-config?tab=requests&request=1']}><SCEPPage /></MemoryRouter>)
    await screen.findAllByText('txn0')
    await waitFor(() => expect(leaves()).toContain('Rejeté'))
    expect(englishStates()).toEqual([])
  })

  it('key recovery requests, an unknown state as sent', async () => {
    render(<MemoryRouter><KeyRecoveryPage /></MemoryRouter>)
    await waitFor(() => expect(leaves()).toContain('quarantined'))
    expect(englishStates()).toEqual([])
  })
})
