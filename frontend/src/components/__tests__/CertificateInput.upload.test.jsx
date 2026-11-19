/** CertificateInput upload: sends `content` to /import/analyze and reads the `pem` it returns. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key,
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

const post = vi.fn()
vi.mock('../../services', () => ({
  apiClient: { post: (...a) => post(...a) },
  certificatesService: { getAll: vi.fn(), getById: vi.fn(), export: vi.fn() },
}))

import { CertificateInput } from '../CertificateInput'

const CERT = '-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----'
const KEY = '-----BEGIN PRIVATE KEY-----\nBBBB\n-----END PRIVATE KEY-----'

// jsdom's File has no text() or arrayBuffer()
const makeFile = (parts, name) => {
  const file = new File(parts, name)
  const bytes = parts[0] instanceof Uint8Array ? parts[0] : new TextEncoder().encode(parts.join(''))
  file.text = async () => new TextDecoder().decode(bytes)
  file.arrayBuffer = async () => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength)
  return file
}

const upload = (container, file) => {
  fireEvent.click(screen.getByText('certInput.modeUpload'))
  fireEvent.change(container.querySelector('input[type="file"]'), { target: { files: [file] } })
}

describe('CertificateInput upload', () => {
  beforeEach(() => post.mockReset())

  it('sends the file as content and fills both fields from the returned pem', async () => {
    post.mockResolvedValue({ data: { objects: [
      { type: 'certificate', is_ca: false, pem: CERT },
      { type: 'private_key', pem: KEY },
    ] } })
    const onChange = vi.fn()
    const { container } = render(<CertificateInput value={{ cert_pem: '', key_pem: '' }} onChange={onChange} />)
    upload(container, makeFile([CERT + '\n' + KEY], 'both.pem'))
    await waitFor(() => expect(onChange).toHaveBeenCalledWith({ cert_pem: CERT, key_pem: KEY }))
    const [url, body] = post.mock.calls[0]
    expect(url).toBe('/import/analyze')
    expect(body).toEqual({ content: CERT + '\n' + KEY, include_pem: true })
    expect(body).not.toHaveProperty('files')
  })

  it('sends a binary file as base64 content with its password', async () => {
    post.mockResolvedValueOnce({ data: { objects: [] } })
    post.mockResolvedValueOnce({ data: { objects: [{ type: 'certificate', pem: CERT }, { type: 'private_key', pem: KEY }] } })
    const onChange = vi.fn()
    const { container } = render(<CertificateInput value={{ cert_pem: '', key_pem: '' }} onChange={onChange} />)
    upload(container, makeFile([new Uint8Array([48, 130, 1, 2])], 'bundle.p12'))
    const prompt = await screen.findByPlaceholderText('certInput.enterPassword')
    expect(post.mock.calls[0][1].content).toBe(btoa(String.fromCharCode(48, 130, 1, 2)))
    fireEvent.change(prompt, { target: { value: 'pw' } })
    fireEvent.click(screen.getByText('common.ok'))
    await waitFor(() => expect(onChange).toHaveBeenCalledWith({ cert_pem: CERT, key_pem: KEY }))
    expect(post.mock.calls[1][1]).toMatchObject({ password: 'pw', include_pem: true })
  })

  it('asks for the password of a sealed key instead of storing it', async () => {
    post.mockResolvedValue({ data: { objects: [{ type: 'private_key', is_encrypted: true }] } })
    const onChange = vi.fn()
    const { container } = render(<CertificateInput value={{ cert_pem: '', key_pem: '' }} onChange={onChange} />)
    upload(container, makeFile(['-----BEGIN ENCRYPTED PRIVATE KEY-----'], 'k.key'))
    expect(await screen.findByPlaceholderText('certInput.enterPassword')).toBeInTheDocument()
    expect(onChange).not.toHaveBeenCalled()
  })
})
