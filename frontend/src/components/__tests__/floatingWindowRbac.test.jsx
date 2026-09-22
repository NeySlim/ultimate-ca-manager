/**
 * The floating window judges an entry by its own resource (DUP-FE-020).
 *
 * The window opens certificates, CAs, user certificates and trust store
 * entries, but derived the RBAC resource from only the first three:
 *
 *   const resource = isCA ? 'cas' : isUserCert ? 'user_certificates' : 'certificates'
 *
 * so a trust store entry fell through to 'certificates' and its Delete was
 * gated on delete:certificates. DELETE /api/v2/truststore/<id> requires
 * delete:truststore (backend/api/v2/truststore.py), and TrustStorePage gates
 * the very same call on canDelete('truststore'). The asymmetry cut both ways:
 * the window offered a delete the route would refuse, and hid one it would
 * accept, for the same row.
 *
 * The guard now also sits at the head of the handler, so a call site that
 * wires the button up anyway still cannot reach the API.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const authState = vi.hoisted(() => ({ permissions: [] }))
const truststoreMocks = vi.hoisted(() => ({
  getById: vi.fn(),
  delete: vi.fn(),
}))
const notify = vi.hoisted(() => ({
  showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(),
  showConfirm: vi.fn(), showPrompt: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, fallback) => (typeof fallback === 'string' ? fallback : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../contexts', () => ({
  useNotification: () => notify,
  useMobile: () => ({ isMobile: false, isTablet: false }),
}))

vi.mock('../../contexts/WindowManagerContext', () => ({
  useWindowManager: () => ({
    closeWindow: vi.fn(), focusWindow: vi.fn(), sameWindow: true,
    openWindow: vi.fn(), windows: [],
  }),
}))

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ permissions: authState.permissions }),
}))

vi.mock('../../services', () => ({
  certificatesService: { getById: vi.fn(), delete: vi.fn(), export: vi.fn() },
  casService: { getById: vi.fn(), delete: vi.fn(), export: vi.fn() },
  userCertificatesService: { getById: vi.fn(), delete: vi.fn(), export: vi.fn() },
  truststoreService: truststoreMocks,
}))

import { FloatingDetailWindow } from '../FloatingDetailWindow'

const ENTRY = {
  id: 9,
  name: 'Corporate Root',
  subject: 'CN=Corporate Root',
  purpose: 'tls',
}

const WINDOW = { id: 'w1', type: 'truststore', entityId: 9, defaultPos: { x: 0, y: 0 } }

const renderWindow = async () => {
  render(<FloatingDetailWindow windowInfo={WINDOW} />)
  await screen.findByText(ENTRY.name)
}

describe('deleting a trust store entry from the floating window', () => {
  beforeEach(() => {
    Object.values(notify).forEach(fn => fn.mockReset())
    truststoreMocks.getById.mockReset()
    truststoreMocks.delete.mockReset()
    truststoreMocks.getById.mockResolvedValue({ data: ENTRY })
    truststoreMocks.delete.mockResolvedValue({})
    notify.showConfirm.mockResolvedValue(true)
  })

  it('is not offered to a principal holding only delete:certificates', async () => {
    // The route asks for delete:truststore, so this could only ever 403.
    authState.permissions = ['read:truststore', 'delete:certificates']
    await renderWindow()
    expect(screen.queryByLabelText('common.delete')).toBeNull()
  })

  it('is offered to a principal holding delete:truststore', async () => {
    authState.permissions = ['read:truststore', 'delete:truststore']
    await renderWindow()
    expect(screen.getByLabelText('common.delete')).toBeInTheDocument()

    fireEvent.click(screen.getByLabelText('common.delete'))
    await waitFor(() => expect(truststoreMocks.delete).toHaveBeenCalledWith(9))
  })

  it('carries the guard at the head of the handler, not only on the button', () => {
    // ActionBar receives onDelete as a prop. A surface that wires the button up
    // regardless must still not be able to send the request, so the check lives
    // in the handler too rather than only in the JSX that offers it.
    const source = readFileSync(join(__dirname, '..', 'FloatingDetailWindow.jsx'), 'utf8')
    const start = source.indexOf('const handleDelete =')
    expect(start).toBeGreaterThan(-1)
    const body = source.slice(start, source.indexOf('const handleOffline', start))
    const guard = body.indexOf('canDelete(resource)')
    const call = body.indexOf('.delete(')
    expect(guard, 'handleDelete does not check canDelete(resource)').toBeGreaterThan(-1)
    expect(guard).toBeLessThan(call)
  })

  it('revokes a user certificate through its own route, with its own id', async () => {
    // windowInfo.entityId is the enrolment (AuthCertificate) id: the row comes
    // from auth_cert.to_dict() and exposes the Certificate id separately as
    // cert_id. Sending it to POST /certificates/<id>/revoke resolves it against
    // a different table, so an admin revoked an unrelated certificate.
    authState.permissions = ['read:user_certificates', 'write:user_certificates']
    const { userCertificatesService, certificatesService } = await import('../../services')
    userCertificatesService.getById.mockResolvedValue({
      data: { id: 11, name: 'alice@example.test', status: 'valid' },
    })
    userCertificatesService.revoke = vi.fn().mockResolvedValue({})
    certificatesService.revoke = vi.fn().mockResolvedValue({})

    render(<FloatingDetailWindow windowInfo={{ ...WINDOW, id: 'w3', type: 'user_certificate', entityId: 11 }} />)
    await screen.findAllByText('alice@example.test')
    fireEvent.click(screen.getByText('Revoke'))
    fireEvent.submit(await screen.findByText('revocation.confirm').then(el => el.closest('form')))

    await waitFor(() => expect(userCertificatesService.revoke).toHaveBeenCalledTimes(1))
    expect(userCertificatesService.revoke.mock.calls[0][0]).toBe(11)
    expect(certificatesService.revoke).not.toHaveBeenCalled()
  })

  it('still judges a certificate window by delete:certificates', async () => {
    authState.permissions = ['read:certificates', 'delete:certificates']
    const { certificatesService } = await import('../../services')
    certificatesService.getById.mockResolvedValue({ data: { id: 4, common_name: 'web.example.com' } })
    render(<FloatingDetailWindow windowInfo={{ ...WINDOW, id: 'w2', type: 'certificate', entityId: 4 }} />)
    await screen.findAllByText('web.example.com')
    expect(screen.getByLabelText('common.delete')).toBeInTheDocument()
  })
})

// One more row menu disagreed with its own detail panel. Reading the source is
// enough to catch the guard going away again.
//
// TemplatesPage used to be checked here the same way, against a `rowActions`
// callback the table was never given. The menu it built was never rendered, so
// the assertion could not fail for the reason that mattered; the guard that a
// user actually meets is the detail panel's, and it is asserted by rendering
// the page in pages/__tests__/TemplatesPage.systemCustom.test.jsx.
const readPage = (rel) => readFileSync(join(__dirname, '..', '..', 'pages', rel), 'utf8')

describe('row menus agree with the panel beside them', () => {
  it('gates the discovered-row delete on delete:certificates', () => {
    const source = readPage('DiscoveryPage.jsx')
    const marker = source.indexOf("setDeleteConfirm({ type: 'discovered'")
    expect(marker).toBeGreaterThan(-1)
    // DELETE /api/v2/discovery/<id> asks for delete:certificates, not write.
    const preceding = source.slice(Math.max(0, marker - 400), marker)
    expect(preceding).toContain("canDelete('certificates')")
    expect(preceding).not.toContain("canWrite('certificates') && (\n            <button")
  })
})
