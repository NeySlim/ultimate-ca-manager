/**
 * The theme is a set of CSS variables written by `ThemeContext` and declared in
 * `index.css`, exposed to Tailwind through `tailwind.config.js`. A class or a
 * `var(--x)` that names a token nobody declared produces no CSS at all: the
 * colour silently does not render, and nothing in the build complains.
 * `DESIGN_SYSTEM.md` documents the tokens this test accepts.
 */
import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'
import tailwindConfig from '../../../tailwind.config.js'

const SRC = path.resolve(__dirname, '../..')
const INDEX_CSS = fs.readFileSync(path.join(SRC, 'index.css'), 'utf8')
const THEME_CONTEXT = fs.readFileSync(path.join(SRC, 'contexts/ThemeContext.jsx'), 'utf8')

function sourceFiles(dir, exts, acc = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name === '__tests__' || entry.name === 'node_modules') continue
      sourceFiles(full, exts, acc)
    } else if (exts.test(entry.name)) {
      acc.push(full)
    }
  }
  return acc
}

function collect(files, regex, pick) {
  const used = new Map()
  for (const file of files) {
    fs.readFileSync(file, 'utf8').split('\n').forEach((line, i) => {
      for (const m of line.matchAll(regex)) {
        const key = pick(m)
        if (key === null) continue
        if (!used.has(key)) used.set(key, [])
        used.get(key).push(`${path.relative(SRC, file)}:${i + 1}`)
      }
    })
  }
  return used
}

function report(used, declared) {
  return [...used.keys()]
    .filter((key) => !declared.has(key))
    .map((key) => `${key} — used at ${used.get(key).slice(0, 5).join(', ')}`)
}

/** `--x:` in index.css or an inline style, plus every key ThemeContext writes with setProperty. */
function declaredVariables(files) {
  const found = new Set()
  for (const file of files) {
    for (const m of fs.readFileSync(file, 'utf8').matchAll(/--([a-zA-Z0-9-]+)['"]?\s*:/g)) found.add(m[1])
  }
  // Only the quoted keys of the dark/light blocks reach setProperty; `id`, `accent`… do not.
  for (const m of THEME_CONTEXT.matchAll(/^\s+'([a-z][a-z0-9-]*)'\s*:/gm)) found.add(m[1])
  // Tailwind's own gradient and ring internals
  found.add('tw-gradient-to').add('tw-gradient-from').add('tw-gradient-stops')
  return found
}

/** Every class selector hand-written in index.css. */
function handWrittenClasses() {
  const found = new Set()
  for (const m of INDEX_CSS.matchAll(/\.((?:[a-zA-Z0-9_-]+\\:)*[a-zA-Z0-9_-]+)/g)) {
    found.add(m[1].replace(/\\/g, ''))
  }
  return found
}

const UTILITIES = '(?:bg|text|border(?:-[lrtbxy])?|ring-offset|ring|divide|from|via|to|outline|fill|stroke|placeholder|caret|decoration)'
const TOKEN = '(?:accent|status|bg|text|border)(?:-[a-z0-9]+)*'
// A colour utility whose colour is one of our token families, with its variants
// (`hover:`) and an optional Tailwind `/opacity` suffix.
const COLOR_CLASS = new RegExp(
  `(?<![a-zA-Z0-9_\\-\\[$])((?:[a-z][a-z0-9-]*:)*)(${UTILITIES}-${TOKEN})(/[0-9]+)?(?![a-zA-Z0-9_\\-\\[$])`,
  'g'
)

describe('design tokens', () => {
  const jsFiles = sourceFiles(SRC, /\.jsx?$/)
  const styleFiles = sourceFiles(SRC, /\.(jsx?|css)$/)

  // A `var(--x, fallback)` renders its fallback, so only the bare form is checked.
  const BARE_VAR = /var\(\s*--([a-zA-Z0-9-]+)\s*\)/g

  it('every var(--x) read in the source is declared by index.css or ThemeContext', () => {
    const used = collect(styleFiles, BARE_VAR, (m) => m[1])
    const undeclared = report(used, declaredVariables(styleFiles))
    expect(
      undeclared,
      `These variables are never set; the colour they promise never renders:\n  ${undeclared.join('\n  ')}`
    ).toEqual([])
  })

  it('every token-coloured class resolves to a Tailwind colour or a hand-written rule', () => {
    const colors = new Set(Object.keys(tailwindConfig.theme.extend.colors))
    const classes = handWrittenClasses()
    const used = collect(jsFiles, COLOR_CLASS, (m) => {
      const [whole, variants, base, opacity] = m
      if (/-op[0-9]+$/.test(base)) return null // covered by opacityClasses.test.js
      // Tailwind cannot apply `/NN` to a var() colour: the class is dropped.
      if (opacity) return whole
      const token = base.replace(new RegExp(`^${UTILITIES}-`), '')
      if (colors.has(token) || classes.has(base) || classes.has(whole)) return null
      return variants + base
    })
    const unresolved = report(used, new Set())
    expect(
      unresolved,
      `These classes produce no CSS; use a declared token or an -opNN helper:\n  ${unresolved.join('\n  ')}`
    ).toEqual([])
  })

  it('scans a non-trivial amount of source, so the checks above cannot silently pass', () => {
    expect(declaredVariables(styleFiles).size).toBeGreaterThan(60)
    expect(handWrittenClasses().size).toBeGreaterThan(200)
    expect(collect(styleFiles, BARE_VAR, (m) => m[1]).size).toBeGreaterThan(50)
    expect(collect(jsFiles, COLOR_CLASS, (m) => m[2]).size).toBeGreaterThan(50)
  })
})
