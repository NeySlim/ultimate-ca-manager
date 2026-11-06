import { describe, it, expect, vi } from 'vitest'
import { fetchAllPages, fetchPages } from '../fetchAllPages'

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

const rateLimited = (retryAfter) => Object.assign(new Error('Too many requests'), { status: 429, retryAfter })

describe('fetchPages', () => {
  it('loads at most 4 pages at a time', async () => {
    let running = 0
    let peak = 0
    const getPage = vi.fn(async ({ page, per_page }) => {
      running += 1
      peak = Math.max(peak, running)
      await new Promise((r) => setTimeout(r, 1))
      running -= 1
      return pageOf(page, per_page, 1000)
    })
    const { rows, complete } = await fetchPages(getPage, { max: 1000 })
    expect(complete).toBe(true)
    expect(rows).toHaveLength(1000)
    expect(peak).toBe(4)
  })

  it('retries a page answered 429 after its Retry-After', async () => {
    const wait = vi.fn(() => Promise.resolve())
    let refused = 0
    const getPage = vi.fn(({ page, per_page }) => {
      if (page === 2 && refused < 2) { refused += 1; return Promise.reject(rateLimited(refused === 1 ? 3 : undefined)) }
      return Promise.resolve(pageOf(page, per_page, 250))
    })
    const { rows, total, complete } = await fetchPages(getPage, { wait })
    expect(complete).toBe(true)
    expect(total).toBe(250)
    expect(rows.map((r) => r.id)).toEqual(Array.from({ length: 250 }, (_, i) => i + 1))
    expect(wait.mock.calls.map(([ms]) => ms)).toEqual([3000, 1000])
  })

  it('keeps the other pages when one fails for good', async () => {
    const wait = vi.fn(() => Promise.resolve())
    const getPage = vi.fn(({ page, per_page }) =>
      page === 2 ? Promise.reject(rateLimited(0)) : Promise.resolve(pageOf(page, per_page, 250)))
    const { rows, total, complete } = await fetchPages(getPage, { wait })
    expect(complete).toBe(false)
    expect(total).toBe(250)
    expect(rows).toHaveLength(150)
    expect(getPage.mock.calls.filter(([q]) => q.page === 2)).toHaveLength(3)
  })

  it('does not retry another error', async () => {
    const getPage = vi.fn(({ page, per_page }) =>
      page === 3 ? Promise.reject(Object.assign(new Error('boom'), { status: 500 })) : Promise.resolve(pageOf(page, per_page, 250)))
    const { rows, complete } = await fetchPages(getPage, { wait: () => Promise.resolve() })
    expect(complete).toBe(false)
    expect(rows).toHaveLength(200)
    expect(getPage).toHaveBeenCalledTimes(3)
  })

  it('fetchAllPages still fails rather than return a partial listing', async () => {
    const getPage = vi.fn(({ page, per_page }) =>
      page === 2 ? Promise.reject(rateLimited(0)) : Promise.resolve(pageOf(page, per_page, 250)))
    await expect(fetchAllPages(getPage, { wait: () => Promise.resolve() })).rejects.toThrow()
  })
})
