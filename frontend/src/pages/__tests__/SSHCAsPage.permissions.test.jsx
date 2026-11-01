/**
 * SSH CA actions follow the ssh_cas scopes, not the SSH certificate ones.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const authState = vi.hoisted(() => ({ permissions: [] }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key,
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

// One object for every render: a fresh one each time re-runs the page's load effect in a loop
const notify = vi.hoisted(() => ({
  showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(),
  showConfirm: vi.fn(() => Promise.resolve(false)),
}))

vi.mock('../../contexts', () => ({
  useNotification: () => notify,
  useMobile: () => ({ isMobile: false, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
}))

// usePermission reads `permissions` from AuthContext directly.
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ permissions: authState.permissions }),
}))

const getAll = vi.fn()
vi.mock('../../services', () => ({
  sshCasService: { getAll: (...a) => getAll(...a), create: vi.fn(), importCA: vi.fn() },
  policiesService: { getEffective: vi.fn().mockResolvedValue({ data: {} }) },
}))

import SSHCAsPage from '../SSHCAsPage'

async function renderPage(permissions) {
  authState.permissions = permissions
  render(<MemoryRouter><SSHCAsPage /></MemoryRouter>)
  await waitFor(() => expect(getAll).toHaveBeenCalled())
  await screen.findAllByText('sshCas.noData')
}

describe('SSHCAsPage permissions', () => {
  beforeEach(() => {
    window.localStorage.clear()
    getAll.mockReset()
    getAll.mockResolvedValue({ data: [] })
  })

  it('offers no create or import with the SSH certificate scopes alone', async () => {
    await renderPage(['read:ssh_cas', 'read:ssh', 'write:ssh', 'delete:ssh'])
    expect(screen.queryAllByText('sshCas.createCA')).toHaveLength(0)
    expect(screen.queryAllByText('common.import')).toHaveLength(0)
  })

  it('offers create and import with write:ssh_cas', async () => {
    await renderPage(['read:ssh_cas', 'write:ssh_cas'])
    expect(screen.getAllByText('sshCas.createCA').length).toBeGreaterThan(0)
    expect(screen.getAllByText('common.import').length).toBeGreaterThan(0)
  })
})
