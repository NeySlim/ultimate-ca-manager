/**
 * A write refused for its CSRF token (a page older than the session's record, #457): the
 * client fetches a new token and sends the write once more; refused again, it says in the
 * page's language that the page is out of date instead of the server's raw text.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import i18next from 'i18next'
import en from '../../i18n/locales/en.json'
import fr from '../../i18n/locales/fr.json'

const CSRF_PROBLEM = 'urn:ucm:problem:csrf-invalid'
const RAW = 'CSRF validation failed: Invalid CSRF token'

const json = (status, body) => ({
  ok: status >= 200 && status < 300,
  status,
  headers: new Headers({ 'content-type': status >= 400 ? 'application/problem+json' : 'application/json' }),
  json: () => Promise.resolve(body),
})
const refused = (type = CSRF_PROBLEM) => json(403, { status: 403, type, detail: RAW, message: RAW })
const verified = (token) => json(200, { data: { authenticated: true, csrf_token: token } })
const saved = () => json(200, { data: { ok: true } })

const sentToken = (call) => (call[1]?.headers || {})['X-CSRF-Token']
const writes = () => global.fetch.mock.calls.filter(([url]) => !url.endsWith('/auth/verify'))

describe('a write refused for its CSRF token', () => {
  const originalFetch = global.fetch

  beforeEach(async () => {
    global.fetch = vi.fn()
    sessionStorage.clear()
    await i18next.init({ lng: 'en', fallbackLng: 'en', resources: { en: { translation: en }, fr: { translation: fr } } })
  })

  afterEach(() => {
    global.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('gets a new token and sends the write once more with it', async () => {
    const { apiClient } = await import('../apiClient')
    apiClient.setCsrfToken('stale')
    global.fetch
      .mockResolvedValueOnce(refused())
      .mockResolvedValueOnce(verified('fresh'))
      .mockResolvedValueOnce(saved())
    await expect(apiClient.put('/account/preferences', {})).resolves.toEqual({ data: { ok: true } })
    expect(writes().map(sentToken)).toEqual(['stale', 'fresh'])
    expect(apiClient.getCsrfToken()).toBe('fresh')
  })

  it('sends it once only, then says the page is out of date in its language', async () => {
    const { apiClient } = await import('../apiClient')
    apiClient.setCsrfToken('stale')
    await i18next.changeLanguage('fr')
    // Every check hands a token, every write is refused (a fifth one would be saved)
    let sent = 0
    global.fetch.mockImplementation(async (url) => {
      if (url.endsWith('/auth/verify')) return verified(`fresh-${sent}`)
      sent += 1
      return sent < 5 ? refused() : saved()
    })
    await expect(apiClient.post('/cas', { name: 'x' })).rejects.toMatchObject({
      status: 403, stale: true, message: fr.messages.errors.csrfStale,
    })
    expect(writes()).toHaveLength(2)
  })

  it('knows the refusal of an older server by its text', async () => {
    const { apiClient } = await import('../apiClient')
    apiClient.setCsrfToken('stale')
    global.fetch
      .mockResolvedValueOnce(refused('about:blank'))
      .mockResolvedValueOnce(verified('fresh'))
      .mockResolvedValueOnce(saved())
    await expect(apiClient.delete('/cas/3')).resolves.toEqual({ data: { ok: true } })
    expect(writes()).toHaveLength(2)
  })

  it('does not send again when no new token comes', async () => {
    const { apiClient } = await import('../apiClient')
    apiClient.setCsrfToken('stale')
    global.fetch
      .mockResolvedValueOnce(refused())
      .mockResolvedValueOnce(json(200, { data: { authenticated: false } }))
    await expect(apiClient.post('/cas', {})).rejects.toMatchObject({ stale: true, message: en.messages.errors.csrfStale })
    expect(writes()).toHaveLength(1)
  })

  it('leaves any other 403 as it is, sent once', async () => {
    const { apiClient } = await import('../apiClient')
    apiClient.setCsrfToken('mine')
    global.fetch.mockResolvedValueOnce(json(403, { status: 403, detail: 'Permission denied', message: 'Permission denied' }))
    await expect(apiClient.post('/cas', {})).rejects.toMatchObject({ status: 403, message: 'Permission denied' })
    expect(global.fetch).toHaveBeenCalledTimes(1)
  })

  it('renews the token of an upload the same way', async () => {
    const { apiClient } = await import('../apiClient')
    apiClient.setCsrfToken('stale')
    global.fetch
      .mockResolvedValueOnce(refused())
      .mockResolvedValueOnce(verified('fresh'))
      .mockResolvedValueOnce(saved())
    await expect(apiClient.upload('/import', new FormData())).resolves.toEqual({ data: { ok: true } })
    expect(writes().map(sentToken)).toEqual(['stale', 'fresh'])
  })
})
