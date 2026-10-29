import { describe, it, expect } from 'vitest'
import { commonNameOf, crossAttachOffered, crossStateOf, certificateFileToPem } from '../crossCertificates'
import { crossSummary } from '../importResult'

describe('cross-certificate helpers', () => {
  it('reads the CN of a distinguished name', () => {
    expect(commonNameOf('CN=Root A,O=Acme,C=FR')).toBe('Root A')
    expect(commonNameOf('O=Acme')).toBe('O=Acme')
    expect(commonNameOf('')).toBe('')
  })

  it('names why a cross-certificate cannot be served', () => {
    expect(crossStateOf({ revoked: true, expired: true })).toBe('revoked')
    expect(crossStateOf({ expired: true })).toBe('expired')
    expect(crossStateOf({ not_yet_valid: true })).toBe('notYetValid')
    expect(crossStateOf({})).toBeNull()
  })

  it('offers the attachment only on the cross-certificate 409', () => {
    const err = (status, code, options) => ({ status, data: { details: { code, options } } })
    expect(crossAttachOffered(err(409, 'cross_certificate_detected', ['attach', 'replace']))).toBe(true)
    expect(crossAttachOffered(err(409, 'cross_certificate_detected', ['replace']))).toBe(false)
    expect(crossAttachOffered(err(409, 'other', ['attach']))).toBe(false)
    expect(crossAttachOffered(err(400, 'cross_certificate_detected', ['attach']))).toBe(false)
    expect(crossAttachOffered(new Error('x'))).toBe(false)
  })

  it('keeps PEM text and wraps DER bytes', async () => {
    const pem = '-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----\n'
    expect(await certificateFileToPem(new Blob([pem]))).toBe(pem)
    const der = await certificateFileToPem(new Blob([new Uint8Array([0x30, 0x82, 0x01, 0xff])]))
    expect(der).toMatch(/^-----BEGIN CERTIFICATE-----\nMIIB\/w==\n-----END CERTIFICATE-----\n$/)
  })

  it('counts the cross-certificates a Smart Import attached or left out', () => {
    const result = { warning_details: [
      { code: 'cross_certificate_attached' }, { code: 'cross_certificate_skipped' },
      { code: 'cross_certificate_skipped' }, { code: 'other' },
    ] }
    expect(crossSummary(result)).toEqual({ attached: 1, skipped: 2 })
    expect(crossSummary(null)).toEqual({ attached: 0, skipped: 0 })
  })
})
