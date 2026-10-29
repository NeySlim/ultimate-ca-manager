import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const mocks = vi.hoisted(() => ({
  getCrossCertificates: vi.fn(),
  attachCrossCertificate: vi.fn(),
  setCrossCertificateServed: vi.fn(),
  detachCrossCertificate: vi.fn(),
  exportCrossCertificate: vi.fn(),
  crossSign: vi.fn(),
  getAll: vi.fn(),
  showSuccess: vi.fn(),
  showError: vi.fn(),
  showWarning: vi.fn(),
  showConfirm: vi.fn(),
  downloadBlob: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, vars) => (vars?.issuer ? `${key}:${vars.issuer}` : key) }),
}))
vi.mock('../../../contexts', () => ({
  useNotification: () => ({
    showSuccess: mocks.showSuccess, showError: mocks.showError,
    showWarning: mocks.showWarning, showConfirm: mocks.showConfirm,
  }),
}))
vi.mock('../../../services', () => ({ casService: mocks }))
vi.mock('../../../lib/utils', async (orig) => ({ ...(await orig()), downloadBlob: mocks.downloadBlob }))
vi.mock('../../Modal', () => ({
  Modal: ({ open, children }) => (open ? <div role="dialog">{children}</div> : null),
}))

import { CrossCertificatesSection } from '../CrossCertificatesSection'

const ca = { id: 9, name: 'Root B', common_name: 'Root B' }
const row = (over = {}) => ({
  id: 3, ca_id: 9, issuer: 'CN=Root A,O=Acme', valid_from: '2026-01-01T00:00:00Z',
  valid_to: '2030-01-01T00:00:00Z', served: false, revoked: false, expired: false, not_yet_valid: false, ...over,
})

describe('CrossCertificatesSection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getCrossCertificates.mockResolvedValue({ data: [row()] })
    mocks.showConfirm.mockResolvedValue(true)
    mocks.setCrossCertificateServed.mockResolvedValue({ data: row({ served: true }) })
    mocks.detachCrossCertificate.mockResolvedValue({})
    mocks.attachCrossCertificate.mockResolvedValue({ data: { warnings: ['name constraints'] } })
    mocks.crossSign.mockResolvedValue({ data: { warnings: [] } })
  })

  it('lists the rows with their issuer and state', async () => {
    mocks.getCrossCertificates.mockResolvedValue({ data: [row({ served: true }), row({ id: 4, revoked: true })] })
    render(<CrossCertificatesSection ca={ca} canWrite />)
    expect(await screen.findAllByText('crossCerts.issuedBy:Root A')).toHaveLength(2)
    expect(screen.getByText('crossCerts.served')).toBeInTheDocument()
    expect(screen.getByText('crossCerts.state.revoked')).toBeInTheDocument()
  })

  it('shows nothing to a reader when there is none', async () => {
    mocks.getCrossCertificates.mockResolvedValue({ data: [] })
    const { container } = render(<CrossCertificatesSection ca={ca} canWrite={false} />)
    await waitFor(() => expect(mocks.getCrossCertificates).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })

  it('serves a cross-certificate, and refuses to serve a revoked one', async () => {
    mocks.getCrossCertificates.mockResolvedValue({ data: [row(), row({ id: 4, revoked: true })] })
    render(<CrossCertificatesSection ca={ca} canWrite />)
    const buttons = await screen.findAllByText('crossCerts.serve')
    expect(buttons[1].closest('button')).toBeDisabled()
    fireEvent.click(buttons[0])
    await waitFor(() => expect(mocks.setCrossCertificateServed).toHaveBeenCalledWith(9, 3, true))
  })

  it('detaches only after confirmation', async () => {
    render(<CrossCertificatesSection ca={ca} canWrite />)
    await screen.findByText('crossCerts.issuedBy:Root A')
    mocks.showConfirm.mockResolvedValueOnce(false)
    fireEvent.click(screen.getByLabelText('crossCerts.detach'))
    await waitFor(() => expect(mocks.showConfirm).toHaveBeenCalledTimes(1))
    expect(mocks.detachCrossCertificate).not.toHaveBeenCalled()
    fireEvent.click(screen.getByLabelText('crossCerts.detach'))
    await waitFor(() => expect(mocks.detachCrossCertificate).toHaveBeenCalledWith(9, 3))
  })

  it('exports the certificate as PEM', async () => {
    mocks.exportCrossCertificate.mockResolvedValue(new Blob(['x']))
    render(<CrossCertificatesSection ca={ca} canWrite={false} />)
    fireEvent.click(await screen.findByLabelText('export.title'))
    await waitFor(() => expect(mocks.exportCrossCertificate).toHaveBeenCalledWith(9, 3, 'pem'))
    expect(mocks.downloadBlob).toHaveBeenCalled()
  })

  it('hides the write actions from a reader', async () => {
    render(<CrossCertificatesSection ca={ca} canWrite={false} />)
    await screen.findByText('crossCerts.issuedBy:Root A')
    expect(screen.queryByLabelText('crossCerts.detach')).toBeNull()
    expect(screen.queryByText('crossCerts.sign')).toBeNull()
  })

  it('attaches a pasted certificate and relays the warnings', async () => {
    render(<CrossCertificatesSection ca={ca} canWrite />)
    fireEvent.click(await screen.findByText('crossCerts.attach'))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(dialog.querySelector('textarea'), { target: { value: ' -----BEGIN CERTIFICATE-----\nAA\n-----END CERTIFICATE----- ' } })
    fireEvent.click(dialog.querySelector('input[type=checkbox]'))
    fireEvent.submit(dialog.querySelector('form'))
    await waitFor(() => expect(mocks.attachCrossCertificate).toHaveBeenCalledWith(
      9, '-----BEGIN CERTIFICATE-----\nAA\n-----END CERTIFICATE-----', { served: true }))
    expect(mocks.showWarning).toHaveBeenCalledWith('name constraints')
  })

  it('cross-signs with a CA held in UCM that can sign', async () => {
    mocks.getAll.mockResolvedValue({ data: [
      { id: 1, name: 'Root A', status: 'Active', has_private_key: true, crt: 'x' },
      { id: 2, name: 'Keyless', status: 'Active', has_private_key: false, crt: 'x' },
      { id: 9, name: 'Root B', status: 'Active', has_private_key: true, crt: 'x' },
    ] })
    render(<CrossCertificatesSection ca={ca} canWrite />)
    fireEvent.click(await screen.findByText('crossCerts.sign'))
    const dialog = await screen.findByRole('dialog')
    await waitFor(() => expect(dialog.querySelectorAll('option')).toHaveLength(2))
    expect(dialog.textContent).not.toContain('Keyless')
    fireEvent.change(dialog.querySelector('select'), { target: { value: '1' } })
    fireEvent.change(dialog.querySelector('#cross-sign-days'), { target: { value: '90' } })
    fireEvent.submit(dialog.querySelector('form'))
    await waitFor(() => expect(mocks.crossSign).toHaveBeenCalledWith(
      1, { subjectCaId: 9, validityDays: 90, pathLength: undefined }))
  })
})
