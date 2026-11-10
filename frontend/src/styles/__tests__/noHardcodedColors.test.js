/**
 * No colour literal and no Tailwind palette class in src/**: colours come from
 * styles/tokens.css. Every exception below must still match something, so the list cannot rot.
 */
import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'

const SRC = path.resolve(__dirname, '../..')

const PALETTES = 'slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose'
const UTILS = 'text|bg|border|ring|fill|stroke|from|to|via|divide|outline|shadow|placeholder|accent|decoration|caret'
const FORBIDDEN = [
  /(?<![\w&])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![\w-])/g,
  /\b(?:rgba?|hsla?)\(\s*\d/g,
  new RegExp(`(?<![\\w-])(?:[a-z]+:)*(?:${UTILS})-(?:(?:${PALETTES})-\\d{2,3}|white|black)(?:/\\d+)?(?![\\w-])`, 'g'),
]

// file (relative to src), regexp of the literals it may keep, reason.
export const EXCEPTIONS = [
  { file: 'styles/tokens.css', match: /./, reason: 'the token definitions themselves' },
  { file: 'components/ProviderIcons.jsx', match: /./, reason: 'third-party brand colours' },
  { file: 'contexts/ThemeContext.jsx', match: /#[0-9a-fA-F]{6}/, reason: 'theme picker swatches show a theme other than the active one' },
  { file: 'components/ui/FloatingHelpPanel.jsx', match: /#[0-9a-fA-F]{6}/, reason: 'fixed sepia reading palette of the help reader' },
  { file: 'components/EmailTemplateWindow.jsx', match: /#f4f5f7/i, reason: 'email preview canvas imitates a mail client' },
  { file: 'index.css', match: /#(?:FF5E5B|D63B36|B8312C)/i, reason: 'Ko-fi brand colours' },
]

// In-app help is prose (it quotes issue numbers such as "#221"), not styling.
const SKIP_DIRS = new Set(['__tests__', 'help'])
const SKIP_FILES = new Set(['helpContent.js'])

function walk(dir, out = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) {
      if (!SKIP_DIRS.has(e.name)) walk(p, out)
    } else if (/\.(js|jsx|css)$/.test(e.name) && !/\.test\./.test(e.name) && !SKIP_FILES.has(e.name)) out.push(p)
  }
  return out
}

// Comments carry issue references such as "#345": drop them before scanning.
function stripComments(text, isCss) {
  let out = text.replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, ' '))
  if (!isCss) out = out.replace(/(^|[^:\\'"`])\/\/[^\n]*/g, '$1')
  return out
}

export function scan(text, isCss) {
  const clean = stripComments(text, isCss)
  return FORBIDDEN.flatMap((re) => [...clean.matchAll(re)].map((m) => m[0]))
}

const files = walk(SRC).map((f) => ({ rel: path.relative(SRC, f).split(path.sep).join('/'), abs: f }))

describe('no hardcoded colours', () => {
  it('finds source files to scan', () => {
    expect(files.length).toBeGreaterThan(100)
  })

  it('detects what it forbids', () => {
    expect(scan('const a = "#ff0000"', false)).toEqual(['#ff0000'])
    expect(scan('<p className="text-red-500 hover:bg-gray-800">', false)).toHaveLength(2)
    expect(scan('x { color: rgba(0,0,0,.5) }', true)).toHaveLength(1)
    expect(scan('// see #345\n/* #123 */ ok', false)).toEqual([])
    expect(scan('bg-status-danger text-on-accent icon-bg-blue', false)).toEqual([])
  })

  it('has no literal outside the exception list', () => {
    const offenders = []
    for (const f of files) {
      const exc = EXCEPTIONS.find((e) => e.file === f.rel)
      const hits = scan(fs.readFileSync(f.abs, 'utf8'), f.rel.endsWith('.css'))
        .filter((h) => !(exc && exc.match.test(h)))
      if (hits.length) offenders.push(`${f.rel}: ${[...new Set(hits)].join(', ')}`)
    }
    expect(offenders).toEqual([])
  })

  it('has no unused exception', () => {
    for (const exc of EXCEPTIONS) {
      const f = files.find((x) => x.rel === exc.file)
      expect(f, `${exc.file} no longer exists`).toBeTruthy()
      const hits = scan(fs.readFileSync(f.abs, 'utf8'), f.rel.endsWith('.css')).filter((h) => exc.match.test(h))
      expect(hits.length, `${exc.file} no longer needs its exception`).toBeGreaterThan(0)
      expect(exc.reason.length).toBeGreaterThan(10)
    }
  })
})
