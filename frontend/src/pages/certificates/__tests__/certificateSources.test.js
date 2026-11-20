/** Every source the stats endpoint reports has its own words, not a humanized key. */
import { describe, it, expect } from 'vitest'
import { sourceLabel } from '../certificateSources'

const t = (key) => key

describe('sourceLabel', () => {
  it.each([
    ['acme', 'certificates.sourceAcme'], ['acme-renewal', 'certificates.sourceAcmeRenewal'],
    ['acme_client', 'certificates.sourceAcmeClient'], ['approval', 'certificates.sourceApproval'],
    ['est', 'certificates.sourceEst'], ['issued', 'certificates.sourceIssued'],
    ['letsencrypt', 'certificates.sourceLetsencrypt'], ['manual', 'certificates.sourceManual'],
    ['msca', 'certificates.sourceMsca'], ['scep', 'certificates.sourceScep'], ['upload', 'certificates.sourceUpload'],
  ])('names %s', (source, key) => {
    expect(sourceLabel(source, t)).toBe(key)
  })

  it('humanizes a source it does not know', () => {
    expect(sourceLabel('some_new_path', t)).toBe('Some New Path')
  })
})
