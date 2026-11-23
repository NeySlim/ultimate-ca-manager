/**
 * The bulk operations' tabs in French: whole words, and an acronym takes no plural mark (« AC », « CSR »),
 * never the English abbreviations « Certs », « ACs », « CSRs ».
 */
import { describe, it, expect } from 'vitest'
import fr from '../locales/fr.json'

describe('French short labels', () => {
  it('names the bulk tabs in French', () => {
    expect(fr.common.certificatesShort).toBe('Certificats')
    expect(fr.common.casShort).toBe('AC')
    expect(fr.common.csrsShort).toBe('CSR')
  })
})
