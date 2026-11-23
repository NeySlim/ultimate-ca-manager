/**
 * The search the palette reads: GET /search answers in the API envelope ({ data: { certificates, cas, … } }),
 * the service gives the palette the groups themselves, so a certificate found opens in its dock.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const get = vi.fn()
vi.mock('../apiClient', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, apiClient: { ...actual.apiClient, get: (...a) => get(...a) } }
})

const { searchService } = await import('../search.service')

beforeEach(() => get.mockReset())

describe('searchService.globalSearch', () => {
  it('gives the groups of the envelope the server answers', async () => {
    const groups = { certificates: [{ id: 224, name: 'web.example.com' }], cas: [], users: [], templates: [] }
    get.mockResolvedValue({ data: groups })
    await expect(searchService.globalSearch('web', 5)).resolves.toEqual(groups)
    expect(get).toHaveBeenCalledWith('/search?q=web&limit=5')
  })

  it('asks nothing under two characters, and answers the empty groups the server would', async () => {
    // The groups of GET /search (api/v2/search.py): it has no CSR group
    await expect(searchService.globalSearch('w')).resolves.toEqual({
      certificates: [], cas: [], users: [], templates: [], acme_accounts: [], scep_profiles: [],
    })
    expect(get).not.toHaveBeenCalled()
  })
})
