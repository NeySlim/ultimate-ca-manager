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
const refusal = (options) => Object.assign(new Error('cross-certificate refused'), {
  status: 409, data: { details: { code: 'cross_certificate_detected', options } },
})

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
    uploadCertificate.mockRejectedValue(refusal(['attach']))
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

  it('shows the error of any other refusal and offers nothing', async () => {
    uploadCertificate.mockRejectedValue(Object.assign(new Error('nope'), { status: 400, data: {} }))
    await submit()
    await waitFor(() => expect(showError).toHaveBeenCalledWith('nope'))
    expect(screen.queryByText('crossCerts.attachAsCross')).toBeNull()
  })
})
