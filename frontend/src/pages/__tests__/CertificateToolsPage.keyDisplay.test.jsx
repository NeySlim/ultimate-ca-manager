/**
 * The SSL Checker and the decoders name a post-quantum key with its level and
 * no size; a classical key keeps its size or curve.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
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
vi.mock('../../components/ui/responsive', () => ({
  ResponsiveLayout: ({ children, tabs, onTabChange }) => (
    <div>
      {tabs.map(tab => <button key={tab.id} type="button" onClick={() => onTabChange(tab.id)}>tab-{tab.id}</button>)}
      {children}
    </div>
  ),
}))

const decoded = vi.hoisted(() => ({ data: null }))
vi.mock('../../services', () => ({
  toolsService: {
    checkSsl: () => Promise.resolve({ data: decoded.data }),
    decodeCsr: () => Promise.resolve({ data: decoded.data }),
    decodeCert: () => Promise.resolve({ data: decoded.data }),
  },
}))

import CertificateToolsPage from '../CertificateToolsPage'

const ML_DSA = { type: 'ML-DSA-65', security_level: 3 }
const SUBJECT = { commonName: 'tool.example.com' }

async function run(tool, publicKey) {
  decoded.data = { public_key: publicKey, subject: SUBJECT, issuer: SUBJECT, extensions: {} }
  render(<CertificateToolsPage />)
  if (tool === 'ssl-checker') {
    fireEvent.change(screen.getByPlaceholderText(en.common.commonNamePlaceholder), { target: { value: 'tool.example.com' } })
    fireEvent.click(screen.getByText(en.tools.checkSSL))
  } else {
    fireEvent.click(screen.getByText(`tab-${tool}`))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '-----BEGIN-----' } })
    fireEvent.click(screen.getByText(tool === 'csr-decoder' ? en.tools.decodeCsr : en.tools.decodeCert))
  }
  await screen.findAllByText(en.common.keyType)
}

describe('certificate tools key display', () => {
  it.each(['ssl-checker', 'csr-decoder', 'cert-decoder'])('%s names an ML-DSA key with its level, no size', async (tool) => {
    await run(tool, ML_DSA)
    expect(screen.getByText('ML-DSA-65 (level 3)')).toBeInTheDocument()
    expect(screen.queryByText(/-bit|undefined/)).toBeNull()
  })

  it('ssl-checker keeps the size of an RSA key', async () => {
    await run('ssl-checker', { type: 'RSA', size: 2048 })
    expect(screen.getByText('RSA 2048-bit')).toBeInTheDocument()
  })

  it.each(['csr-decoder', 'cert-decoder'])('%s keeps the curve of an EC key', async (tool) => {
    await run(tool, { type: 'EC', curve: 'secp384r1' })
    expect(screen.getByText('EC secp384r1')).toBeInTheDocument()
  })
})
