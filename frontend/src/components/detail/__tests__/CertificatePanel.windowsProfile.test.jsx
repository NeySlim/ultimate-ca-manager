/** The detail of a certificate names the Windows enrollment profile that issued it. */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import en from '../../../i18n/locales/en.json'

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
vi.mock('../../deploy/CertDeploySection', () => ({ CertDeploySection: () => null }))
vi.mock('../../CertificateLintModal', () => ({ CertificateLintModal: () => null }))

import { CertificatePanel } from '../CertificatePanel'


const base = {
  id: 7, common_name: 'pc.example.com', subject: 'CN=pc.example.com', serial_number: '42',
  valid_to: '2030-01-01T00:00:00Z', has_private_key: true, status: 'valid',
}

describe('CertificatePanel with a Windows profile', () => {
  it('names the profile', () => {
    render(<CertificatePanel certificate={{ ...base, windows_profile_id: 3, windows_profile_name: 'Corp' }} />)
    expect(screen.getByText('Windows profile')).toBeInTheDocument()
    expect(screen.getByText('Corp')).toBeInTheDocument()
  })

  it('falls back to the id once the profile is gone', () => {
    render(<CertificatePanel certificate={{ ...base, windows_profile_id: 3, windows_profile_name: null }} />)
    expect(screen.getByText('#3')).toBeInTheDocument()
  })

  it('shows nothing for a certificate no profile issued', () => {
    render(<CertificatePanel certificate={{ ...base, windows_profile_id: null, windows_profile_name: null }} />)
    expect(screen.queryByText('Windows profile')).toBeNull()
  })
})
