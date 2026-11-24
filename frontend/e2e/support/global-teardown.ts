import { rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { basename, dirname, resolve } from 'node:path'
import { SEED_DIR_ENV, SEED_DIR_PREFIX } from './api'

// The run's seed directory (global-setup), and nothing else, is removed
export default async function globalTeardown() {
  const dir = process.env[SEED_DIR_ENV]
  if (!dir || dirname(resolve(dir)) !== resolve(tmpdir()) || !basename(dir).startsWith(SEED_DIR_PREFIX)) return
  rmSync(dir, { recursive: true, force: true })
}
