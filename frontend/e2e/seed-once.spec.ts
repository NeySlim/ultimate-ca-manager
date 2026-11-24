import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, utimesSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { test, expect } from '@playwright/test'
import { SEED_DIR_ENV, SEED_DIR_PREFIX, seedFs, seedOnce } from './support/api'
import globalTeardown from './support/global-teardown'
import { SEED_WAIT_MS, TEST_TIMEOUT_MS } from './support/timeouts'

// The shared seeds of a run, checked on a directory of their own: no browser and no instance needed
test.describe('seedOnce', () => {
  let dir: string
  let kept: string | undefined
  const real = { ...seedFs }

  test.beforeEach(() => {
    kept = process.env[SEED_DIR_ENV]
    dir = mkdtempSync(join(tmpdir(), 'ucm-seedonce-test-'))
    process.env[SEED_DIR_ENV] = dir
  })

  test.afterEach(() => {
    Object.assign(seedFs, real)
    if (kept === undefined) delete process.env[SEED_DIR_ENV]
    else process.env[SEED_DIR_ENV] = kept
    rmSync(dir, { recursive: true, force: true })
  })

  test('a seed published while the lock was being taken is read, not made again', async () => {
    // Another worker publishes it and lets the lock go between this one's read and its lock
    seedFs.mkdirSync = ((path: string) => {
      writeFileSync(join(dir, 'raced.json'), JSON.stringify({ by: 'other' }))
      return real.mkdirSync(path)
    }) as typeof seedFs.mkdirSync
    let made = 0
    const seed = await seedOnce('raced', async () => { made += 1; return { by: 'me' } })
    expect(seed).toEqual({ by: 'other' })
    expect(made).toBe(0)
    expect(existsSync(join(dir, 'raced.lock'))).toBe(false)
  })

  test('a lock older than a test\'s limit is taken back and the seed made', async () => {
    const lock = join(dir, 'orphan.lock')
    mkdirSync(lock)
    const past = (Date.now() - TEST_TIMEOUT_MS - 5_000) / 1000
    utimesSync(lock, past, past)
    const seed = await seedOnce('orphan', async () => ({ made: true }), { waitMs: 1_000 })
    expect(seed).toEqual({ made: true })
    expect(JSON.parse(readFileSync(join(dir, 'orphan.json'), 'utf8'))).toEqual({ made: true })
    expect(existsSync(lock)).toBe(false)
  })

  test('a lock held by a living maker is waited for, less long than a test may run', async () => {
    mkdirSync(join(dir, 'busy.lock'))
    let made = 0
    await expect(seedOnce('busy', async () => { made += 1 }, { waitMs: 300 })).rejects.toThrow(/still making it/)
    expect(made).toBe(0)
    expect(SEED_WAIT_MS).toBeLessThan(TEST_TIMEOUT_MS)
  })

  test('the teardown removes the run\'s seed directory and nothing else', async () => {
    const run = mkdtempSync(join(tmpdir(), SEED_DIR_PREFIX))
    writeFileSync(join(run, 'x.json'), '{}')
    process.env[SEED_DIR_ENV] = run
    await globalTeardown()
    expect(existsSync(run)).toBe(false)
    // A directory global-setup did not make is left as it is
    process.env[SEED_DIR_ENV] = dir
    await globalTeardown()
    expect(existsSync(dir)).toBe(true)
  })
})
