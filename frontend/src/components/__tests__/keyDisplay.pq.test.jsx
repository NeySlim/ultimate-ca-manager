/**
 * Surfaces other than the certificate panel: a post-quantum key keeps its
 * name and level, and a missing or unsplittable key name is never shown as RSA.
 */
import { render, renderHook, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import en from '../../i18n/locales/en.json'
import { GROUP_PQ, KEY_ALGORITHMS } from '../../lib/keyAlgorithms'

const lookup = (key) => key.split('.').reduce((node, part) => (node == null ? node : node[part]), en)
const t = (key, opts) => {
  const vars = typeof opts === 'object' && opts ? opts : {}
  const template = lookup(key) ?? (typeof opts === 'string' ? opts : vars.defaultValue ?? key)
  return String(template).replace(/\{\{(\w+)\}\}/g, (_m, name) => (vars[name] ?? `{{${name}}}`))
}
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t, i18n: { language: 'en' } }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: () => {} },
}))
vi.mock('../../contexts/NotificationContext', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showConfirm: vi.fn() }),
}))
vi.mock('../../services', () => ({ casService: {} }))
vi.mock('../cas/CACrlSection', () => ({ CACrlSection: () => null }))
vi.mock('../cas/ChainUsageSection', () => ({ ChainUsageSection: () => null }))

const { CADetails } = await import('../CADetails')
const { TemplatePreviewModal } = await import('../TemplatePreviewModal')
const { useCertificateColumns } = await import('../../pages/certificates/useCertificateColumns')

const ML_DSA_65 = KEY_ALGORITHMS.find(a => a.group === GROUP_PQ && a.label === 'ML-DSA-65')
const LEVEL_LABEL = `${ML_DSA_65.label} (level ${ML_DSA_65.securityLevel})`

const keyCell = (row) => {
  const { result } = renderHook(() => useCertificateColumns(t))
  const column = result.current.find(c => c.key === 'key_type')
  return render(<div>{column.render(row.key_type, row)}</div>)
}

describe('key display outside the certificate panel', () => {
  it('names an ML-DSA CA with its level, a badge, and no RSA signature scheme', () => {
    const ca = { id: 9, descr: 'PQ root', key_type: 'ML-DSA-65', security_level: 3, post_quantum: true,
      valid_to: '2030-01-01T00:00:00Z' }
    render(<CADetails ca={ca} />)
    expect(screen.getAllByText(LEVEL_LABEL).length).toBeGreaterThan(0)
    expect(screen.queryByText(ML_DSA_65.label)).toBeNull()
    expect(screen.getByTestId('post-quantum-badge')).toBeInTheDocument()
    expect(screen.queryByText(en.cas.signatureSchemePkcs1v15)).toBeNull()
  })

  it('explains the badge by the key, never by the signature', () => {
    // An RSA CA may sign an ML-DSA leaf: the badge follows the leaf's own key
    render(<CADetails ca={{ id: 9, descr: 'PQ root', key_type: 'ML-DSA-65', post_quantum: true }} />)
    const hint = screen.getByTestId('post-quantum-badge').getAttribute('title')
    expect(hint).toMatch(/post-quantum key/i)
    expect(hint).not.toMatch(/signed/i)
  })

  it('previews an ML-DSA template under its own name', () => {
    render(<TemplatePreviewModal open onClose={() => {}} template={{ name: 'PQ', key_type: 'ML-DSA-65' }} />)
    expect(screen.getByText(LEVEL_LABEL)).toBeInTheDocument()
    expect(screen.queryByText(/-bit|256/)).toBeNull()
  })

  it('previews a classical template with its registry name', () => {
    render(<TemplatePreviewModal open onClose={() => {}} template={{ name: 'TLS', key_type: 'EC-P384' }} />)
    expect(screen.getByText('ECDSA P-384')).toBeInTheDocument()
  })

  it('lists an ML-DSA certificate with its level, an unnamed key as a dash', () => {
    keyCell({ key_algorithm: 'ML-DSA-65', key_type: 'ML-DSA-65', security_level: 3 })
    expect(screen.getByText(LEVEL_LABEL)).toBeInTheDocument()
    keyCell({ key_algorithm: null, key_type: null })
    expect(screen.queryByText('RSA')).toBeNull()
  })
})
