/**
 * The panels of components/detail stay pure: no service import, no request,
 * no navigation. Actions belong to hooks/useEntityActions.
 */
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const DIR = join(__dirname, '..')
const files = readdirSync(DIR).filter(f => /\.(jsx?|js)$/.test(f))

describe('components/detail', () => {
  it('has panels to check', () => {
    expect(files).toEqual(expect.arrayContaining(['CertificatePanel.jsx', 'CAPanel.jsx', 'TrustCertPanel.jsx', 'CSRPanel.jsx']))
  })

  it.each(files)('%s imports no service and sends no request', (file) => {
    const source = readFileSync(join(DIR, file), 'utf8')
    expect(source).not.toMatch(/from\s+['"][^'"]*services/)
    expect(source).not.toMatch(/\bfetch\s*\(/)
    expect(source).not.toMatch(/\bdispatchEvent\b/)
  })
})
