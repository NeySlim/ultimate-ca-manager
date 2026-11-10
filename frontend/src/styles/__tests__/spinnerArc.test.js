import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'
import postcss from 'postcss'
import tailwindcss from 'tailwindcss'
import tailwindConfig from '../../../tailwind.config.js'

const SRC = path.resolve(__dirname, '../..')

function walk(dir, out = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    if (e.name === '__tests__' || e.name === 'node_modules') continue
    const p = path.join(dir, e.name)
    if (e.isDirectory()) walk(p, out)
    else if (/\.jsx?$/.test(e.name)) out.push(p)
  }
  return out
}

// className={...} expressions: the balanced braces after `className=`.
function braceExpressions(text) {
  const out = []
  for (const m of text.matchAll(/className=\{/g)) {
    let depth = 1
    let i = m.index + m[0].length
    const start = i
    for (; i < text.length && depth > 0; i++) {
      if (text[i] === '{') depth++
      else if (text[i] === '}') depth--
    }
    out.push(text.slice(start, i - 1))
  }
  return out
}

// Spinning elements whose ring uses the on-accent ink, from "literal" and {expression} classNames.
// An expression that interpolates (`${...}`) next to animate-spin cannot be read: it is reported.
export function scanSpinners(text) {
  const found = []
  const unreadable = []
  const lists = [...text.matchAll(/className="([^"]*)"/g)].map((m) => m[1])
  for (const expr of braceExpressions(text)) {
    if (!expr.includes('animate-spin')) continue
    if (expr.includes('${')) unreadable.push(expr.trim())
    lists.push([...expr.matchAll(/(['"`])((?:(?!\1).)*)\1/g)].map((m) => m[2]).join(' '))
  }
  for (const list of lists) {
    if (list.includes('animate-spin') && list.includes('on-accent')) found.push(list.split(/\s+/))
  }
  return { found, unreadable }
}

function onAccentSpinners() {
  const found = []
  const unreadable = []
  for (const file of walk(SRC)) {
    const rel = path.relative(SRC, file)
    const r = scanSpinners(fs.readFileSync(file, 'utf8'))
    found.push(...r.found.map((classes) => ({ file: rel, classes })))
    unreadable.push(...r.unreadable.map((expr) => `${rel}: ${expr}`))
  }
  return { found, unreadable }
}

// Built CSS with the same Tailwind config, scanned over the spinner markup only.
async function buildCss(classes) {
  const css = fs.readFileSync(path.join(SRC, 'index.css'), 'utf8')
  const config = { ...tailwindConfig, content: [{ raw: classes.join(' '), extension: 'html' }], safelist: [] }
  const result = await postcss([tailwindcss(config)]).process(css, { from: path.join(SRC, 'index.css') })
  return result.root
}

// The top value of a border-color shorthand: its first space-separated component outside parentheses.
function firstComponent(value) {
  let depth = 0
  for (let i = 0; i < value.length; i++) {
    if (value[i] === '(') depth++
    else if (value[i] === ')') depth--
    else if (depth === 0 && /\s/.test(value[i])) return value.slice(0, i)
  }
  return value
}

// Single-class rules share specificity 0,1,0, so the last declaration in source order wins.
function effectiveBorderTop(root, classes) {
  let value = null
  root.walkRules((rule) => {
    if (rule.parent.type !== 'root') return
    const hit = rule.selectors.some((s) => {
      const m = /^\.((?:\\.|[\w-])+)$/.exec(s.trim())
      return m && classes.includes(m[1].replace(/\\/g, ''))
    })
    if (!hit) return
    rule.walkDecls((d) => {
      if (d.prop === 'border-top-color' || d.prop === 'border-color') {
        value = d.prop === 'border-color' ? firstComponent(d.value) : d.value
      }
    })
  })
  return value
}

describe('spinner scan', () => {
  it('reads literal, expression, template and cn() classNames', () => {
    const text = [
      '<i className="animate-spin border-on-accent" />',
      "<i className={cn('animate-spin rounded-full', 'border-on-accent', busy && 'x')} />",
      '<i className={`animate-spin border-on-accent ${size}`} />',
      "<i className={busy ? 'animate-spin border-on-accent' : ''} />",
      "<i className={busy ? 'animate-spin' : ''} />",
    ].join('\n')
    const { found, unreadable } = scanSpinners(text)
    expect(found).toHaveLength(4)
    expect(unreadable).toHaveLength(1)
  })
})

describe('on-accent spinners', () => {
  it('keep a solid top arc over the translucent ring', async () => {
    const { found: spinners, unreadable } = onAccentSpinners()
    expect(unreadable).toEqual([])
    expect(spinners.length).toBeGreaterThan(0)
    const root = await buildCss(spinners.flatMap((s) => s.classes))
    for (const s of spinners) {
      expect({ file: s.file, top: effectiveBorderTop(root, s.classes) })
        .toEqual({ file: s.file, top: 'var(--on-accent)' })
    }
  }, 30000)
})
