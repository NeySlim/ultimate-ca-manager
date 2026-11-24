import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

// jsdom gives import.meta.url a non-file scheme: api.ts reads VERSION through this stand-in
const fsStandIn = vi.hoisted(() => async (importOriginal) => {
  const fs = await importOriginal()
  const readFileSync = (p, ...rest) => (String(p).endsWith('/VERSION') ? '3.0-test\n' : fs.readFileSync(p, ...rest))
  return { ...fs, default: { ...fs, readFileSync }, readFileSync }
})
vi.mock('node:fs', fsStandIn)
vi.mock('fs', fsStandIn)

// The E2E seeds shared by the tests of a run: made once whatever the workers, never read by another run
describe('seedOnce', () => {
  let dir
  let saved

  beforeEach(() => {
    saved = process.env.UCM_E2E_SEED_DIR
    dir = mkdtempSync(join(tmpdir(), 'seed-once-test-'))
  })

  afterEach(() => {
    if (saved === undefined) delete process.env.UCM_E2E_SEED_DIR
    else process.env.UCM_E2E_SEED_DIR = saved
    rmSync(dir, { recursive: true, force: true })
  })

  it('makes the seed once for callers that ask together, and gives each its result', async () => {
    process.env.UCM_E2E_SEED_DIR = dir
    const { seedOnce } = await import('../../e2e/support/api.ts')
    const make = vi.fn(async () => { await new Promise((r) => setTimeout(r, 300)); return { id: 7 } })
    const results = await Promise.all(Array.from({ length: 5 }, () => seedOnce('lists', make)))
    expect(make).toHaveBeenCalledTimes(1)
    expect(results).toEqual(Array(5).fill({ id: 7 }))
    expect(await seedOnce('lists', make)).toEqual({ id: 7 })
    expect(make).toHaveBeenCalledTimes(1)
  })

  it('leaves a seed that failed to the next caller', async () => {
    process.env.UCM_E2E_SEED_DIR = dir
    const { seedOnce } = await import('../../e2e/support/api.ts')
    await expect(seedOnce('broken', async () => { throw new Error('refused') })).rejects.toThrow('refused')
    expect(await seedOnce('broken', async () => 'made')).toBe('made')
  })

  it('makes it each time without a run directory', async () => {
    delete process.env.UCM_E2E_SEED_DIR
    const { seedOnce } = await import('../../e2e/support/api.ts')
    const make = vi.fn(async () => 1)
    await seedOnce('lists', make)
    await seedOnce('lists', make)
    expect(make).toHaveBeenCalledTimes(2)
  })
})
