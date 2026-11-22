/**
 * CASideDetails as typed rows (KV-3): constraints, extensions, fingerprints and metadata are Facts; a digest
 * or a key identifier is a hex chip, a URL a url chip, both copied whole; a missing value is an absence.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'

const t = (key, opts) => (opts?.name ? `${key} ${opts.name}` : key)
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t, i18n: { language: 'en' } }) }))
vi.mock('../../../contexts/NotificationContext', () => ({ useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn() }) }))

import { CASideDetails } from '../CASideDetails'

const SHA256 = Array.from({ length: 32 }, (_, i) => (i * 7 + 16).toString(16).toUpperCase().padStart(2, '0').slice(-2)).join(':')
const SHA1 = Array.from({ length: 20 }, (_, i) => (i * 11 + 3).toString(16).toUpperCase().padStart(2, '0').slice(-2)).join(':')
const SKI = '96:E1:32:F0:4F:31:88:8E:73:10:48:18:80:67:58:87:38:92:F3:BF'
const SIA = 'http://pki.example.com/repository/ucm-production-intermediate-ca.p7c'
const CDP = 'http://pki.example.com/crl/ucm-production-intermediate-ca.crl'
const ca = (over = {}) => ({
  id: 7, path_length: 0, sia_enabled: true, sia_urls: [SIA],
  name_constraints_permitted: [{ type: 'DNS', value: 'example.com' }, { type: 'DNS', value: '.corp.example.org' }],
  inhibit_any_policy: 0,
  extensions: {
    basic_constraints: { ca: true, path_length: 0, critical: true },
    subject_key_identifier: { value: SKI },
    crl_distribution_points: { urls: [CDP] },
    authority_info_access: { ocsp: ['http://ocsp.example.com'], ca_issuers: [] },
  },
  thumbprint_sha256: SHA256, thumbprint_sha1: SHA1,
  created_at: '2026-09-15T07:26:00Z', created_by: null, imported_from: 'generated',
  ...over,
})

let writeText
beforeEach(() => {
  writeText = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
  Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true })
})

const open = (testId) => {
  const fold = screen.getByTestId(testId)
  fireEvent.click(within(fold).getAllByRole('button')[0])
  return fold
}
const row = (fold, label) => within(fold).getByText(label, { selector: 'dt' }).closest('.row')

describe('CASideDetails: typed rows', () => {
  it('draws every folded section as Facts, none as a flat dl.props', () => {
    const { container } = render(<CASideDetails ca={ca()} t={t} />)
    for (const id of ['ca-constraints', 'ca-extensions', 'ca-fingerprints', 'ca-metadata']) open(id)
    expect(container.querySelectorAll('dl.props')).toHaveLength(0)
    expect(container.querySelectorAll('dl.kv')).toHaveLength(4)
  })

  it('writes the fingerprints as hex chips in lines of 8 bytes, each copied whole, no button beside them', async () => {
    render(<CASideDetails ca={ca()} t={t} />)
    const fold = open('ca-fingerprints')
    const sha256 = row(fold, 'SHA-256')
    expect(sha256.querySelectorAll('dd.v .code-value.hex .line')).toHaveLength(4)
    expect(sha256.querySelectorAll('button')).toHaveLength(1)
    fireEvent.click(within(sha256).getByRole('button', { name: 'protocols.copyValue SHA-256' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(SHA256))
    fireEvent.click(within(row(fold, 'SHA-1')).getByRole('button', { name: 'protocols.copyValue SHA-1' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(SHA1))
  })

  it('says a fingerprint is missing instead of leaving its value empty', () => {
    render(<CASideDetails ca={ca({ thumbprint_sha1: '' })} t={t} />)
    const sha1 = row(open('ca-fingerprints'), 'SHA-1')
    expect(sha1.querySelector('dd.v')).toBeNull()
    expect(sha1.querySelector('dd.absent')).toHaveTextContent('—')
    expect(sha1.querySelector('button')).toBeNull()
  })

  it('writes a SIA URL as a url chip copied whole, and the name constraints as a long row', async () => {
    render(<CASideDetails ca={ca()} t={t} />)
    const fold = open('ca-constraints')
    const sia = row(fold, 'cas.siaUrls')
    expect(sia.querySelector('dd.v .code-value.url')).toBeTruthy()
    fireEvent.click(within(sia).getByRole('button', { name: 'protocols.copyValue cas.siaUrls' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(SIA))
    expect(row(fold, 'cas.nameConstraintsPermitted')).toHaveClass('long')
    expect(row(fold, 'cas.nameConstraintsPermitted').querySelector('dd.v')).toHaveTextContent('DNS:example.com, DNS:.corp.example.org')
    expect(row(fold, 'cas.pathLength').querySelector('dd.v')).toHaveTextContent('cas.pathLengthLeafOnly')
  })

  it('names an extension in its term, its OID under its value, a key identifier and a URL in their chips', async () => {
    render(<CASideDetails ca={ca()} t={t} />)
    const fold = open('ca-extensions')
    const ski = row(fold, 'Subject Key Identifier')
    expect(ski.querySelector('dt')).toHaveTextContent(/^Subject Key Identifier$/)
    expect(ski.querySelector('dd.v .code-value.hex')).toBeTruthy()
    expect(ski.querySelector('dd.v > .sub')).toHaveTextContent('2.5.29.14')
    fireEvent.click(within(ski).getByRole('button', { name: 'protocols.copyValue Subject Key Identifier' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(SKI))
    const bc = row(fold, 'Basic Constraints')
    expect(bc.querySelector('dd.v > .sub')).toHaveTextContent('2.5.29.19 · inspector.cert.critical')
    const cdp = row(fold, 'CRL Distribution Points')
    fireEvent.click(within(cdp).getByRole('button', { name: 'protocols.copyValue CRL Distribution Points' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(CDP))
    // « OCSP: <url> » keeps its prefix in text, the URL in its chip
    const aia = row(fold, 'Authority Information Access')
    expect(aia.querySelector('dd.v')).toHaveTextContent(/^OCSP/)
    expect(aia.querySelector('dd.v .code-value.url')).toBeTruthy()
  })

  it('writes a missing metadata as an absence, not as a value', () => {
    render(<CASideDetails ca={ca()} t={t} />)
    const fold = open('ca-metadata')
    const by = row(fold, 'details.createdBy')
    expect(by.querySelector('dd.v')).toBeNull()
    expect(by.querySelector('dd.absent')).toHaveTextContent('—')
    expect(row(fold, 'details.importedFrom').querySelector('dd.v')).toHaveTextContent('generated')
  })
})
