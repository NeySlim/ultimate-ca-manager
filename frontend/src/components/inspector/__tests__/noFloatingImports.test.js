/**
 * The detail-window modules are no longer imported by the application: the
 * inspector replaced them. Their files stay until A-08 deletes them.
 * ui/FloatingWindow and useFloatingWindow are not in that set: the help panel
 * and the email template editor still use them.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'

const SRC = join(__dirname, '../../..')
const LEGACY = {
  'components/FloatingDetailWindow.jsx': /\bFloatingDetailWindow\b/,
  'components/DetailWindowLayer.jsx': /\bDetailWindowLayer\b/,
  'contexts/WindowManagerContext.jsx': /\bWindowManagerContext\b|\buseWindowManager\b|\bWindowManagerProvider\b/,
}

function sources(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) { if (name !== '__tests__' && name !== 'node_modules') sources(p, out) }
    else if (/\.(jsx?|tsx?)$/.test(name) && !/\.test\./.test(name)) out.push(p)
  }
  return out
}

// Whole import/export-from statements and dynamic imports, however many lines they span
export function importStatements(text) {
  return text.match(/\b(?:import|export)\b[^;'"`]*?\bfrom\s*['"][^'"]+['"]|\bimport\s*\(?\s*['"][^'"]+['"]/g) || []
}

describe('import statement scanner', () => {
  it('sees a multi-line import and a dynamic one, not a bare mention', () => {
    const text = "import {\n  useWindowManager,\n} from '../contexts'\nconst x = import('./Foo')\n// useWindowManager"
    const found = importStatements(text)
    expect(found).toHaveLength(2)
    expect(LEGACY['contexts/WindowManagerContext.jsx'].test(found[0])).toBe(true)
  })
})

describe('legacy detail windows', () => {
  const files = sources(SRC).map((p) => [relative(SRC, p), readFileSync(p, 'utf8')])

  it.each(Object.entries(LEGACY))('%s is imported by no live module', (legacy, pattern) => {
    const users = files
      .filter(([rel]) => !Object.keys(LEGACY).includes(rel))
      .filter(([, text]) => importStatements(text).some((st) => pattern.test(st)))
      .map(([rel]) => rel)
    expect(users).toEqual([])
  })

  it.each(['ui/FloatingWindow.jsx', 'hooks/useFloatingWindow.js'])(
    'keeps %s out of the legacy set while a live module imports it', (shared) => {
      const name = shared.split('/').pop().replace(/\.jsx?$/, '')
      const users = files
        .filter(([rel]) => !Object.keys(LEGACY).includes(rel) && rel !== shared)
        .filter(([, text]) => importStatements(text).some((st) => new RegExp(`/${name}['"]`).test(st)))
      expect(users.length).toBeGreaterThan(0)
      expect(Object.keys(LEGACY)).not.toContain(shared)
    })
})
