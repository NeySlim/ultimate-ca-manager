/**
 * A post-quantum certificate is shown under its own name, with its security
 * level and a badge, and a key the API does not name is never shown as RSA.
 * Records follow the API contract for ML-DSA and SLH-DSA keys.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import en from '../../i18n/locales/en.json'
import { GROUP_PQ, KEY_ALGORITHMS } from '../../lib/keyAlgorithms'

// Resolves keys against the English catalogue, so the test reads what a user reads
const lookup = (key) => key.split('.').reduce((node, part) => (node == null ? node : node[part]), en)
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => {
      const vars = typeof opts === 'object' && opts ? opts : {}
      const template = lookup(key) ?? (typeof opts === 'string' ? opts : vars.defaultValue ?? key)
      return String(template).replace(/\{\{(\w+)\}\}/g, (_m, name) => (vars[name] ?? `{{${name}}}`))
    },
  }),
  initReactI18next: { type: '3rdParty', init: () => {} },
  Trans: ({ children }) => children,
}))
vi.mock('../deploy/CertDeploySection', () => ({ CertDeploySection: () => null }))
vi.mock('../CertificateLintModal', () => ({ CertificateLintModal: () => null }))

import { CertificateDetails } from '../CertificateDetails'

const PQ_ROWS = KEY_ALGORITHMS.filter(a => a.group === GROUP_PQ)

const base = {
  id: 7, common_name: 'pq.example.com', subject: 'CN=pq.example.com', serial_number: '42',
  valid_to: '2030-01-01T00:00:00Z', has_private_key: true, status: 'valid',
}
const mldsa = (a) => ({
  ...base, key_algorithm: a.label, key_type: a.label, key_size: null,
  security_level: a.securityLevel, post_quantum: true, signature_algorithm: a.label,
})
const slhdsa = {
  ...base, has_private_key: false, key_algorithm: 'SLH-DSA-SHA2-128s', key_type: 'SLH-DSA-SHA2-128s',
  key_size: null, post_quantum: true, verifiable: false, signature_algorithm: 'SLH-DSA-SHA2-128s',
}
const rsa = {
  ...base, key_algorithm: 'RSA', key_type: 'RSA 2048', key_size: 2048, post_quantum: false,
  signature_algorithm: 'SHA256-RSA',
}

const levelLabel = (a) => `${a.label} (level ${a.securityLevel})`

describe('CertificateDetails with a post-quantum key', () => {
  it.each(PQ_ROWS.map(a => [a.label, a]))('names %s with its security level and a badge', (_label, a) => {
    render(<CertificateDetails certificate={mldsa(a)} />)
    expect(screen.getAllByText(levelLabel(a)).length).toBeGreaterThan(0)
    expect(screen.getByTestId('post-quantum-badge')).toHaveTextContent('Post-quantum')
    // No size in bits for a key that has none
    expect(screen.queryByText(/bits/)).toBeNull()
  })

  it('shows the whole ML-DSA signature name in the summary chip', () => {
    const a = PQ_ROWS.find(r => r.label === 'ML-DSA-65')
    render(<CertificateDetails certificate={mldsa(a)} />)
    expect(screen.queryByText('ML')).toBeNull()
  })

  it('names an SLH-DSA key as the API does, with the badge', () => {
    render(<CertificateDetails certificate={slhdsa} />)
    expect(screen.getAllByText('SLH-DSA-SHA2-128s').length).toBeGreaterThan(0)
    expect(screen.getByTestId('post-quantum-badge')).toBeInTheDocument()
  })

  it('keeps an RSA certificate as it was, without the badge', () => {
    render(<CertificateDetails certificate={rsa} />)
    expect(screen.getByText('RSA')).toBeInTheDocument()
    expect(screen.getByText('2048 bits')).toBeInTheDocument()
    expect(screen.queryByTestId('post-quantum-badge')).toBeNull()
  })

  it.each([[false], [true]])('never calls a key the API did not name RSA (embedded: %s)', (embedded) => {
    const unnamed = { ...base, key_algorithm: null, key_type: null, key_size: null, signature_algorithm: null }
    render(<CertificateDetails certificate={unnamed} embedded={embedded} />)
    expect(screen.queryByText(/\bRSA\b/)).toBeNull()
  })

  it('offers no PKCS#12 or JKS export for an ML-DSA key', () => {
    const a = PQ_ROWS.find(r => r.label === 'ML-DSA-65')
    render(<CertificateDetails certificate={mldsa(a)} onExport={vi.fn()} canExportKey />)
    fireEvent.click(screen.getAllByRole('button', { name: /export/i })[0])
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText('P12 / PKCS#12').closest('button')).toBeDisabled()
    expect(within(dialog).getByText('JKS').closest('button')).toBeDisabled()
    expect(within(dialog).getByText('PEM').closest('button')).toBeEnabled()
  })
})
