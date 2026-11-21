/**
 * Certificate tools on the mockup's sectioned form: a flat table of contents, one tool in its
 * frame with its name and sentence, its run as a settings test line, a link to ?tab= opening on
 * its tool, the result of the previous tool dropped on a switch, no save bar.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
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
  return {
    useTranslation: () => ({ t, i18n: { language: 'en' } }),
    Trans: ({ children }) => children,
    initReactI18next: { type: '3rdParty', init: () => {} },
  }
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

const open = (entry = '/tools') => render(<MemoryRouter initialEntries={[entry]}><CertificateToolsPage /></MemoryRouter>)

describe('certificate tools sections', () => {
  it('lists the five tools in a flat table of contents and shows the SSL checker first, without a save bar', () => {
    open()
    const toc = screen.getByRole('navigation', { name: en.tools.tocLabel })
    expect(toc).toHaveClass('settings-toc')
    expect(within(toc).getAllByRole('link').map((a) => a.getAttribute('href')))
      .toEqual(['/tools', '/tools?tab=csr-decoder', '/tools?tab=cert-decoder', '/tools?tab=key-matcher', '/tools?tab=converter'])
    expect(screen.getByRole('heading', { level: 2, name: en.tools.sslChecker })).toBeInTheDocument()
    expect(screen.getByText(en.tools.sslCheckerDesc)).toBeInTheDocument()
    expect(document.getElementById('settings-savebar')).toBeNull()
  })

  it('opens on the tool a link names', () => {
    open('/tools?tab=converter')
    expect(screen.getByRole('heading', { level: 2, name: en.tools.converter })).toBeInTheDocument()
    expect(within(screen.getByRole('navigation', { name: en.tools.tocLabel })).getByRole('link', { name: en.tools.converter }))
      .toHaveAttribute('aria-current', 'true')
    expect(screen.getByRole('heading', { level: 2, name: en.tools.converter })).toHaveFocus()
  })

  it('leaves the focus alone when no link names a tool', () => {
    open()
    expect(screen.getByRole('heading', { level: 2, name: en.tools.sslChecker })).not.toHaveFocus()
  })

  it('says under its title what the Modules menu says of it', () => {
    open()
    expect(screen.getByText(en.shell.moduleDesc.tools)).toBeInTheDocument()
  })

  it('runs a tool from a button on its own test line, not across the frame, open while writes are held', () => {
    open()
    const run = screen.getByRole('button', { name: en.tools.checkSSL })
    expect(run.parentElement).toHaveClass('settings-test')
    expect(run).not.toHaveAttribute('data-write')
    expect(run.parentElement).toHaveTextContent(en.tools.runHint)
    expect(screen.getByLabelText(en.common.portLabel).closest('.field')).toHaveClass('short')
  })

  it('says the outcome on the test line, then the details under it', async () => {
    decoded.data = { status: 'expired', is_ca: false, public_key: { type: 'RSA', size: 2048 }, subject: { commonName: 'a' }, issuer: { commonName: 'a' }, extensions: {} }
    open('/tools?tab=cert-decoder')
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '-----BEGIN-----' } })
    fireEvent.click(screen.getByText(en.tools.decodeCert))
    const line = await screen.findByRole('status')
    expect(line).toHaveClass('test-result', 'bad')
    expect(line).toHaveTextContent(`${en.common.expired} · ${en.tools.endEntityCertificate}`)
    const details = screen.getByRole('group', { name: en.common.certificateDetails })
    expect(within(details).getByText(en.common.keyType).tagName).toBe('DT')
    expect(within(details).getByText('RSA 2048')).toBeInTheDocument()
  })

  it('drops the result of the previous tool on a switch', async () => {
    decoded.data = { public_key: { type: 'RSA', size: 2048 }, subject: { commonName: 'a' }, issuer: { commonName: 'a' }, extensions: {} }
    open('/tools?tab=cert-decoder')
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '-----BEGIN-----' } })
    fireEvent.click(screen.getByText(en.tools.decodeCert))
    await screen.findAllByText(en.common.keyType)
    fireEvent.click(screen.getByRole('link', { name: en.tools.csrDecoder }))
    expect(screen.queryByText(en.common.keyType)).toBeNull()
    expect(screen.getByRole('heading', { level: 2, name: en.tools.csrDecoder })).toHaveFocus()
  })
})
