/**
 * The floating-window modules are no longer imported by the application: the
 * inspector replaced them. Their files stay until they are deleted.
 * ui/FloatingWindow is still used by the two non-detail windows below.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'

const SRC = join(__dirname, '../../..')
const LEGACY = {
  'components/FloatingDetailWindow.jsx': /\bFloatingDetailWindow\b/,
  'components/DetailWindowLayer.jsx': /\bDetailWindowLayer\b/,
  'contexts/WindowManagerContext.jsx': /\bWindowManagerContext\b|\buseWindowManager\b|\bWindowManagerProvider\b/,
  'hooks/useFloatingWindow.js': /\buseFloatingWindow\b/,
  'components/ui/FloatingWindow.jsx': /\/FloatingWindow['"]/,
}
const ALLOWED = { 'components/ui/FloatingWindow.jsx': ['components/EmailTemplateWindow.jsx', 'components/ui/FloatingHelpPanel.jsx'] }

function sources(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) { if (name !== '__tests__' && name !== 'node_modules') sources(p, out) }
    else if (/\.(jsx?|tsx?)$/.test(name) && !/\.test\./.test(name)) out.push(p)
  }
  return out
}

describe('legacy floating windows', () => {
  const files = sources(SRC).map((p) => [relative(SRC, p), readFileSync(p, 'utf8')])

  it.each(Object.entries(LEGACY))('%s is imported by no live module', (legacy, pattern) => {
    const users = files
      .filter(([rel]) => !Object.keys(LEGACY).includes(rel) && !(ALLOWED[legacy] || []).includes(rel))
      .filter(([, text]) => text.split('\n').some((l) => /['"]/.test(l) && /\bfrom\b|^\s*import\b|\bimport\(/.test(l) && pattern.test(l)))
      .map(([rel]) => rel)
    expect(users).toEqual([])
  })
})
