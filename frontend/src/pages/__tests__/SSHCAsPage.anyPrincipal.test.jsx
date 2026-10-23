/**
 * An SSH CA with no listed principal signs nothing unless the operator
 * explicitly allows any principal.
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
const getEffective = vi.fn()
vi.mock('../../services', () => ({
  sshCasService: { getAll: (...a) => getAll(...a), create: (...a) => create(...a), importCA: vi.fn() },
  policiesService: { getEffective: (...a) => getEffective(...a) },
}))

import SSHCAsPage from '../SSHCAsPage'

async function createCa() {
  render(<MemoryRouter><SSHCAsPage /></MemoryRouter>)
  await waitFor(() => expect(getAll).toHaveBeenCalled())
  fireEvent.click(screen.getAllByText('sshCas.createCA')[0])
  fireEvent.change(await screen.findByPlaceholderText('sshCas.modal.descriptionPlaceholder'), {
    target: { value: 'New SSH CA' },
  })
  await waitFor(() => expect(getEffective).toHaveBeenCalled())
  return document.querySelector('form')
}

describe('SSHCAsPage any-principal setting', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.clearAllMocks()
    getAll.mockResolvedValue({ data: [] })
    getEffective.mockResolvedValue({ data: { allowed_key_types: null } })
    create.mockResolvedValue({ data: { id: 7, descr: 'New SSH CA', ca_type: 'user', cert_count: 0 } })
  })

  it('creates a CA that signs nothing by default', async () => {
    const form = await createCa()
    fireEvent.click(form.querySelector('button[type="submit"]'))
    await waitFor(() => expect(create).toHaveBeenCalled())
    expect(create.mock.calls[0][0].allow_any_principal).toBe(false)
    expect(create.mock.calls[0][0].allowed_principals).toEqual([])
  })

  it('sends the explicit opt-in when ticked', async () => {
    const form = await createCa()
    fireEvent.click(screen.getByLabelText('sshCas.modal.allowAnyPrincipal'))
    fireEvent.click(form.querySelector('button[type="submit"]'))
    await waitFor(() => expect(create).toHaveBeenCalled())
    expect(create.mock.calls[0][0].allow_any_principal).toBe(true)
  })
})
