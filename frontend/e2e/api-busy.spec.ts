import { test, expect } from '@playwright/test'
import type { APIRequestContext } from '@playwright/test'
import { Api, ApiError, BUSY_MESSAGE } from './support/api'

// The seeding API sends again the server's « busy, retry shortly » answer, and only that one, a bounded
// number of times: checked on a stand-in for the request context, no browser and no instance needed
const problem = (detail: string) => ({ status: 503, json: { type: 'about:blank', title: 'Service Unavailable', status: 503, detail } })
const BUSY = { ...problem(BUSY_MESSAGE), retryAfter: '5' }
const OK = { status: 200, json: { data: { id: 7, csrf_token: 'tok' } } }
type Answer = { status: number, json?: unknown, text?: string, retryAfter?: string }

function standIn(answers: Answer[]) {
  const sent: string[] = []
  const answer = (what: string) => {
    sent.push(what)
    const a = answers[Math.min(sent.length - 1, answers.length - 1)]
    const headers: Record<string, string> = { 'content-type': a.json !== undefined ? 'application/problem+json' : 'text/plain' }
    if (a.retryAfter) headers['retry-after'] = a.retryAfter
    return Promise.resolve({
      status: () => a.status, ok: () => a.status < 400, headers: () => headers,
      json: () => Promise.resolve(a.json), text: () => Promise.resolve(a.text ?? ''),
    })
  }
  const request = {
    fetch: (url: string, options: { method: string }) => answer(`${options.method} ${url}`),
    post: (url: string) => answer(`POST ${url}`),
  } as unknown as APIRequestContext
  return { request, sent }
}

function clock() {
  const waits: number[] = []
  return { waits, backoff: { delays: [250, 500, 1000, 2000, 4000], sleep: async (ms: number) => { waits.push(ms) } } }
}

test('a busy answer is sent again until the write goes through', async () => {
  const { request, sent } = standIn([BUSY, BUSY, OK])
  const { waits, backoff } = clock()
  const api = new Api(request, 'tok', backoff)
  expect(await api.post('/csrs/3/sign', { ca_id: 1 })).toEqual({ id: 7, csrf_token: 'tok' })
  expect(sent).toEqual(Array(3).fill('POST /api/v2/csrs/3/sign'))
  expect(waits).toEqual([250, 500])
})

test('the waits stop at the bound, and the last busy answer is the error', async () => {
  const { request, sent } = standIn([BUSY])
  const { waits, backoff } = clock()
  const error = await new Api(request, 'tok', backoff).post('/certificates').catch((e) => e)
  expect(error).toBeInstanceOf(ApiError)
  expect(error.status).toBe(503)
  expect(sent).toHaveLength(6)
  expect(waits).toEqual([250, 500, 1000, 2000, 4000])
})

test('no wait is longer than the Retry-After of the answer', async () => {
  const { request } = standIn([{ ...BUSY, retryAfter: '1' }])
  const { waits, backoff } = clock()
  await new Api(request, 'tok', backoff).status('POST', '/certificates')
  expect(waits).toEqual([250, 500, 1000, 1000, 1000])
})

test('any other 503 is the test\'s own: neither a restore holding the database nor a plain-text one is sent again', async () => {
  for (const other of [
    problem('This UCM instance is restoring a backup and its transaction holds the database: only the health checks and the restore job are served until it ends. Retry later.'),
    { status: 503, text: BUSY_MESSAGE },
    { status: 500, json: { detail: BUSY_MESSAGE } },
  ]) {
    const { request, sent } = standIn([other, OK])
    const { waits, backoff } = clock()
    const api = new Api(request, 'tok', backoff)
    expect(await api.status('GET', '/crl/1')).toBe(other.status)
    expect(sent).toHaveLength(1)
    expect(waits).toEqual([])
  }
})

test('the sign-in is sent again on a busy answer too', async () => {
  const { request, sent } = standIn([BUSY, OK])
  const { waits, backoff } = clock()
  const api = await Api.login(request, 'admin', 'secret', backoff)
  expect(sent).toEqual(['POST /api/v2/auth/login', 'POST /api/v2/auth/login'])
  expect(waits).toEqual([250])
  // The session it opens keeps the same bound
  const { request: busy } = standIn([BUSY])
  Object.assign(api, { request: busy })
  await api.status('GET', '/certificates')
  expect(waits).toEqual([250, 250, 500, 1000, 2000, 4000])
})
