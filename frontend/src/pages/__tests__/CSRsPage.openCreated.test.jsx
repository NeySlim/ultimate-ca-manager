/**
 * CSRsPage: a CSR/certificate just created is easy to find (#368).
 */
import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'

beforeAll(() => {
  global.ResizeObserver = global.ResizeObserver || class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture || (() => false)
  Element.prototype.setPointerCapture = Element.prototype.setPointerCapture || (() => {})
  Element.prototype.releasePointerCapture = Element.prototype.releasePointerCapture || (() => {})
  Element.prototype.scrollIntoView = Element.prototype.scrollIntoView || (() => {})
})

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts && typeof opts.count === 'number' ? `${key}:${opts.count}` : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

let mockIsMobile = false
const openWindow = vi.fn()
const navigate = vi.fn()

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => navigate }
})

vi.mock('../../contexts', () => ({
  useNotification: () => ({
    showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(),
    showConfirm: vi.fn().mockResolvedValue(false), showPrompt: vi.fn().mockResolvedValue(null),
  }),
  useMobile: () => ({
    isMobile: mockIsMobile, isTablet: false, isDesktop: !mockIsMobile, isTouch: false,
    isLargeScreen: !mockIsMobile, screenWidth: mockIsMobile ? 375 : 1440,
    sidebarOpen: true, setSidebarOpen: vi.fn(),
  }),
  useWindowManager: () => ({
    openWindow, closeWindow: vi.fn(), windows: [],
    prefs: { sameWindow: true, closeOnNav: true }, updatePrefs: vi.fn(),
  }),
}))

vi.mock('../../contexts/MobileContext', () => ({
  useMobile: () => ({
    isMobile: mockIsMobile, isTablet: false, isDesktop: !mockIsMobile, isTouch: false,
    isLargeScreen: !mockIsMobile, screenWidth: mockIsMobile ? 375 : 1440,
    sidebarOpen: true, setSidebarOpen: vi.fn(),
  }),
}))

vi.mock('../../hooks', async () => {
  const common = await vi.importActual('../../hooks/useCommon')
  return {
    useModals: common.useModals,
    usePermission: () => ({
      canWrite: () => true, canDelete: () => true, hasPermission: () => true, canRead: () => true,
    }),
  }
})

const getAll = vi.fn()
const getHistory = vi.fn()
const getById = vi.fn()
const upload = vi.fn()
const create = vi.fn()
const sign = vi.fn()
const signCSR = vi.fn()

vi.mock('../../services', () => ({
  csrsService: {
    getAll: (...a) => getAll(...a),
    getHistory: (...a) => getHistory(...a),
    getById: (...a) => getById(...a),
    upload: (...a) => upload(...a),
    create: (...a) => create(...a),
    sign: (...a) => sign(...a),
    delete: vi.fn().mockResolvedValue({ data: {} }),
    download: vi.fn(),
    downloadKey: vi.fn(),
    uploadKey: vi.fn(),
  },
  casService: {
    getAll: vi.fn().mockResolvedValue({ data: [
      { id: 1, refid: 'ca-1', descr: 'CA 1', has_private_key: true },
    ] }),
  },
  templatesService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  mscaService: {
    getEnabled: vi.fn().mockResolvedValue({ data: [] }),
    getTemplates: vi.fn().mockResolvedValue({ data: ['WebServer'] }),
    signCSR: (...a) => signCSR(...a),
  },
  ekuService: { getKnown: vi.fn().mockResolvedValue({ data: { ekus: [] } }) },
}))

vi.mock('../../components/SmartImport', () => ({
  SmartImportModal: ({ isOpen, onImportComplete }) =>
    isOpen ? <button onClick={() => onImportComplete(window.__importResult)}>do-import</button> : null,
}))

import CSRsPage from '../CSRsPage'

const PENDING_CSR = { id: 11, common_name: 'pending.example.com', cn: 'pending.example.com', has_private_key: false }

const renderPage = (initialEntries = ['/csrs']) => render(
  <MemoryRouter initialEntries={initialEntries}><CSRsPage /></MemoryRouter>
)

describe('CSRsPage — finding a new CSR/certificate (#368)', () => {
  beforeEach(() => {
    mockIsMobile = false
    openWindow.mockReset()
    navigate.mockReset()
    getAll.mockReset().mockResolvedValue({ data: [PENDING_CSR] })
    getHistory.mockReset().mockResolvedValue({ data: [] })
    getById.mockReset().mockResolvedValue({ data: { ...PENDING_CSR } })
    upload.mockReset()
    create.mockReset()
    sign.mockReset()
    signCSR.mockReset()
  })

  it('selects the CSR it has just generated', async () => {
    create.mockResolvedValue({ data: { id: 101, common_name: 'new-gen.example.com' } })
    getById.mockResolvedValueOnce({ data: { ...PENDING_CSR } })
      .mockResolvedValueOnce({ data: { id: 101, common_name: 'new-gen.example.com' } })
    renderPage()
    await waitFor(() => expect(getAll).toHaveBeenCalled())

    fireEvent.click(screen.getAllByText('csrs.generateCSR')[0])
    const cnInputs = await screen.findAllByPlaceholderText('example.com')
    fireEvent.change(cnInputs[0], { target: { value: 'new-gen.example.com' } })
    const genButtons = screen.getAllByText('csrs.generateCSR')
    fireEvent.click(genButtons[genButtons.length - 1])

    await waitFor(() => expect(create).toHaveBeenCalled())
    await waitFor(() => expect(getById).toHaveBeenCalledWith(101))
  })

  it('selects the CSR it has just uploaded (paste)', async () => {
    upload.mockResolvedValue({ data: { id: 102, common_name: 'pasted.example.com' } })
    getById.mockResolvedValueOnce({ data: { ...PENDING_CSR } })
      .mockResolvedValueOnce({ data: { id: 102, common_name: 'pasted.example.com' } })
    renderPage(['/csrs?action=upload'])
    await waitFor(() => expect(getAll).toHaveBeenCalled())

    fireEvent.click(await screen.findByText('csrs.pastePEM'))
    fireEvent.change(screen.getByPlaceholderText(/BEGIN CERTIFICATE REQUEST/), {
      target: { value: '-----BEGIN CERTIFICATE REQUEST-----\nfoo\n-----END CERTIFICATE REQUEST-----' },
    })
    fireEvent.click(screen.getByText('common.upload'))

    await waitFor(() => expect(upload).toHaveBeenCalled())
    await waitFor(() => expect(getById).toHaveBeenCalledWith(102))
  })

  const openSignModal = async () => {
    renderPage()
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    fireEvent.click(await screen.findByText('pending.example.com'))
    fireEvent.click(await screen.findByText('csrs.sign'))
    await screen.findByText('csrs.signCSRDescription')
  }


  const clickSignSubmit = () => {
    const dialog = screen.getByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'common.signCSR' }))
  }

  const selectCA = async (user) => {
    const dialog = screen.getByRole('dialog')
    const trigger = dialog.querySelectorAll('[role="combobox"]')[0]
    await user.click(trigger)
    await user.click(await screen.findByRole('option', { name: 'CA 1' }))
  }

  it('opens the certificate signed locally as a normal cert', async () => {
    const user = userEvent.setup()
    sign.mockResolvedValue({ data: { id: 201 } })
    await openSignModal()
    await selectCA(user)

    clickSignSubmit()
    await waitFor(() => expect(sign).toHaveBeenCalled())
    await waitFor(() => expect(openWindow).toHaveBeenCalledWith('certificate', 201))
  })

  it('opens the CA signed locally as an intermediate CA', async () => {
    const user = userEvent.setup()
    sign.mockResolvedValue({ data: { id: 202 } })
    await openSignModal()
    await selectCA(user)

    // Second combobox in the modal is the cert-type Select
    const typeTrigger = screen.getByRole('dialog').querySelectorAll('[role="combobox"]')[1]
    await user.click(typeTrigger)
    await user.click(await screen.findByRole('option', { name: 'certificates.certTypes.intermediateCA' }))

    clickSignSubmit()
    await waitFor(() => expect(sign).toHaveBeenCalled())
    await waitFor(() => expect(openWindow).toHaveBeenCalledWith('ca', 202))
  })

  it('opens nothing when local signing is queued for approval', async () => {
    const user = userEvent.setup()
    // id present too: an approval response could carry one; must still open nothing
    sign.mockResolvedValue({ data: { approval_required: true, policy_name: 'P', id: 999 } })
    await openSignModal()
    await selectCA(user)

    clickSignSubmit()
    await waitFor(() => expect(sign).toHaveBeenCalled())
    expect(openWindow).not.toHaveBeenCalled()
  })

  const openMscaSignModal = async () => {
    renderPage()
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    fireEvent.click(await screen.findByText('pending.example.com'))
    fireEvent.click(await screen.findByText('csrs.sign'))
    fireEvent.click(await screen.findByText('msca.signMicrosoft'))
  }

  it('opens the certificate when an MSCA signing comes back issued', async () => {
    const user = userEvent.setup()
    signCSR.mockResolvedValue({ data: { status: 'issued' } })
    // mscaConnections is loaded from getEnabled at loadData time — override for this test
    const { mscaService } = await import('../../services')
    mscaService.getEnabled.mockResolvedValue({ data: [
      { id: 5, name: 'MSCA1', server: 'srv.example.com', default_template: 'WebServer' },
    ] })

    await openMscaSignModal()
    const connTrigger = screen.getByRole('dialog').querySelectorAll('[role="combobox"]')[0]
    await user.click(connTrigger)
    await user.click(await screen.findByRole('option', { name: /MSCA1/ }))

    await waitFor(() => expect(within(screen.getByRole('dialog')).getByRole('button', { name: 'common.signCSR' })).not.toBeDisabled())
    clickSignSubmit()

    await waitFor(() => expect(signCSR).toHaveBeenCalled())
    await waitFor(() => expect(openWindow).toHaveBeenCalledWith('certificate', 11))
  })

  it('opens nothing when an MSCA signing comes back pending', async () => {
    const user = userEvent.setup()
    signCSR.mockResolvedValue({ data: { status: 'pending' } })
    const { mscaService } = await import('../../services')
    mscaService.getEnabled.mockResolvedValue({ data: [
      { id: 5, name: 'MSCA1', server: 'srv.example.com', default_template: 'WebServer' },
    ] })

    await openMscaSignModal()
    const connTrigger = screen.getByRole('dialog').querySelectorAll('[role="combobox"]')[0]
    await user.click(connTrigger)
    await user.click(await screen.findByRole('option', { name: /MSCA1/ }))

    await waitFor(() => expect(within(screen.getByRole('dialog')).getByRole('button', { name: 'common.signCSR' })).not.toBeDisabled())
    clickSignSubmit()

    await waitFor(() => expect(signCSR).toHaveBeenCalled())
    expect(openWindow).not.toHaveBeenCalled()
  })

  const openImport = () => {
    fireEvent.click(screen.getAllByText('common.import')[0])
  }

  it('smart import: exactly one CSR selects it', async () => {
    window.__importResult = { imported_ids: { csrs: [303] } }
    getById.mockResolvedValueOnce({ data: { ...PENDING_CSR } })
      .mockResolvedValueOnce({ data: { id: 303, common_name: 'imported.example.com' } })
    renderPage()
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    openImport()
    fireEvent.click(await screen.findByText('do-import'))
    await waitFor(() => expect(getById).toHaveBeenCalledWith(303))
  })

  it('smart import: exactly one certificate opens it', async () => {
    window.__importResult = { imported_ids: { certificates: [304] } }
    renderPage()
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    openImport()
    fireEvent.click(await screen.findByText('do-import'))
    await waitFor(() => expect(openWindow).toHaveBeenCalledWith('certificate', 304))
  })

  it('smart import: two objects opens nothing', async () => {
    window.__importResult = { imported_ids: { certificates: [305], cas: [306] } }
    renderPage()
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    openImport()
    fireEvent.click(await screen.findByText('do-import'))
    await waitFor(() => expect(getAll).toHaveBeenCalledTimes(2)) // reload after import
    expect(openWindow).not.toHaveBeenCalled()
    expect(getById).not.toHaveBeenCalledWith(305)
  })

  it('on mobile, signing locally navigates to the certificate route instead of opening a window', async () => {
    mockIsMobile = true
    const user = userEvent.setup()
    sign.mockResolvedValue({ data: { id: 401 } })
    renderPage()
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    // Mobile shows a tab menu first; "pending" opens the CSR list pane
    fireEvent.click((await screen.findAllByText('common.pending')).at(-1))
    fireEvent.click(await screen.findByText('pending.example.com'))
    fireEvent.click(await screen.findByText('csrs.sign'))
    await screen.findByText('csrs.signCSRDescription')
    await selectCA(user)

    clickSignSubmit()
    await waitFor(() => expect(sign).toHaveBeenCalled())
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/certificates/401'))
    expect(openWindow).not.toHaveBeenCalled()
  })
})
