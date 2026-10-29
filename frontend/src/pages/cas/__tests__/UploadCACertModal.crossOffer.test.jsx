/**
 * A certificate that re-certifies the CA's key answers 409 cross_certificate_detected:
 * the modal offers to attach it as a cross-certificate instead (#400).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { UploadCACertModal } from '../UploadCACertModal'

const { showSuccess, showError, showWarning, uploadCertificate, importCa } = vi.hoisted(() => ({
  showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), uploadCertificate: vi.fn(), importCa: vi.fn(),
}))

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }))
vi.mock('../../../contexts', () => ({ useNotification: () => ({ showSuccess, showError, showWarning }) }))
vi.mock('../../../services', () => ({ casService: { uploadCertificate, import: importCa } }))
vi.mock('../../../components/Modal', () => ({
  Modal: ({ open, title, children }) => (open ? <div>{title}{children}</div> : null),
}))

const PEM = '-----BEGIN CERTIFICATE-----\nAA\n-----END CERTIFICATE-----'
// The 409 body the backend sends (problem+json with the legacy keys)
const refusal = (options) => {
  const message = "This certificate is a cross-certificate of this CA; installing it would replace the CA's own certificate, so it is refused"
  return Object.assign(new Error(message), {
    status: 409,
    data: {
      code: 409, error: true, status: 409, title: 'Conflict', type: 'about:blank', message, detail: message,
      instance: '/api/v2/cas/5/certificate',
      details: { ca_id: 5, code: 'cross_certificate_detected', options },
    },
  })
}

async function submit() {
  const onSuccess = vi.fn()
  render(<UploadCACertModal open onClose={vi.fn()} ca={{ id: 5, common_name: 'Root' }} onSuccess={onSuccess} />)
  fireEvent.change(screen.getByPlaceholderText('-----BEGIN CERTIFICATE-----'), { target: { value: PEM } })
  fireEvent.click(screen.getByText('cas.uploadCertificate'))
  await waitFor(() => expect(uploadCertificate).toHaveBeenCalled())
  return onSuccess
}

describe('UploadCACertModal cross-certificate offer', () => {
  beforeEach(() => vi.clearAllMocks())

  it('offers to attach on the cross-certificate 409 and attaches with cross_mode=attach', async () => {
    uploadCertificate.mockRejectedValue(refusal(['attach', 'replace']))
    importCa.mockResolvedValue({ data: { warnings: ['w'] } })
    const onSuccess = await submit()
    expect(showError).not.toHaveBeenCalled()
    fireEvent.click(await screen.findByText('crossCerts.attachAsCross'))
    await waitFor(() => expect(importCa).toHaveBeenCalled())
    const form = importCa.mock.calls[0][0]
    expect(form.get('cross_mode')).toBe('attach')
    expect(form.get('pem_content')).toBe(PEM)
    expect(showSuccess).toHaveBeenCalledWith('crossCerts.attached')
    expect(showWarning).toHaveBeenCalledWith('w')
    expect(onSuccess).toHaveBeenCalled()
  })

  it('offers to replace and resends the upload with cross_mode=replace', async () => {
    uploadCertificate.mockRejectedValueOnce(refusal(['attach', 'replace']))
    uploadCertificate.mockResolvedValueOnce({ data: {} })
    const onSuccess = await submit()
    expect(screen.getByText('crossCerts.replaceHint')).toBeTruthy()
    fireEvent.click(await screen.findByText('crossCerts.replaceCurrent'))
    await waitFor(() => expect(uploadCertificate).toHaveBeenCalledTimes(2))
    expect(uploadCertificate.mock.calls[1][1]).toMatchObject({ pemContent: PEM, crossMode: 'replace' })
    expect(importCa).not.toHaveBeenCalled()
    expect(showSuccess).toHaveBeenCalledWith('cas.certInstalled')
    expect(onSuccess).toHaveBeenCalled()
  })

  it('offers no replace button when the backend does not list it', async () => {
    uploadCertificate.mockRejectedValue(refusal(['attach']))
    await submit()
    expect(await screen.findByText('crossCerts.attachAsCross')).toBeTruthy()
    expect(screen.queryByText('crossCerts.replaceCurrent')).toBeNull()
  })

  it('shows the error of any other refusal and offers nothing', async () => {
    uploadCertificate.mockRejectedValue(Object.assign(new Error('nope'), { status: 400, data: {} }))
    await submit()
    await waitFor(() => expect(showError).toHaveBeenCalledWith('nope'))
    expect(screen.queryByText('crossCerts.attachAsCross')).toBeNull()
  })
})
