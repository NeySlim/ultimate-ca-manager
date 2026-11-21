/**
 * ApprovalsPage: approving a request opens what it issued (certificate or CA),
 * with the outcome messages of each case; the queue names each request's type.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// Stable across renders: t and showError are loader dependencies, a fresh one reloads in a loop
const stable = vi.hoisted(() => ({
  i18n: {
    t: (key, opts) => (opts && typeof opts.count === 'number' ? `${key}:${opts.count}` : key),
    i18n: { language: 'en', changeLanguage: () => {}, on: () => {}, off: () => {} },
  },
  notify: {
    showSuccess: () => {}, showError: () => {}, showInfo: () => {}, showWarning: () => {},
  },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => stable.i18n,
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

let mockCanRead = true
const openEntity = vi.fn()

vi.mock('../../contexts', () => ({
  useNotification: () => stable.notify,
  useMobile: () => ({ isMobile: false, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
  useInspector: () => ({
    openEntity, activeKey: null, closeWindow: vi.fn(), windows: [],
    prefs: { sameWindow: true, closeOnNav: true }, updatePrefs: vi.fn(),
  }),
}))

vi.mock('../../hooks', () => ({
  usePermission: () => ({
    canWrite: () => true, canDelete: () => true, hasPermission: () => true,
    canRead: (resource) => (resource === 'certificates' || resource === 'cas') ? mockCanRead : true,
  }),
}))

const list = vi.fn()
const getStats = vi.fn()
const approve = vi.fn()
const reject = vi.fn()
const getById = vi.fn()
vi.mock('../../services', () => ({
  approvalsService: {
    list: (...args) => list(...args),
    getStats: (...args) => getStats(...args),
    approve: (...args) => approve(...args),
    reject: (...args) => reject(...args),
    getById: (...args) => getById(...args),
  },
}))

import ApprovalsPage from '../ApprovalsPage'

const REQUEST = { id: 1, request_type: 'certificate', status: 'pending', requester_username: 'alice', created_at: new Date().toISOString() }

const renderPage = () => render(<MemoryRouter><ApprovalsPage /></MemoryRouter>)

const clickApproveOrReject = async (label) => {
  await waitFor(() => expect(list).toHaveBeenCalled())
  // The row's button opens the confirmation; its own button decides
  fireEvent.click(await screen.findByRole('button', { name: `approvals.work.${label}Named` }))
  if (label === 'reject') {
    fireEvent.change(document.querySelector('#decision-reason'), { target: { value: 'Wrong profile' } })
  }
  fireEvent.click(await screen.findByTestId('decision-confirm'))
}

describe('ApprovalsPage — opening what an approval issued', () => {
  beforeEach(() => {
    mockCanRead = true
    openEntity.mockReset()
    list.mockReset(); getStats.mockReset(); approve.mockReset(); reject.mockReset()
    list.mockResolvedValue({ data: [REQUEST] })
    getStats.mockResolvedValue({ data: { pending: 1, approved: 0, rejected: 0, total: 1 } })
  })

  it('opens the issued certificate', async () => {
    approve.mockResolvedValue({ data: { certificate_issued: true, certificate: { id: 7 } } })
    renderPage()
    await clickApproveOrReject('approve')
    await waitFor(() => expect(approve).toHaveBeenCalled())
    await waitFor(() => expect(openEntity).toHaveBeenCalledWith('certificate', 7))
  })

  it('opens the issued intermediate CA', async () => {
    approve.mockResolvedValue({ data: { certificate_issued: true, certificate: { id: null, ca_id: 9 } } })
    renderPage()
    await clickApproveOrReject('approve')
    await waitFor(() => expect(approve).toHaveBeenCalled())
    await waitFor(() => expect(openEntity).toHaveBeenCalledWith('ca', 9))
  })

  it('opens nothing when the certificate was not issued', async () => {
    approve.mockResolvedValue({ data: { certificate_issued: false, issue_error: 'x' } })
    renderPage()
    await clickApproveOrReject('approve')
    await waitFor(() => expect(approve).toHaveBeenCalled())
    expect(openEntity).not.toHaveBeenCalled()
  })

  it('opens nothing when the request was closed instead of issued', async () => {
    approve.mockResolvedValue({ data: { request_closed: true, issue_error: 'x' } })
    renderPage()
    await clickApproveOrReject('approve')
    await waitFor(() => expect(approve).toHaveBeenCalled())
    expect(openEntity).not.toHaveBeenCalled()
  })

  it('reports an approval whose issuance waits for the client as a success', async () => {
    const showError = vi.spyOn(stable.notify, 'showError')
    const showSuccess = vi.spyOn(stable.notify, 'showSuccess')
    approve.mockResolvedValue({ data: { certificate_issued: false, deferred: true, status: 'approved' } })
    renderPage()
    await clickApproveOrReject('approve')
    await waitFor(() => expect(showSuccess).toHaveBeenCalledWith('approvals.work.toast.approvedOne'))
    expect(showError).not.toHaveBeenCalled()
    expect(openEntity).not.toHaveBeenCalled()
    showError.mockRestore(); showSuccess.mockRestore()
  })

  it.each([['acme_local_only', true], ['related_acme_local_only', 7], ['msca_local_only', true]])(
    'warns when an approved revocation stayed local (%s)', async (flag, value) => {
      const showWarning = vi.spyOn(stable.notify, 'showWarning')
      const showSuccess = vi.spyOn(stable.notify, 'showSuccess')
      approve.mockResolvedValue({ data: { certificate_issued: true,
        certificate: { id: 7, revoked: true, [flag]: value } } })
      renderPage()
      await clickApproveOrReject('approve')
      await waitFor(() => expect(showSuccess).toHaveBeenCalledWith('approvals.revocationPerformed'))
      expect(showWarning).toHaveBeenCalledWith('revocation.revokedLocallyOnly')
      showWarning.mockRestore(); showSuccess.mockRestore()
    })

  it('says of an owed revocation what the single route says', async () => {
    const showWarning = vi.spyOn(stable.notify, 'showWarning')
    const said = 'Certificate revoked in UCM, but the ACME CA did not confirm the revocation (HTTP 503); it is sent again automatically until the CA does.'
    approve.mockResolvedValue({ data: { certificate_issued: true, certificate: {
      id: 7, revoked: true, reason: 'keyCompromise', acme_local_only: true,
      acme_upstream_pending: true, acme_message: said } } })
    renderPage()
    await clickApproveOrReject('approve')
    await waitFor(() => expect(showWarning).toHaveBeenCalledWith(said))
    expect(showWarning).not.toHaveBeenCalledWith('revocation.revokedLocallyOnly')
    showWarning.mockRestore()
  })

  it('warns of nothing for an approved hold of an ACME certificate', async () => {
    const showWarning = vi.spyOn(stable.notify, 'showWarning')
    approve.mockResolvedValue({ data: { certificate_issued: true, certificate: {
      id: 7, revoked: true, reason: 'certificateHold', acme_local_only: true,
      acme_message: 'Certificate put on hold in UCM only' } } })
    renderPage()
    await clickApproveOrReject('approve')
    await waitFor(() => expect(openEntity).toHaveBeenCalled())
    expect(showWarning).not.toHaveBeenCalled()
    showWarning.mockRestore()
  })

  it('warns of nothing when the issuing CA was told of an approved revocation', async () => {
    const showWarning = vi.spyOn(stable.notify, 'showWarning')
    approve.mockResolvedValue({ data: { certificate_issued: true, certificate: {
      id: 7, revoked: true, acme_local_only: false, msca_local_only: false } } })
    renderPage()
    await clickApproveOrReject('approve')
    await waitFor(() => expect(approve).toHaveBeenCalled())
    await waitFor(() => expect(openEntity).toHaveBeenCalled())
    expect(showWarning).not.toHaveBeenCalled()
    showWarning.mockRestore()
  })

  it('opens nothing on reject', async () => {
    reject.mockResolvedValue({ data: {} })
    renderPage()
    await clickApproveOrReject('reject')
    await waitFor(() => expect(reject).toHaveBeenCalled())
    expect(openEntity).not.toHaveBeenCalled()
  })

  it('opens nothing when the approver lacks read:certificates', async () => {
    mockCanRead = false
    approve.mockResolvedValue({ data: { certificate_issued: true, certificate: { id: 7 } } })
    renderPage()
    await clickApproveOrReject('approve')
    await waitFor(() => expect(approve).toHaveBeenCalled())
    expect(openEntity).not.toHaveBeenCalled()
  })
})

describe('ApprovalsPage — what a request asks for', () => {
  beforeEach(() => { list.mockReset() })

  it('names a revocation, not the raw type', async () => {
    list.mockResolvedValue({ data: [{ ...REQUEST, id: 5, request_type: 'ca_revocation',
      request_summary: { cn: 'Issuing CA 2', target_ca_id: 3, reason: 'cACompromise' } }] })
    renderPage()
    expect(await screen.findByText(/Issuing CA 2$/)).toBeTruthy()
    expect(screen.getByRole('button', { name: /^approvals\.work\.what\.ca_revocation/ })).toBeTruthy()
    expect(screen.queryByText(/ca_revocation$/)).toBeNull()
  })

  it('names the protocol of a held enrolment in its pill', async () => {
    list.mockResolvedValue({ data: [{ ...REQUEST, id: 51, request_type: 'est_enroll', requester_username: 'est:basic:device',
      request_summary: { cn: 'device.example', protocol: 'est', operation: 'enroll', identity: 'basic:device' } }] })
    renderPage()
    expect(await screen.findByText(/device\.example$/)).toBeTruthy()
    expect(screen.getByText('approvals.work.kind')).toHaveClass('queue-kind')
    expect(screen.queryByText('est_enroll')).toBeNull()
  })

  it('reads every request at once and no statistics', async () => {
    list.mockResolvedValue({ data: [REQUEST] })
    renderPage()
    await waitFor(() => expect(list).toHaveBeenCalledWith('all'))
    expect(getStats).not.toHaveBeenCalled()
  })
})

describe('ApprovalsPage deep link', () => {
  it('opens the request named in the link in the dock, even when the list does not hold it', async () => {
    openEntity.mockReset()
    list.mockResolvedValue({ data: [] })
    const linked = { ...REQUEST, id: 42, request_summary: { cn: 'linked.example.com' } }
    getById.mockResolvedValue({ data: linked })
    render(<MemoryRouter initialEntries={['/approvals?id=42']}><ApprovalsPage /></MemoryRouter>)
    await waitFor(() => expect(getById).toHaveBeenCalledWith('42'))
    const dock = await screen.findByRole('complementary', { name: 'atelier.detailOf' })
    expect(within(dock).getByRole('heading', { level: 2, name: /linked\.example\.com$/ })).toBeTruthy()
    expect(openEntity).not.toHaveBeenCalled()
  })
})
