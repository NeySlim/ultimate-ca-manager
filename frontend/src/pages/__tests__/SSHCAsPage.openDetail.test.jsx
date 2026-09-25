/**
 * SSHCAsPage: a CA just created or imported becomes the selected one (open-detail).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts && typeof opts.count === 'number' ? `${key}:${opts.count}` : key),
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
const importCA = vi.fn()
vi.mock('../../services', () => ({
  sshCasService: {
    getAll: (...args) => getAll(...args),
    create: (...args) => create(...args),
    importCA: (...args) => importCA(...args),
  },
}))

import SSHCAsPage from '../SSHCAsPage'

const EXISTING = [
  { id: 1, descr: 'Users CA', ca_type: 'user', key_type: 'ed25519', fingerprint: 'SHA256:aaa', cert_count: 2 },
]

const renderPage = () => render(<MemoryRouter><SSHCAsPage /></MemoryRouter>)

describe('SSHCAsPage — opening the CA just created or imported', () => {
  beforeEach(() => {
    window.localStorage.clear()
    getAll.mockReset()
    create.mockReset()
    importCA.mockReset()
    getAll.mockResolvedValue({ data: EXISTING })
  })

  it('selects the CA it has just created', async () => {
    create.mockResolvedValue({ data: { id: 99, descr: 'Created CA Alpha', ca_type: 'user', cert_count: 0 } })
    renderPage()
    await waitFor(() => expect(getAll).toHaveBeenCalled())

    fireEvent.click(screen.getByText('sshCas.createCA'))
    fireEvent.change(await screen.findByPlaceholderText('sshCas.modal.descriptionPlaceholder'), {
      target: { value: 'Created CA Alpha' },
    })
    const form = document.querySelector('form')
    fireEvent.click(form.querySelector('button[type="submit"]'))

    await waitFor(() => expect(create).toHaveBeenCalled())
    await waitFor(() => expect(screen.getAllByText('Created CA Alpha').length).toBeGreaterThan(0))
  })

  it('selects the CA it has just imported', async () => {
    importCA.mockResolvedValue({ data: { id: 100, descr: 'Imported CA Beta', ca_type: 'host', cert_count: 0 } })
    renderPage()
    await waitFor(() => expect(getAll).toHaveBeenCalled())

    fireEvent.click(screen.getByText('common.import'))
    const form = await screen.findByText('sshCas.importCADescription').then(el => el.closest('form'))
    fireEvent.change(form.querySelector('input[name="descr"]'), { target: { value: 'Imported CA Beta' } })
    fireEvent.change(form.querySelector('textarea'), { target: { value: 'PRIVATE KEY DATA' } })
    fireEvent.click(form.querySelector('button[type="submit"]'))

    await waitFor(() => expect(importCA).toHaveBeenCalled())
    await waitFor(() => expect(screen.getAllByText('Imported CA Beta').length).toBeGreaterThan(0))
  })
})
