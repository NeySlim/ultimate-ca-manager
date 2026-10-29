/**
 * The ACME domain form says how many CAs it leaves out, and a saved CA that can
 * no longer sign stays listed without being counted (#426).
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, opts) => (opts?.count !== undefined ? `${key}:${opts.count}` : key) }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

import LocalDomainForm from '../LocalDomainForm'

const signer = { id: 1, common_name: 'Issuing CA', has_private_key: true }
const keylessRoot = { id: 2, common_name: 'Imported root', is_root: true, certificate_only: true, has_private_key: false }
const offline = { id: 3, common_name: 'Offline CA', has_private_key: true, offline: true }

describe('LocalDomainForm CAs that cannot sign (#426)', () => {
  it('counts the CAs it leaves out', () => {
    render(<LocalDomainForm cas={[signer, keylessRoot, offline]} onSubmit={vi.fn()} onCancel={vi.fn()} />)
    expect(screen.getByText('cas.notListedForSigning:2')).toBeInTheDocument()
  })

  it('does not count the saved CA it keeps showing', () => {
    render(<LocalDomainForm domain={{ domain: 'x.example', issuing_ca_id: 3 }} cas={[signer, keylessRoot, offline]}
      onSubmit={vi.fn()} onCancel={vi.fn()} />)
    expect(screen.getByText('cas.notListedForSigning:1')).toBeInTheDocument()
  })

  it('says nothing when every CA can sign', () => {
    render(<LocalDomainForm cas={[signer]} onSubmit={vi.fn()} onCancel={vi.fn()} />)
    expect(screen.queryByText(/cas\.notListedForSigning/)).toBeNull()
  })
})
