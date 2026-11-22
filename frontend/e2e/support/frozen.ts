import type { BrowserContext, Page } from '@playwright/test'

type Kept = { status: number, headers: Record<string, string>, body: Buffer }
export type Frozen = Map<string, Kept>

// The session and the account's own state are read live: a replayed one would carry another session's token
const LIVE = /\/api\/v2\/(auth|account)\//

/**
 * Every GET of the API answered, after its first time, as it was then (across the pages and contexts given the same
 * `kept`): a geometry measured twice reads the same counters, not the certificates other tests issue meanwhile.
 */
export async function freezeApi(target: Page | BrowserContext, kept: Frozen = new Map()) {
  await target.route('**/api/v2/**', async (route) => {
    const request = route.request()
    if (request.method() !== 'GET' || LIVE.test(request.url())) return route.fallback()
    const seen = kept.get(request.url())
    if (seen) return route.fulfill(seen)
    const response = await route.fetch()
    const headers = { ...response.headers() }
    // The body is kept decoded: its encoding and length headers would no longer describe it
    for (const h of ['content-encoding', 'content-length', 'transfer-encoding']) delete headers[h]
    const answer = { status: response.status(), headers, body: await response.body() }
    if (response.ok()) kept.set(request.url(), answer)
    return route.fulfill(answer)
  })
  return kept
}
