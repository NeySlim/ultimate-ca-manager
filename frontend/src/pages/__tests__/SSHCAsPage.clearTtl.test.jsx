/**
 * SSHCAsPage: emptying the default or maximum validity of a CA sends null, so the server clears it.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key,
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../contexts', () => ({
  useNotification: () => ({
    showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(),
    showConfirm: vi.fn().mockResolvedValue(false),
  }),
  useMobile: () => ({ isMobile: false, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
}))

vi.mock('../../hooks', async () => {
  const actual = await vi.importActual('../../hooks')
  return {
    ...actual,
    usePermission: () => ({
      canWrite: () => true, canDelete: () => true, hasPermission: () => true, canRead: () => true,
    }),
  }
})

const getAll = vi.fn()
const create = vi.fn()
const update = vi.fn()
const getEffective = vi.fn()
vi.mock('../../services', () => ({
  sshCasService: { getAll: (...a) => getAll(...a), create: (...a) => create(...a), update: (...a) => update(...a), importCA: vi.fn() },
  policiesService: { getEffective: (...a) => getEffective(...a) },
}))

import SSHCAsPage from '../SSHCAsPage'

const CA = {
  id: 1, descr: 'Users CA', ca_type: 'user', key_type: 'ed25519', fingerprint: 'SHA256:aaa',
  cert_count: 0, default_ttl: 28800, max_ttl: 86400, allowed_principals: [], default_extensions: [],
}

async function editCa() {
  render(<MemoryRouter><SSHCAsPage /></MemoryRouter>)
  await waitFor(() => expect(getAll).toHaveBeenCalled())
  fireEvent.click((await screen.findAllByText('Users CA'))[0])
  // Edit is in the panel's « ⋯ » menu
  fireEvent.click(await waitFor(() => { const b = document.querySelector('aside#inspector [data-ssh-ca-menu]'); expect(b).not.toBeNull(); return b }))
  fireEvent.click(await waitFor(() => { const b = document.querySelector('[data-action="cert-edit"]'); expect(b).not.toBeNull(); return b }))
  await waitFor(() => expect(getEffective).toHaveBeenCalled())
  return document.querySelector('form')
}

describe('SSHCAsPage durations', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.clearAllMocks()
    getAll.mockResolvedValue({ data: [CA] })
    getEffective.mockResolvedValue({ data: { allowed_key_types: null } })
    update.mockResolvedValue({ data: CA })
  })

  it('sends null for a field emptied on edit', async () => {
    const form = await editCa()
    const inputs = [...form.querySelectorAll('input')].filter((i) => i.value === '28800' || i.value === '86400')
    expect(inputs).toHaveLength(2)
    inputs.forEach((i) => fireEvent.change(i, { target: { value: '' } }))
    fireEvent.click(form.querySelector('button[type="submit"]'))
    await waitFor(() => expect(update).toHaveBeenCalled())
    const sent = update.mock.calls[0][1]
    expect(sent.default_ttl).toBeNull()
    expect(sent.max_ttl).toBeNull()
  })

  it('keeps a value that is still there', async () => {
    const form = await editCa()
    fireEvent.click(form.querySelector('button[type="submit"]'))
    await waitFor(() => expect(update).toHaveBeenCalled())
    expect(update.mock.calls[0][1].default_ttl).toBe(28800)
  })
})
