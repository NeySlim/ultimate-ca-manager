/**
 * The sections of a request in typed rows: its state a pill, a missing subject field in grey, the
 * serial of a signed request copyable whole, the signature named by its hash as a certificate's is.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'

vi.mock('react-i18next', async () => {
  const { enI18n } = await import('../../test/enT')
  return { useTranslation: () => enI18n, Trans: ({ children }) => children, initReactI18next: { type: '3rdParty', init: () => {} } }
})
vi.mock('../certificates/inspector/PemPanel', () => ({ PemPanel: () => <pre data-testid="pem" /> }))

import en from '../../i18n/locales/en.json'
import { CsrSections } from '../csrs/CsrSections'

const SIGNED = {
  id: 298, cn: 'smartcard.example.test', common_name: 'smartcard.example.test', requester: 'system', key_type: 'RSA 2048',
  created_at: '2026-10-12T15:30:29Z', status: 'Signed', signed_by: 'Smoke CA', signed_at: '2026-10-12T15:15:29Z',
  valid_to: '2026-11-11T15:30:29Z', serial_number: '4660', organization: 'Example', signature_algorithm: 'sha256WithRSAEncryption',
}
const rowOf = (label) => screen.getByText(label, { selector: 'dt' }).closest('div.row')
let writeText

beforeEach(() => {
  writeText = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
  Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true })
})

describe('a request\'s overview', () => {
  it('draws Facts, its state a pill, its serial copyable whole', async () => {
    const { container } = render(<CsrSections csr={SIGNED} signed section="overview" />)
    expect(container.querySelector('dl.props')).toBeNull()
    expect(rowOf(en.atelier.state).querySelector('dd.v .badge.good')).toHaveTextContent(en.csrs.states.signed)
    const serial = rowOf(en.common.serial)
    expect(serial.querySelector('dd.v .code-value.hex')).toHaveTextContent('12:34')
    fireEvent.click(within(serial).getByRole('button', { name: `Copy ${en.common.serial}` }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('12:34'))
  })

  it('says an unknown submission date in grey, not as a value', () => {
    render(<CsrSections csr={{ ...SIGNED, created_at: null }} signed section="overview" />)
    expect(rowOf(en.csrs.module.submitted).querySelector('dd.absent')).toHaveTextContent('—')
  })
})

describe('a request\'s details', () => {
  it('greys the missing subject fields and names the signature by its hash', () => {
    const { container } = render(<CsrSections csr={SIGNED} signed section="details" />)
    expect(container.querySelector('dl.props')).toBeNull()
    expect(rowOf(en.common.organization).querySelector('dd.v')).toHaveTextContent('Example')
    expect(rowOf(en.common.orgUnit).querySelector('dd.absent')).toHaveTextContent('—')
    expect(rowOf(en.common.email).querySelector('dd.v')).toBeNull()
    expect(rowOf(en.common.signature).querySelector('dd.v')).toHaveTextContent(/^SHA-256$/)
  })
})
