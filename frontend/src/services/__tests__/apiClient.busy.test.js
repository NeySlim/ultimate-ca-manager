/**
 * The server's busy answer (SQLite: a write that met another one) reads as such in the page's
 * language, with its Retry-After; any other 503 keeps the server's own message.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import i18next from 'i18next'
import en from '../../i18n/locales/en.json'
import fr from '../../i18n/locales/fr.json'

const BUSY = 'The database is busy with another write: retry shortly.'

const answer = (body, retryAfter = '5') => ({
  ok: false,
  status: 503,
  headers: new Headers({ 'content-type': 'application/problem+json', 'retry-after': retryAfter }),
  json: () => Promise.resolve(body),
})

describe('a busy server', () => {
  const originalFetch = global.fetch

  beforeEach(async () => {
    global.fetch = vi.fn()
    await i18next.init({ lng: 'en', fallbackLng: 'en', resources: { en: { translation: en }, fr: { translation: fr } } })
  })

  afterEach(() => {
    global.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('says the server is busy, in the page\'s language, and keeps its Retry-After', async () => {
    const { apiClient } = await import('../apiClient')
    global.fetch.mockResolvedValueOnce(answer({ status: 503, detail: BUSY, message: BUSY }))
    await expect(apiClient.post('/csrs/7/sign', {})).rejects.toMatchObject({
      status: 503, busy: true, retryAfter: 5, message: en.messages.errors.serverBusy,
    })
    await i18next.changeLanguage('fr')
    global.fetch.mockResolvedValueOnce(answer({ status: 503, detail: BUSY, message: BUSY }))
    await expect(apiClient.post('/csrs/7/sign', {})).rejects.toMatchObject({ message: fr.messages.errors.serverBusy })
  })

  it('keeps the message of another 503', async () => {
    const { apiClient } = await import('../apiClient')
    global.fetch.mockResolvedValueOnce(answer({ status: 503, detail: 'A restore is in progress', code: 'maintenance' }))
    const error = await apiClient.post('/csrs/7/sign', {}).catch((e) => e)
    expect(error).toMatchObject({ status: 503, message: 'A restore is in progress' })
    expect(error.busy).toBeFalsy()
  })
})
