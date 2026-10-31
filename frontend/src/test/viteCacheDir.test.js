/**
 * Each checkout keeps its own vite and vitest cache: node_modules may be a link
 * shared between checkouts, and suites running side by side then overwrite each other's.
 */
import { describe, it, expect } from 'vitest'
import { execFileSync } from 'child_process'
import fs from 'fs'
import path from 'path'

const frontendDir = path.resolve(__dirname, '../..')

// Resolved by vite itself, in a plain node process (esbuild refuses to load under jsdom)
function resolvedCacheDir(configFile) {
  const script = `
    const { resolveConfig } = await import('vite')
    const c = await resolveConfig({ configFile: ${JSON.stringify(configFile)}, logLevel: 'silent' }, 'serve', 'test')
    process.stdout.write(c.cacheDir)`
  return execFileSync(process.execPath, ['--input-type=module', '-e', script], { cwd: frontendDir, encoding: 'utf8' })
}

describe.each(['vite.config.js', 'vitest.config.js'])('%s', (configFile) => {
  it('keeps its cache in this checkout, outside node_modules', () => {
    const dir = resolvedCacheDir(path.join(frontendDir, configFile))
    expect(path.relative(frontendDir, dir).split(path.sep)).not.toContain('node_modules')
    // the cache's parent must be the checkout itself, not a link out of it
    expect(fs.realpathSync(path.dirname(dir))).toBe(fs.realpathSync(frontendDir))
  }, 20000)
})
