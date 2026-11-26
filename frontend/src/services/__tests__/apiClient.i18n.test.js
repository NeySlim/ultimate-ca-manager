/**
 * The client's own error texts (network failure, a status with no message from the server)
 * read in the interface's language.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import i18next from 'i18next'
import en from '../../i18n/locales/en.json'
import fr from '../../i18n/locales/fr.json'

const bare = (status) => ({
  ok: false, status, headers: new Headers({ 'content-type': 'text/html' }),
  json: () => Promise.reject(new Error('not json')), text: () => Promise.resolve('<html>'),
})

describe('apiClient error texts', () => {
  const originalFetch = global.fetch
  beforeEach(async () => {
    global.fetch = vi.fn()
    await i18next.init({ lng: 'fr', fallbackLng: 'en', resources: { en: { translation: en }, fr: { translation: fr } } })
  })
  afterEach(() => { global.fetch = originalFetch; vi.restoreAllMocks() })

  it('a network failure', async () => {
    const { apiClient } = await import('../apiClient')
    global.fetch.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    await expect(apiClient.get('/x')).rejects.toMatchObject({ status: 0, message: fr.messages.errors.network })
    expect(fr.messages.errors.network).not.toBe(en.messages.errors.network)
  })

  it.each([502, 504, 413])('a %s without a message from the server', async (status) => {
    const { apiClient } = await import('../apiClient')
    global.fetch.mockResolvedValueOnce(bare(status))
    await expect(apiClient.get('/x')).rejects.toMatchObject({ status, message: fr.messages.errors.http[status] })
    expect(fr.messages.errors.http[status]).not.toBe(en.messages.errors.http[status])
  })

  it('a download refused', async () => {
    const { apiClient } = await import('../apiClient')
    global.fetch.mockResolvedValueOnce(bare(404))
    await expect(apiClient.download('/x')).rejects.toThrow(fr.messages.errors.http[404])
  })

  it('keeps the server\'s own message', async () => {
    const { apiClient } = await import('../apiClient')
    global.fetch.mockResolvedValueOnce({ ok: false, status: 504, headers: new Headers({ 'content-type': 'application/json' }),
      json: () => Promise.resolve({ message: 'Upstream CA timed out' }) })
    await expect(apiClient.get('/x')).rejects.toMatchObject({ message: 'Upstream CA timed out' })
  })
})
