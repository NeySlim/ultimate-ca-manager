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

// Class lists of every spinning element whose ring uses the on-accent ink.
function onAccentSpinners() {
  const found = []
  for (const file of walk(SRC)) {
    const text = fs.readFileSync(file, 'utf8')
    for (const m of text.matchAll(/className="([^"]*animate-spin[^"]*)"/g)) {
      if (m[1].includes('on-accent')) found.push({ file: path.relative(SRC, file), classes: m[1].split(/\s+/) })
    }
  }
  return found
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

describe('on-accent spinners', () => {
  it('keep a solid top arc over the translucent ring', async () => {
    const spinners = onAccentSpinners()
    expect(spinners.length).toBeGreaterThan(0)
    const root = await buildCss(spinners.flatMap((s) => s.classes))
    for (const s of spinners) {
      expect({ file: s.file, top: effectiveBorderTop(root, s.classes) })
        .toEqual({ file: s.file, top: 'var(--on-accent)' })
    }
  }, 30000)
})
