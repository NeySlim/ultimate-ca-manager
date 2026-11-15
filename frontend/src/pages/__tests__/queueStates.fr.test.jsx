/**
 * The queue pages show request states in the user's language, and an unknown state as sent.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, configure } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import fr from '../../i18n/locales/fr.json'

const api = vi.hoisted(() => ({ get: vi.fn() }))
const lookup = (key) => key.split('.').reduce((node, part) => (node == null ? node : node[part]), fr)
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, arg) => {
      const opts = typeof arg === 'object' && arg ? arg : {}
      const found = lookup(key)
      const text = typeof found === 'string' ? found : (typeof arg === 'string' ? arg : (opts.defaultValue ?? key))
      return text.replace(/\{\{(\w+)\}\}/g, (_, name) => opts[name])
    },
    i18n: { language: 'fr', changeLanguage: () => {}, on: () => {}, off: () => {} },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: () => {} },
}))
vi.mock('../../contexts', () => ({
  useNotification: () => ({ showSuccess() {}, showError() {}, showInfo() {}, showWarning() {}, showConfirm() {}, showPrompt() {} }),
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

// A loaded machine slows the first render past the default second
configure({ asyncUtilTimeout: 5000 })

const leaves = () => [...document.body.querySelectorAll('*')].filter((e) => !e.children.length).map((e) => e.textContent)
const englishStates = () => leaves().filter((text) => ENGLISH.test(text))
const ENGLISH = /\b(pending|approved|rejected|expired|issued|recovered|cancelled)\b/
const STATUSES = ['pending', 'approved', 'rejected', 'expired']

const approvals = STATUSES.map((status, i) => ({ id: i + 1, request_type: 'certificate', status, requester_username: `user${i}`, created_at: '2026-01-01T00:00:00Z' }))
const scep = [...STATUSES.slice(0, 3), 'issued'].map((status, i) => ({ id: i + 1, status, subject: `CN=dev${i}`, transaction_id: `txn${i}`, created_at: '2026-01-01T00:00:00Z' }))
const recoveries = ['pending', 'approved', 'rejected', 'recovered', 'cancelled'].map((status, i) => ({ id: i + 1, status, cert_cn: `escrow${i}.example.com`, reason: 'r', requested_by: 'u', requested_at: '2026-01-01T00:00:00Z' }))

function answer(url) {
  const path = url.split('?')[0]
  if (path === '/approvals') return { data: approvals }
  if (path === '/approvals/stats' || path === '/scep/stats') return { data: { pending: 1, approved: 1, rejected: 1, total: 4 } }
  if (path === '/approvals/1') return { data: approvals[0] }
  if (path === '/scep/requests') return { data: scep }
  if (path === '/key-recovery') return { data: { requests: recoveries, dual_control: true } }
  if (path === '/scep/config') return { data: {} }
  return { data: [] }
}

beforeEach(() => { api.get.mockReset(); api.get.mockImplementation(async (url) => answer(url)) })

describe('request states in French', () => {
  it('approvals list and detail', async () => {
    render(<MemoryRouter initialEntries={['/approvals?request=1&status=all']}><ApprovalsPage /></MemoryRouter>)
    expect((await screen.findAllByText('user0')).length).toBeGreaterThan(0)
    await screen.findByText('Détails de la demande')
    await waitFor(() => expect(screen.queryByText(/Chargement/)).toBeNull())
    expect(englishStates()).toEqual([])
  })

  it('SCEP requests list and detail', async () => {
    api.get.mockImplementation(async (url) => (url.split('?')[0] === '/scep/requests/1' ? { data: scep[0] } : answer(url)))
    render(<MemoryRouter initialEntries={['/scep-config?tab=requests&request=1']}><SCEPPage /></MemoryRouter>)
    expect((await screen.findAllByText('dev0')).length).toBeGreaterThan(0)
    await screen.findAllByText('txn0')
    expect(englishStates()).toEqual([])
  })

  it('key recovery requests', async () => {
    render(<MemoryRouter><KeyRecoveryPage /></MemoryRouter>)
    expect((await screen.findAllByText('escrow0.example.com')).length).toBeGreaterThan(0)
    expect(englishStates()).toEqual([])
  })

  it('an unknown state reads as sent', async () => {
    api.get.mockImplementation(async (url) => (url.split('?')[0] === '/key-recovery'
      ? { data: { requests: [{ ...recoveries[0], status: 'quarantined' }], dual_control: true } } : answer(url)))
    render(<MemoryRouter><KeyRecoveryPage /></MemoryRouter>)
    expect((await screen.findAllByText('quarantined')).length).toBeGreaterThan(0)
  })
})
