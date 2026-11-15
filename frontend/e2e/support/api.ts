import { createHmac } from 'node:crypto'
import { readFileSync } from 'node:fs'
import type { APIRequestContext } from '@playwright/test'

export const ADMIN_USER = 'admin'
export const ADMIN_PASSWORD = process.env.UCM_E2E_ADMIN_PASSWORD || ''

export class ApiError extends Error {
  constructor(public status: number, public body: unknown, what: string) {
    super(`${what}: HTTP ${status} ${JSON.stringify(body).slice(0, 500)}`)
  }
}

/** The JSON API with the session of the page it was opened from (cookies are shared). */
export class Api {
  constructor(private request: APIRequestContext, private csrf: string) {}

  static async login(request: APIRequestContext, username: string, password: string): Promise<Api> {
    const r = await request.post('/api/v2/auth/login', { data: { username, password } })
    const body = await r.json().catch(() => ({}))
    if (!r.ok()) throw new ApiError(r.status(), body, `login ${username}`)
    return new Api(request, body?.data?.csrf_token || '')
  }

  async call(method: string, path: string, data?: unknown, okOnly = true) {
    const r = await this.request.fetch(`/api/v2${path}`, {
      method,
      headers: { 'X-CSRF-Token': this.csrf },
      ...(data === undefined ? {} : { data }),
    })
    const type = r.headers()['content-type'] || ''
    const body = type.includes('json') ? await r.json() : await r.text()
    if (okOnly && !r.ok()) throw new ApiError(r.status(), body, `${method} ${path}`)
    return { status: r.status(), body, headers: r.headers() }
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

export function strongPassword() {
  return `E2e!${Math.random().toString(36).slice(2, 10)}${Date.now().toString(36)}Qz9`
}

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
