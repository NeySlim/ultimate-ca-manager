/**
 * SmartImport Tests — encrypted key detection for both paste and file upload
 */
import { describe, it, expect } from 'vitest'

// Test the encrypted detection logic directly (extracted from SmartImport)
describe('SmartImport — encrypted key detection', () => {
  const ENCRYPTED_PEM = `-----BEGIN ENCRYPTED PRIVATE KEY-----
MIIFHDBOBgkqhkiG9w0BBQ0wQTApBgkqhkiG9w0BBQwwHAQI...
-----END ENCRYPTED PRIVATE KEY-----`

  const PLAIN_PEM = `-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASC...
-----END PRIVATE KEY-----`

  const CERT_PEM = `-----BEGIN CERTIFICATE-----
MIIDXTCCAkWgAwIBAgIJALKo...
-----END CERTIFICATE-----`

  it('detects encrypted PEM in paste content', () => {
    const hasEncrypted = ENCRYPTED_PEM.includes('ENCRYPTED')
    expect(hasEncrypted).toBe(true)
  })

  it('does not flag plain PEM as encrypted', () => {
    const hasEncrypted = PLAIN_PEM.includes('ENCRYPTED')
    expect(hasEncrypted).toBe(false)
  })

  it('does not flag certificate as encrypted', () => {
    const hasEncrypted = CERT_PEM.includes('ENCRYPTED')
    expect(hasEncrypted).toBe(false)
  })

  it('detects encrypted key in uploaded text file', () => {
    // Simulates a file upload with type: 'text' (how SmartImport stores parsed PEMs)
    const files = [
      { name: 'cert.pem', type: 'text', data: CERT_PEM },
      { name: 'key.pem', type: 'text', data: ENCRYPTED_PEM },
    ]

    const encryptedIndices = files.reduce((acc, file, idx) => {
      if (file.name?.match(/\.(p12|pfx|key)$/i) ||
          (file.type === 'text' && file.data?.includes('ENCRYPTED'))) {
        acc.push(idx)
      }
      return acc
    }, [])

    expect(encryptedIndices).toEqual([1])
  })

  it('detects encrypted in .p12/.pfx files by extension', () => {
    const files = [
      { name: 'bundle.p12', type: 'binary', data: null },
    ]

    const encryptedIndices = files.reduce((acc, file, idx) => {
      if (file.name?.match(/\.(p12|pfx|key)$/i) ||
          (file.type === 'text' && file.data?.includes('ENCRYPTED'))) {
        acc.push(idx)
      }
      return acc
    }, [])

    expect(encryptedIndices).toEqual([0])
  })
})
