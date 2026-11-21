/**
 * The certificate and key picker in the mockup's form vocabulary: its source in a `.segmented` field,
 * the PEM in monospace textareas, the file as « Choisir un fichier… », what was read in a status line.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'en' } }),
}))
const post = vi.fn()
vi.mock('../../services', () => ({
  apiClient: { post: (...a) => post(...a) },
  certificatesService: { getAll: vi.fn().mockResolvedValue({ data: [], meta: { total: 0 } }), getById: vi.fn(), export: vi.fn() },
}))

import { CertificateInput } from '../CertificateInput'

const CERT = '-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----'
const file = (text, name) => { const f = new File([text], name); f.text = async () => text; return f }
const drawnByTheProduct = (root) => root.querySelector('[class*="space-y"],[class*="text-xs"],[class*="text-text"],[class*="rounded"],.ui-segmented,.ui-control,.ui-field')

describe('CertificateInput in the mockup\'s vocabulary', () => {
  beforeEach(() => post.mockReset())

  it('chooses its source with the segmented control and pastes PEM in monospace fields', () => {
    const onChange = vi.fn()
    const { container } = render(<div className="form-fields"><CertificateInput label="Client" keyLabel="Key" value={{ cert_pem: '', key_pem: '' }} onChange={onChange} /></div>)
    const group = screen.getByRole('group', { name: 'certInput.source' })
    expect(group).toHaveClass('segmented')
    expect(within(group).getByRole('button', { name: 'certInput.modePaste' })).toHaveAttribute('aria-pressed', 'true')
    const cert = screen.getByLabelText('Client')
    expect(cert).toHaveClass('mono')
    expect(cert.closest('.field')).toHaveClass('full')
    expect(screen.getByLabelText('Key')).toHaveClass('mono')
    fireEvent.change(cert, { target: { value: CERT } })
    expect(onChange).toHaveBeenCalledWith({ cert_pem: CERT, key_pem: '' })
    expect(drawnByTheProduct(container)).toBeNull()
  })

  it('reads a file chosen with the text link and says what it read, with the link that removes it', async () => {
    post.mockResolvedValue({ data: { objects: [{ type: 'certificate', is_ca: false, pem: CERT }] } })
    const onChange = vi.fn()
    const { container, rerender } = render(<CertificateInput value={{ cert_pem: '', key_pem: '' }} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: 'certInput.modeUpload' }))
    const pick = container.querySelector('label.text-link input[type="file"]')
    expect(pick).toHaveClass('sr-only')
    fireEvent.change(pick, { target: { files: [file(CERT, 'server.pem')] } })
    await waitFor(() => expect(onChange).toHaveBeenCalledWith({ cert_pem: CERT, key_pem: '' }))
    rerender(<CertificateInput value={{ cert_pem: CERT, key_pem: '' }} onChange={onChange} />)
    const status = await screen.findByRole('status')
    expect(status).toHaveTextContent('server.pem')
    expect(container.querySelector('pre.code-preview')).toHaveTextContent('BEGIN CERTIFICATE')
    fireEvent.click(screen.getByRole('button', { name: 'tools.removeFile' }))
    expect(onChange).toHaveBeenLastCalledWith({ cert_pem: '', key_pem: '' })
    expect(drawnByTheProduct(container)).toBeNull()
  })

  it('says a file it cannot read in the mockup\'s bad notice', async () => {
    post.mockResolvedValue({ data: { objects: [] } })
    const { container } = render(<CertificateInput value={{ cert_pem: '', key_pem: '' }} onChange={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'certInput.modeUpload' }))
    fireEvent.change(container.querySelector('input[type="file"]'), { target: { files: [file('junk', 'x.pem')] } })
    expect(await screen.findByRole('alert')).toHaveClass('notice', 'bad')
  })
})
