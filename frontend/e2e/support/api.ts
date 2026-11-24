import { createHmac } from 'node:crypto'
import { mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import type { APIRequestContext, APIResponse } from '@playwright/test'
import { strongPassword } from './password'

export const ADMIN_USER = 'admin'
export const ADMIN_PASSWORD = process.env.UCM_E2E_ADMIN_PASSWORD || ''

export class ApiError extends Error {
  constructor(public status: number, public body: unknown, what: string) {
    super(`${what}: HTTP ${status} ${JSON.stringify(body).slice(0, 500)}`)
  }
}

/** The server's answer to a write that met another one on SQLite (contracts/database_busy.json). */
export const BUSY_PROBLEM = 'urn:ucm:problem:database-busy'
export const BUSY_MESSAGE = 'The database is busy with another write: retry shortly.'

export type Backoff = { delays: readonly number[], sleep: (ms: number) => Promise<void> }
/** Five more attempts at most, the waits doubling, each one no longer than the answer's Retry-After. */
export const BUSY_BACKOFF: Backoff = { delays: [250, 500, 1000, 2000, 4000], sleep: (ms) => new Promise((r) => setTimeout(r, ms)) }

type Read = { status: number, ok: boolean, body: any, headers: Record<string, string> }

async function read(r: APIResponse): Promise<Read> {
  const type = r.headers()['content-type'] || ''
  const body = type.includes('json') ? await r.json() : await r.text()
  return { status: r.status(), ok: r.ok(), body, headers: r.headers() }
}

/** Only the busy answer of the server is sent again, known by its type (its text from a server
 * that sends none); any other 503 (restore, CRL) is the test's. */
export function isBusy(r: { status: number, body: unknown }) {
  if (r.status !== 503 || !r.body || typeof r.body !== 'object') return false
  const { type, detail } = r.body as { type?: unknown, detail?: unknown }
  return type === BUSY_PROBLEM || ((!type || type === 'about:blank') && detail === BUSY_MESSAGE)
}

async function untilNotBusy(what: string, send: () => Promise<APIResponse>, backoff: Backoff): Promise<Read> {
  let r = await read(await send())
  for (const delay of backoff.delays) {
    if (!isBusy(r)) break
    const after = Number(r.headers['retry-after'])
    const wait = Number.isFinite(after) && after >= 0 ? Math.min(delay, after * 1000) : delay
    console.log(`E2E busy: ${what} answered 503 busy, sent again in ${wait} ms`)
    await backoff.sleep(wait)
    r = await read(await send())
  }
  return r
}

/** The JSON API with the session of the page it was opened from (cookies are shared). */
export class Api {
  constructor(private request: APIRequestContext, private csrf: string, private backoff: Backoff = BUSY_BACKOFF) {}

  static async login(request: APIRequestContext, username: string, password: string, backoff: Backoff = BUSY_BACKOFF): Promise<Api> {
    const r = await untilNotBusy(`login ${username}`, () => request.post('/api/v2/auth/login', { data: { username, password } }), backoff)
    const body = r.body && typeof r.body === 'object' ? r.body as { data?: { csrf_token?: string } } : {}
    if (!r.ok) throw new ApiError(r.status, r.body, `login ${username}`)
    return new Api(request, body?.data?.csrf_token || '', backoff)
  }

  async call(method: string, path: string, data?: unknown, okOnly = true) {
    const r = await untilNotBusy(`${method} ${path}`, () => this.request.fetch(`/api/v2${path}`, {
      method,
      headers: { 'X-CSRF-Token': this.csrf },
      ...(data === undefined ? {} : { data }),
    }), this.backoff)
    if (okOnly && !r.ok) throw new ApiError(r.status, r.body, `${method} ${path}`)
    return { status: r.status, body: r.body, headers: r.headers }
  }

  async get(path: string) { return (await this.call('GET', path)).body?.data }
  async post(path: string, data: unknown = {}) { return (await this.call('POST', path, data)).body?.data }
  async put(path: string, data: unknown = {}) { return (await this.call('PUT', path, data)).body?.data }
  async patch(path: string, data: unknown = {}) { return (await this.call('PATCH', path, data)).body?.data }
  async del(path: string) { return (await this.call('DELETE', path)).body?.data }
  async status(method: string, path: string, data?: unknown) { return (await this.call(method, path, data, false)).status }
}

const VERSION = readFileSync(new URL('../../../VERSION', import.meta.url), 'utf8').trim()

/** The support card shown to administrators once per version is marked as seen. */
export async function dismissSupportCard(api: Api) {
  const prefs = (await api.get('/account/preferences')) || {}
  if (prefs.kofi_seen_version !== VERSION) await api.put('/account/preferences', { ...prefs, kofi_seen_version: VERSION })
}

/** The directory of this run's shared seeds (global-setup sets it, the workers inherit it). */
export const SEED_DIR_ENV = 'UCM_E2E_SEED_DIR'

/**
 * `make` run once per run of the suite, by whichever worker asks first; the others wait for its
 * JSON result. A seed per test made the shared base, and the restore that replays it, grow without end.
 */
export async function seedOnce<T>(name: string, make: () => Promise<T>, waitMs = 120_000): Promise<T> {
  const dir = process.env[SEED_DIR_ENV]
  if (!dir) return make()
  const done = join(dir, `${name}.json`)
  const lock = join(dir, `${name}.lock`)
  const until = Date.now() + waitMs
  for (;;) {
    try {
      return JSON.parse(readFileSync(done, 'utf8'))
    } catch { /* not made yet */ }
    try {
      mkdirSync(lock)
    } catch {
      if (Date.now() > until) throw new Error(`seed ${name}: another worker is still making it`)
      await new Promise((r) => setTimeout(r, 200))
      continue
    }
    // Made under the lock, published whole; a failed make leaves the lock to the next worker
    try {
      const made = await make()
      writeFileSync(`${done}.tmp`, JSON.stringify(made ?? null))
      renameSync(`${done}.tmp`, done)
      return made
    } finally {
      rmSync(lock, { recursive: true, force: true })
    }
  }
}

/** A short unique suffix: every test names its own objects. */
export function uid(prefix = 'e2e') {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

/** A root CA (or, with `parentCAId`, an intermediate) created through the API. */
export async function createCA(api: Api, extra: Record<string, unknown> = {}) {
  const intermediate = 'parentCAId' in extra
  return api.post('/cas', {
    type: intermediate ? 'intermediate' : 'root',
    commonName: uid(intermediate ? 'int' : 'root'),
    keyAlgo: 'RSA', keySize: 2048, validityYears: 5,
    ...extra,
  })
}

/** A server certificate issued by `caId` through the API. */
export async function issueCert(api: Api, caId: number, extra: Record<string, unknown> = {}) {
  return api.post('/certificates', { cn: `${uid('cert')}.example.com`, ca_id: caId, validity_days: 90, ...extra })
}

export { strongPassword }

/** A local user created by the administrator; returns its name and password. */
export async function createUser(api: Api, role: string) {
  const username = uid(role).replace(/-/g, '_')
  const password = strongPassword()
  const user = await api.post('/users', { username, password, email: `${username}@example.test`, role })
  return { id: user.id as number, username, password }
}

/** True when DER `crl` lists `serialHex` (a DER INTEGER with that value). */
export function derHasSerial(der: Buffer, serialHex: string) {
  let hex = serialHex.replace(/[^0-9a-f]/gi, '').toLowerCase().replace(/^(00)+(?=..)/, '')
  if (hex.length % 2) hex = '0' + hex
  let value = Buffer.from(hex, 'hex')
  if (value[0] & 0x80) value = Buffer.concat([Buffer.from([0]), value])
  return der.includes(Buffer.concat([Buffer.from([0x02, value.length]), value]))
}

export function pemBody(pem: string) {
  return Buffer.from(pem.replace(/-----[^-]+-----/g, '').replace(/\s+/g, ''), 'base64')
}

/** RFC 6238 TOTP (SHA-1, 30 s, 6 digits) of a base32 secret. */
export function totp(secret: string, at = Date.now()) {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
  let bits = ''
  for (const c of secret.replace(/=+$/, '').toUpperCase()) bits += alphabet.indexOf(c).toString(2).padStart(5, '0')
  const key = Buffer.from(bits.match(/.{8}/g)!.map(b => parseInt(b, 2)))
  const counter = Buffer.alloc(8)
  counter.writeBigUInt64BE(BigInt(Math.floor(at / 30000)))
  const mac = createHmac('sha1', key).update(counter).digest()
  const offset = mac[mac.length - 1] & 0xf
  return String((mac.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).padStart(6, '0')
}
