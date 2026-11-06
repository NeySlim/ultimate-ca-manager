const RATE_LIMITED = 429
const MAX_RETRY_WAIT_S = 60

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

// A page answered 429 is tried again after its Retry-After (1 s without one)
async function withRetry(load, attempts, wait) {
  for (let attempt = 1; ; attempt += 1) {
    try {
      return await load()
    } catch (error) {
      if (error?.status !== RATE_LIMITED || attempt >= attempts) throw error
      const seconds = Number.isFinite(error.retryAfter) ? error.retryAfter : 1
      await wait(Math.min(Math.max(seconds, 0), MAX_RETRY_WAIT_S) * 1000)
    }
  }
}

// Walk a listing that pages on page/per_page, up to `max` rows, `concurrency` pages at a time.
// A page that fails for good is left out: `complete` is false and `total` says how many rows exist.
export async function fetchPages(getPage, { perPage = 100, max = 500, concurrency = 4, attempts = 3, wait = sleep } = {}) {
  const query = { per_page: perPage }
  const load = (page) => withRetry(() => getPage({ ...query, page }), attempts, wait)
  const first = await load(1)
  const rows = [...(first.data || [])]
  const total = Math.min(first.meta?.total ?? rows.length, max)
  const pages = Math.ceil(total / perPage)
  let failed = 0
  for (let start = 2; start <= pages; start += concurrency) {
    const batch = Array.from({ length: Math.min(concurrency, pages - start + 1) }, (_, k) => start + k)
    const results = await Promise.allSettled(batch.map(load))
    for (const result of results) {
      if (result.status === 'fulfilled') rows.push(...(result.value.data || []))
      else failed += 1
    }
  }
  return { rows, total, complete: failed === 0 }
}

// Every row or an error: for the callers that cannot show a partial listing
export async function fetchAllPages(getPage, options) {
  const { rows, complete } = await fetchPages(getPage, options)
  if (!complete) throw new Error('Some pages of the listing could not be loaded')
  return rows
}
