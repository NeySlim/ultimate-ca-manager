/**
 * No colour literal and no Tailwind palette class in src/**: colours come from
 * styles/tokens.css. Every exception below must still match something, so the list cannot rot.
 */
import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'

const SRC = path.resolve(__dirname, '../..')

const PALETTES = 'slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose'
const UTILS = 'text|bg|border(?:-[trblxyse])?|ring(?:-offset)?|fill|stroke|from|to|via|divide(?:-[xy])?|outline|shadow|placeholder|accent|decoration|caret'
const NAMED = 'white|black|red|green|blue|yellow|orange|purple|pink|gray|grey|silver|navy|teal|cyan|magenta|lime|maroon|olive|aqua|fuchsia'
const FORBIDDEN = [
  /(?<![\w&])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![\w-])/g,
  /\b(?:rgba?|hsla?)\(\s*\d/g,
  new RegExp(`(?<![\\w-])(?:[a-z]+:)*(?:${UTILS})-(?:(?:${PALETTES})-\\d{2,3}|white|black)(?:/\\d+)?(?![\\w-])`, 'g'),
  // Bare HSL components (`220deg 40% 2%`) meant for hsl(var(--x) / a).
  /\b\d+(?:\.\d+)?(?:deg)?\s+\d+(?:\.\d+)?%\s+\d+(?:\.\d+)?%(?!\s*[,)])/g,
]
// Named colours. CSS: any colour property or border shorthand. JS: SVG attributes and style props
// (a bare `color: 'blue'` there is a semantic key, not a colour).
const NAMED_CSS = new RegExp(`(?:color|background|border|fill|stroke|outline|shadow)[a-z-]*\\s*[:=]\\s*\\\\?['"]?(?:${NAMED})['"]?(?![\\w-])|\\b(?:solid|dashed|dotted)\\s+(?:${NAMED})(?![\\w-])`, 'gi')
const NAMED_JS = new RegExp(`\\b(?:fill|stroke|stop-color|flood-color|backgroundColor|borderColor|stopColor)\\s*[:=]\\s*\\{?\\\\?['"](?:${NAMED})['"]`, 'g')

// Exact literals a file may keep (lower case). No file is exempt as a whole except the token file.
export const EXCEPTIONS = [
  { file: 'styles/tokens.css', all: true, reason: 'the token definitions themselves' },
  { file: 'components/ProviderIcons.jsx', all: true, reason: 'third-party brand colours' },
  {
    file: 'contexts/ThemeContext.jsx',
    values: ['#233143', '#94bfff', '#eaf0f6', '#245bb1', '#1a2036', '#a5b4ff', '#eef0f8', '#3742bd',
      '#301e47', '#a855f7', '#e8dff5', '#9a3ff0', '#3a1f16', '#f97316', '#fddcb5', '#cd4d0b'],
    reason: 'theme picker swatches show a theme other than the active one',
  },
  {
    file: 'components/ui/FloatingHelpPanel.jsx',
    values: ['#f4ecd8', '#5b4636', '#d4c5a9', '#ebe0c8', '#8b6914', '#3d2b1f'],
    reason: 'fixed sepia reading palette of the help reader',
  },
  { file: 'components/EmailTemplateWindow.jsx', values: ['#f4f5f7'], reason: 'email preview canvas imitates a mail client' },
  { file: 'index.css', values: ['#ff5e5b', '#d63b36', '#b8312c'], reason: 'Ko-fi brand colours' },
  { file: 'index.css', values: ["stroke='white'"], reason: 'checkmark glyph inside a data URI, which cannot read a token' },
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
  return [...FORBIDDEN, isCss ? NAMED_CSS : NAMED_JS].flatMap((re) => [...clean.matchAll(re)].map((m) => m[0]))
}

const files = walk(SRC).map((f) => ({ rel: path.relative(SRC, f).split(path.sep).join('/'), abs: f }))

const excFor = (rel) => EXCEPTIONS.filter((e) => e.file === rel)
const allowed = (rel, hit) => excFor(rel).some((e) => e.all || e.values.includes(hit.toLowerCase()))
const scanFile = (f) => scan(fs.readFileSync(f.abs, 'utf8'), f.rel.endsWith('.css'))

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
    // Directional and offset utilities.
    expect(scan('border-t-red-500 border-x-blue-400 divide-x-gray-200 divide-y-slate-700 ring-offset-white ring-offset-zinc-900', false)).toHaveLength(6)
    // Named colours and bare HSL components.
    expect(scan('.a { color: white; }', true)).toEqual(['color: white'])
    expect(scan('.a { border: 1px solid black }', true)).toEqual(['solid black'])
    expect(scan('<svg fill="white" /> <b style={{ backgroundColor: \'red\' }} />', false)).toHaveLength(2)
    expect(scan("const kinds = { csr: { color: 'purple' } }; <Chip color=\"blue\" />", false)).toEqual([])
    expect(scan(':root { --c: 220deg 40% 2%; }', true)).toEqual(['220deg 40% 2%'])
    expect(scan('.a { color: var(--white); background: transparent; border-color: currentColor }', true)).toEqual([])
  })

  it('has no literal outside the exception list', () => {
    const offenders = []
    for (const f of files) {
      const hits = scanFile(f).filter((h) => !allowed(f.rel, h))
      if (hits.length) offenders.push(`${f.rel}: ${[...new Set(hits)].join(', ')}`)
    }
    expect(offenders).toEqual([])
  })

  it('exempts no source file as a whole except the token file and the brand icons', () => {
    expect(EXCEPTIONS.filter((e) => e.all).map((e) => e.file).sort())
      .toEqual(['components/ProviderIcons.jsx', 'styles/tokens.css'])
  })

  it('has no unused exception value', () => {
    for (const exc of EXCEPTIONS) {
      const f = files.find((x) => x.rel === exc.file)
      expect(f, `${exc.file} no longer exists`).toBeTruthy()
      expect(exc.reason.length).toBeGreaterThan(10)
      const hits = scanFile(f).map((h) => h.toLowerCase())
      if (exc.all) expect(hits.length, `${exc.file} no longer needs its exception`).toBeGreaterThan(0)
      else for (const v of exc.values) expect(hits, `${exc.file}: ${v} is no longer used`).toContain(v)
    }
  })
})
