/**
 * The results of the SSL Checker and of the decoders in typed rows: a digest and a serial in chips that copy them
 * whole, a status a pill, a missing value an absence, the lists of names on long rows, no button beside a value.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import en from '../../i18n/locales/en.json'

const i18n = vi.hoisted(() => ({ en: null }))
vi.mock('react-i18next', () => {
  const lookup = (key) => key.split('.').reduce((node, part) => (node == null ? node : node[part]), i18n.en)
  const t = (key, opts) => {
    const vars = typeof opts === 'object' && opts ? opts : {}
    const template = lookup(key)
    if (typeof template !== 'string') return key
    return template.replace(/\{\{(\w+)\}\}/g, (_m, name) => (vars[name] ?? `{{${name}}}`))
  }
  return { useTranslation: () => ({ t, i18n: { language: 'en' } }), Trans: ({ children }) => children, initReactI18next: { type: '3rdParty', init: () => {} } }
})
i18n.en = en

vi.mock('../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn() }),
  useMobile: () => ({ isMobile: false, isTablet: false, isDesktop: true }),
}))
vi.mock('../../hooks', () => ({ useClipboard: () => ({ copy: vi.fn() }) }))

const decoded = vi.hoisted(() => ({ data: null }))
vi.mock('../../services', () => ({
  toolsService: {
    checkSsl: () => Promise.resolve({ data: decoded.data }),
    decodeCsr: () => Promise.resolve({ data: decoded.data }),
    decodeCert: () => Promise.resolve({ data: decoded.data }),
  },
}))

import CertificateToolsPage from '../CertificateToolsPage'

const SHA1 = '0F:1E:2D:3C:4B:5A:69:78:87:96:A5:B4:C3:D2:E1:F0:01:12:23:34'
const SHA256 = Array.from({ length: 32 }, (_, i) => (i * 7 + 16).toString(16).toUpperCase().padStart(2, '0').slice(-2)).join(':')
const CERT = {
  subject: { commonName: 'tool.example.com' }, issuer: { commonName: 'Tool CA' }, serial_number: 'ABC0123',
  version: 'v3', not_valid_before: '2026-01-01T00:00:00Z', not_valid_after: '2027-01-01T00:00:00Z', days_until_expiry: 0,
  signature_algorithm: 'SHA256-RSA', public_key: { type: 'RSA', size: 2048 },
  extensions: { subject_alt_names: ['DNS:tool.example.com', 'DNS:www.tool.example.com'] },
  fingerprints: { sha1: SHA1, sha256: SHA256 },
}
const row = (term) => [...document.querySelectorAll('dl.kv > div.row')].find((r) => r.querySelector('dt')?.textContent === term)
let writeText

async function decode(data) {
  writeText = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
  Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true })
  decoded.data = data
  render(<MemoryRouter><CertificateToolsPage /></MemoryRouter>)
  fireEvent.click(screen.getByRole('link', { name: en.tools.decoder }))
  fireEvent.change(screen.getByRole('textbox'), { target: { value: '-----BEGIN-----' } })
  fireEvent.click(screen.getByText(en.tools.decodeCert))
  await screen.findAllByText(en.common.keyType)
}

describe('certificate tools results', () => {
  it('reads a decoded certificate in typed rows', async () => {
    await decode(CERT)
    expect(document.querySelector('dl.props')).toBeNull()
    // the serial in octets, padded to whole bytes, copied as shown
    const serial = row(en.common.serialNumber)
    expect(serial.querySelector('dd.v .code-value.hex')).toHaveTextContent('0A:BC:01:23')
    const sha1 = row(en.tools.sha1)
    expect(sha1).toHaveClass('long')
    expect(sha1.querySelectorAll('.code-value.hex .line')).toHaveLength(2)
    fireEvent.click(sha1.querySelector('.code-value .cp'))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(SHA1))
    expect(row(en.common.subjectAltNames)).toHaveClass('long')
    // a missing organization is an absence; zero days left a value
    expect(row(en.common.organization).querySelector('dd')).toHaveClass('absent')
    expect(row(en.tools.daysLeft).querySelector('dd.v')).toHaveTextContent(/^0$/)
    const buttons = [...document.querySelectorAll('dl.kv dd.v button')]
    expect(buttons.length).toBeGreaterThan(0)
    expect(buttons.every((b) => b.closest('.code-value'))).toBe(true)
  })

  it('writes the result of a check as a pill and its digest in a chip', async () => {
    decoded.data = { ...CERT, status: 'valid', tls_version: 'TLSv1.3', cipher: { name: 'TLS_AES_256_GCM_SHA384' } }
    render(<MemoryRouter><CertificateToolsPage /></MemoryRouter>)
    fireEvent.change(screen.getByPlaceholderText(en.common.commonNamePlaceholder), { target: { value: 'tool.example.com' } })
    fireEvent.click(screen.getByText(en.tools.checkSSL))
    await screen.findAllByText(en.common.keyType)
    expect(row(en.common.status).querySelector('dd.v .badge.good')).toHaveTextContent('valid')
    expect(row(en.common.sha256).querySelectorAll('.code-value.hex .line')).toHaveLength(4)
    expect(row(en.common.commonName).querySelector('dd.v .code-value')).toHaveTextContent('tool.example.com')
  })
})
