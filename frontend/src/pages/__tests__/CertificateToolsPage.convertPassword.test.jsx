/**
 * The converter asks for a password as soon as a separate private key or an encrypted PEM
 * is given, and sends it.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import en from '../../i18n/locales/en.json'

const i18n = vi.hoisted(() => ({ en: null }))
const notify = vi.hoisted(() => ({ showError: vi.fn() }))
vi.mock('react-i18next', () => {
  const lookup = (key) => key.split('.').reduce((node, part) => (node == null ? node : node[part]), i18n.en)
  const t = (key, opts) => {
    const vars = typeof opts === 'object' && opts ? opts : {}
    const template = lookup(key)
    if (typeof template !== 'string') return key
    return template.replace(/\{\{(\w+)\}\}/g, (_m, name) => (vars[name] ?? `{{${name}}}`))
  }
  return {
    useTranslation: () => ({ t, i18n: { language: 'en' } }),
    Trans: ({ children }) => children,
    initReactI18next: { type: '3rdParty', init: () => {} },
  }
})
i18n.en = en

vi.mock('../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: notify.showError }),
  useMobile: () => ({ isMobile: false, isTablet: false, isDesktop: true }),
}))
vi.mock('../../hooks', () => ({ useClipboard: () => ({ copy: vi.fn() }) }))

// Radix Select renders its items in a portal; a native <select> exposes the same options
vi.mock('../../components/Select', () => ({
  SelectComponent: ({ label, options = [], value, onChange }) => (
    <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  ),
}))

const convert = vi.hoisted(() => vi.fn())
vi.mock('../../services', () => ({
  toolsService: { convert: (...a) => convert(...a) },
}))

import CertificateToolsPage from '../CertificateToolsPage'

const CERT = '-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----'
const SEALED = '-----BEGIN ENCRYPTED PRIVATE KEY-----\nBBBB\n-----END ENCRYPTED PRIVATE KEY-----'
const PLAIN_KEY = '-----BEGIN PRIVATE KEY-----\nBBBB\n-----END PRIVATE KEY-----'

const field = () => screen.queryByLabelText(new RegExp(en.tools.inputPassword))
const open = () => {
  render(<MemoryRouter><CertificateToolsPage /></MemoryRouter>)
  fireEvent.click(screen.getByRole('link', { name: en.tools.converter }))
  fireEvent.change(screen.getByPlaceholderText(/BEGIN CERTIFICATE/), { target: { value: CERT } })
}
const toPkcs12 = () => fireEvent.change(screen.getByLabelText(en.tools.outputFormat), { target: { value: 'pkcs12' } })
const pasteKey = (value) => fireEvent.change(screen.getByPlaceholderText('-----BEGIN PRIVATE KEY-----'), { target: { value } })
const run = () => fireEvent.click(screen.getAllByRole('button', { name: new RegExp(en.tools.convert, 'i') }).pop())

describe('converter password', () => {
  beforeEach(() => { convert.mockReset(); notify.showError.mockReset(); convert.mockResolvedValue({ data: {} }) })

  it('shows no password field for a plain certificate', () => {
    open()
    expect(field()).toBeNull()
  })

  it('shows an optional field once a separate key is pasted and sends the password', async () => {
    open()
    toPkcs12()
    fireEvent.change(screen.getByPlaceholderText(en.tools.passwordForP12), { target: { value: 'out-pw' } })
    pasteKey(PLAIN_KEY)
    expect(field()).not.toBeNull()
    expect(field()).not.toBeRequired()
    fireEvent.change(field(), { target: { value: 'pw-1' } })
    run()
    await waitFor(() => expect(convert).toHaveBeenCalled())
    expect(convert.mock.calls[0][0]).toMatchObject({ private_key: PLAIN_KEY, password: 'pw-1' })
  })

  it('requires the password for an encrypted PEM before calling the server', async () => {
    open()
    fireEvent.change(screen.getByPlaceholderText(/BEGIN CERTIFICATE/), { target: { value: CERT + '\n' + SEALED } })
    expect(field()).toBeRequired()
    run()
    await waitFor(() => expect(notify.showError).toHaveBeenCalled())
    expect(convert).not.toHaveBeenCalled()
    fireEvent.change(field(), { target: { value: 'pw-2' } })
    run()
    await waitFor(() => expect(convert).toHaveBeenCalled())
    expect(convert.mock.calls[0][0].password).toBe('pw-2')
  })
})
