/**
 * The server's busy answer (SQLite: a write that met another one) reads as such in the page's
 * language, with its Retry-After; any other 503 keeps the server's own message.
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import i18next from 'i18next'
import en from '../../i18n/locales/en.json'
import fr from '../../i18n/locales/fr.json'

const BUSY = 'The database is busy with another write: retry shortly.'
// What the server writes (backend/tests/test_csr_sign_meets_a_lock.py holds it to the same file)
const CONTRACT = JSON.parse(readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', '..', 'contracts', 'database_busy.json'), 'utf8'))

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

  it('knows the server\'s busy answer by its type, whatever its text', async () => {
    const { apiClient } = await import('../apiClient')
    const { _doc, ...body } = CONTRACT
    global.fetch.mockResolvedValueOnce(answer(body))
    await expect(apiClient.post('/csrs/7/sign', {})).rejects.toMatchObject({ busy: true, retryAfter: 5 })
    global.fetch.mockResolvedValueOnce(answer({ ...body, detail: 'Base occupee' }))
    await expect(apiClient.post('/csrs/7/sign', {})).rejects.toMatchObject({
      busy: true, message: en.messages.errors.serverBusy,
    })
  })

  it('never takes another typed problem for the busy answer', async () => {
    const { apiClient } = await import('../apiClient')
    global.fetch.mockResolvedValueOnce(answer({ type: 'urn:ucm:problem:cluster-maintenance', status: 503, detail: BUSY }))
    const error = await apiClient.post('/csrs/7/sign', {}).catch((e) => e)
    expect(error.busy).toBeFalsy()
  })

  it('keeps the message of another 503', async () => {
    const { apiClient } = await import('../apiClient')
    global.fetch.mockResolvedValueOnce(answer({ status: 503, detail: 'A restore is in progress', code: 'maintenance' }))
    const error = await apiClient.post('/csrs/7/sign', {}).catch((e) => e)
    expect(error).toMatchObject({ status: 503, message: 'A restore is in progress' })
    expect(error.busy).toBeFalsy()
  })
})
