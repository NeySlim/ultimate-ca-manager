import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// The Playwright harness touches only an instance scripts/ci/e2e.sh started (UCM_E2E_MANAGED=1)
const calls = []
vi.mock('@playwright/test', async (importOriginal) => ({
  ...(await importOriginal()),
  request: {
    newContext: vi.fn(async () => ({
      post: async (url) => { calls.push(['POST', url]); return { ok: () => true, status: () => 200, json: async () => ({ data: { csrf_token: 't' } }) } },
      fetch: async (url, opts) => {
        calls.push([opts.method, url])
        return { ok: () => true, status: () => 200, headers: () => ({ 'content-type': 'application/json' }), json: async () => ({ data: {} }) }
      },
      dispose: async () => {},
    })),
  },
}))

// jsdom gives import.meta.url a non-file scheme: api.ts reads VERSION through this stand-in
const fsStandIn = vi.hoisted(() => async (importOriginal) => {
  const fs = await importOriginal()
  const readFileSync = (p, ...rest) => (String(p).endsWith('/VERSION') ? '3.0-test\n' : fs.readFileSync(p, ...rest))
  return { ...fs, default: { ...fs, readFileSync }, readFileSync }
})
vi.mock('node:fs', fsStandIn)
vi.mock('fs', fsStandIn)

const VARS = ['UCM_E2E_MANAGED', 'UCM_LAB', 'UCM_E2E_BASE_URL', 'UCM_BASE_URL', 'UCM_E2E_ADMIN_PASSWORD', 'UCM_PASSWORD']
let saved

function setEnv(env) {
  VARS.forEach((k) => delete process.env[k])
  Object.assign(process.env, env)
}

async function loadConfig(env) {
  setEnv(env)
  vi.resetModules()
  return (await import('../../playwright.config.ts')).default
}

async function runSetup(env) {
  setEnv(env)
  vi.resetModules()
  const setup = (await import('../../e2e/support/global-setup.ts')).default
  await setup({ projects: [{ use: { baseURL: 'https://127.0.0.1:1' } }] })
}

describe('end-to-end harness', () => {
  beforeEach(() => {
    saved = Object.fromEntries(VARS.map((k) => [k, process.env[k]]))
    VARS.forEach((k) => delete process.env[k])
    calls.length = 0
  })
  afterEach(() => {
    VARS.forEach((k) => (saved[k] === undefined ? delete process.env[k] : (process.env[k] = saved[k])))
  })

  it('runs the overview tests alone, after the others and before the restore', async () => {
    const { projects } = await loadConfig({ UCM_E2E_MANAGED: '1' })
    const by = Object.fromEntries(projects.map((p) => [p.name, p]))
    const file = 'e2e/overview.spec.ts'
    expect(by.chromium.testIgnore.some((re) => re instanceof RegExp && re.test(file))).toBe(true)
    expect(by.overview.testMatch.some((re) => re.test(file))).toBe(true)
    expect(by.overview.dependencies).toEqual(['chromium'])
    expect(by.overview.fullyParallel).toBe(false)
    expect(by.restore.dependencies).toEqual(['overview'])
  })

  it('runs the restore project only against the instance the script started', async () => {
    const names = (c) => c.projects.map((p) => p.name)
    expect(names(await loadConfig({ UCM_E2E_MANAGED: '1' }))).toContain('restore')
    expect(names(await loadConfig({}))).not.toContain('restore')
    expect(names(await loadConfig({ UCM_E2E_MANAGED: '1', UCM_LAB: '1' }))).not.toContain('restore')
  })

  it('no longer reads the legacy UCM_BASE_URL and UCM_PASSWORD', async () => {
    const config = await loadConfig({ UCM_BASE_URL: 'https://lab.example.test:8443', UCM_PASSWORD: 'x' })
    expect(config.use.baseURL).toBeUndefined()
    const api = await import('../../e2e/support/api.ts')
    expect(api.ADMIN_PASSWORD).toBe('')
  })

  it('leaves an instance it did not start untouched', async () => {
    await runSetup({ UCM_LAB: '1' })
    expect(calls).toEqual([])
  })

  it('leaves a lab instance untouched even with the managed flag set by hand', async () => {
    await runSetup({ UCM_E2E_MANAGED: '1', UCM_LAB: '1' })
    expect(calls).toEqual([])
  })

  it('sets the protocol URL on its own instance', async () => {
    await runSetup({ UCM_E2E_MANAGED: '1' })
    expect(calls).toContainEqual(['PATCH', '/api/v2/settings/general'])
  })
})
