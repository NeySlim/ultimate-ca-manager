import { describe, it, expect, vi } from 'vitest'
import { fetchAllPages } from '../fetchAllPages'

const pageOf = (page, perPage, total) => ({
  data: Array.from({ length: Math.max(0, Math.min(perPage, total - (page - 1) * perPage)) }, (_, i) => ({ id: (page - 1) * perPage + i + 1 })),
  meta: { total },
})

describe('fetchAllPages', () => {
  it('walks every page of a listing', async () => {
    const getPage = vi.fn(({ page, per_page }) => Promise.resolve(pageOf(page, per_page, 250)))
    const rows = await fetchAllPages(getPage)
    expect(rows).toHaveLength(250)
    expect(getPage).toHaveBeenCalledTimes(3)
    expect(getPage.mock.calls.map(([q]) => q)).toEqual([
      { per_page: 100, page: 1 }, { per_page: 100, page: 2 }, { per_page: 100, page: 3 },
    ])
  })

  it('stops at the cap however large the listing', async () => {
    const getPage = vi.fn(({ page, per_page }) => Promise.resolve(pageOf(page, per_page, 10000)))
    const rows = await fetchAllPages(getPage)
    expect(getPage).toHaveBeenCalledTimes(5)
    expect(rows).toHaveLength(500)
  })

  it('reads one page when the listing reports no total', async () => {
    const getPage = vi.fn(() => Promise.resolve({ data: [{ id: 1 }] }))
    expect(await fetchAllPages(getPage)).toEqual([{ id: 1 }])
    expect(getPage).toHaveBeenCalledTimes(1)
  })
})
