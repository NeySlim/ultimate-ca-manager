/**
 * No frontend call reaches a route the API retired with the Windows profiles (single-row XCEP,
 * WSTEP, Kerberos and AD connector configuration): the services speak to the collections only.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import * as services from '../index'

const REMOVED = [
  /\/xcep\/config/, /\/wstep\/config/, /\/kerberos\/(config|keytab)/,
  /\/ad-connector(?![s\w-])/, // the singular, not /ad-connectors
]

const sources = import.meta.glob('../../**/*.{js,jsx}', { query: '?raw', import: 'default', eager: true })

describe('retired routes', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('is not reached by any service method', async () => {
    const urls = []
    vi.stubGlobal('fetch', vi.fn(async (url) => {
      urls.push(String(url))
      return { ok: true, status: 200, headers: new Headers(), json: async () => ({}), text: async () => '{}', blob: async () => new Blob() }
    }))
    for (const service of Object.values(services)) {
      if (!service || typeof service !== 'object') continue
      for (const method of Object.values(service)) {
        if (typeof method !== 'function') continue
        try { await method(1, new File(['x'], 'k.keytab'), {}) } catch { /* only the URL matters */ }
      }
    }
    expect(urls.length).toBeGreaterThan(100)
    expect(urls.filter(url => REMOVED.some(re => re.test(url)))).toEqual([])
  })

  it('is not written in any source file', () => {
    const offenders = []
    for (const [path, text] of Object.entries(sources)) {
      if (path.includes('__tests__') || path.includes('.test.')) continue
      for (const re of REMOVED) if (re.test(text)) offenders.push(`${path}: ${re}`)
    }
    expect(offenders).toEqual([])
  })

  it('knows the collections', async () => {
    const urls = []
    vi.stubGlobal('fetch', vi.fn(async (url) => {
      urls.push(String(url))
      return { ok: true, status: 200, headers: new Headers(), json: async () => ({}) }
    }))
    for (const call of [
      () => services.windowsProfilesService.list({ page: 1, per_page: 25 }),
      () => services.windowsProfilesService.getSettings(),
      () => services.adConnectorsService.list(),
    ]) {
      try { await call() } catch { /* only the URL matters */ }
    }
    expect(urls).toEqual([
      '/api/v2/windows-profiles?page=1&per_page=25',
      '/api/v2/windows-profiles/settings',
      '/api/v2/ad-connectors',
    ])
  })
})
