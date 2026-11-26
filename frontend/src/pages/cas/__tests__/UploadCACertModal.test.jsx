/**
 * UploadCACertModal — a same-key renewal surfaces the superseded
 * certificate's serial with a revoke-at-your-external-root notice (#298);
 * a first activation shows no such notice.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { UploadCACertModal } from '../UploadCACertModal'
import { formatDate } from '../../../lib/utils'

const { showSuccess, showError, showWarning, uploadCertificate } = vi.hoisted(() => ({
  showSuccess: vi.fn(),
  showError: vi.fn(),
  showWarning: vi.fn(),
  uploadCertificate: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, vars) => (vars?.serial ? `${key}:${vars.serial}:${vars.date}` : key),
  }),
}))

vi.mock('../../../contexts', () => ({
  useNotification: () => ({ showSuccess, showError, showWarning }),
}))

vi.mock('../../../services', () => ({
  casService: { uploadCertificate },
}))

const CA = { id: 5, common_name: 'Ext CA' }

async function submitPem() {
  render(<UploadCACertModal open onClose={vi.fn()} ca={CA} onSuccess={vi.fn()} />)
  fireEvent.change(screen.getByPlaceholderText('-----BEGIN CERTIFICATE-----'), {
    target: { value: '-----BEGIN CERTIFICATE-----\nAA\n-----END CERTIFICATE-----' },
  })
  fireEvent.click(screen.getByText('cas.uploadCertificate'))
  await waitFor(() => expect(uploadCertificate).toHaveBeenCalled())
}

describe('UploadCACertModal superseded notice', () => {
  beforeEach(() => vi.clearAllMocks())

  it('warns with the superseded serial after a renewal upload', async () => {
    uploadCertificate.mockResolvedValue({
      data: {
        superseded_serial: '1a2b3c',
        superseded_valid_to: '2027-01-01T00:00:00+00:00',
        warnings: [],
      },
    })
    await submitPem()
    await waitFor(() => expect(showSuccess).toHaveBeenCalledWith('cas.certInstalled'))
    // The interface's date format and language, as every other date
    const expectedDate = formatDate('2027-01-01T00:00:00+00:00', { time: false })
    expect(showWarning).toHaveBeenCalledWith(
      `cas.certSupersededNotice:1a2b3c:${expectedDate}`
    )
  })

  it('shows no notice on first activation', async () => {
    uploadCertificate.mockResolvedValue({ data: { warnings: [] } })
    await submitPem()
    await waitFor(() => expect(showSuccess).toHaveBeenCalledWith('cas.certInstalled'))
    expect(showWarning).not.toHaveBeenCalled()
  })
})
