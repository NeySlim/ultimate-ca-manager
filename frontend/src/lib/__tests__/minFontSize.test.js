/** No font size below 12px: index.css, tokens.css, tailwind.config.js and text-[Npx] classes in src JSX files. */
import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'
import tailwindConfig from '../../../tailwind.config.js'

const SRC = path.resolve(__dirname, '../..')
const MIN_PX = 12

const toPx = (n, unit) => (unit === 'px' ? n : n * 16)

function cssSizes(file) {
  const css = fs.readFileSync(path.join(SRC, file), 'utf8')
  // em/rem resolve against a 16px base; 0.92em on .font-mono gives 14.7px.
  return [...css.matchAll(/font-size:\s*([0-9.]+)(px|rem|em)\b/g)].map((m) => ({
    where: file,
    px: toPx(parseFloat(m[1]), m[2]),
    text: m[0],
  }))
}

function jsxFiles(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) return e.name === '__tests__' ? [] : jsxFiles(p)
    return e.name.endsWith('.jsx') && !e.name.endsWith('.test.jsx') ? [p] : []
  })
}

function arbitraryClassSizes() {
  return jsxFiles(SRC).flatMap((f) => {
    const src = fs.readFileSync(f, 'utf8')
    return [...src.matchAll(/\btext-\[([0-9.]+)(px|rem|em)\]/g)].map((m) => ({
      where: path.relative(SRC, f),
      px: toPx(parseFloat(m[1]), m[2]),
      text: m[0],
    }))
  })
}

function tailwindSizes() {
  const sizes = tailwindConfig.theme.extend.fontSize ?? {}
  return Object.entries(sizes).map(([name, v]) => {
    const raw = Array.isArray(v) ? v[0] : v
    const m = String(raw).match(/^([0-9.]+)(px|rem)$/)
    return { where: `tailwind fontSize.${name}`, px: toPx(parseFloat(m[1]), m[2]), text: raw }
  })
}

describe('minimum font size', () => {
  const all = [...cssSizes('index.css'), ...cssSizes('styles/tokens.css'), ...tailwindSizes(), ...arbitraryClassSizes()]

  it('reads a non-trivial number of declarations', () => {
    expect(all.length).toBeGreaterThan(4)
  })

  it(`declares nothing below ${MIN_PX}px`, () => {
    const small = all.filter((s) => s.px < MIN_PX).map((s) => `${s.where}: ${s.text}`)
    expect(small).toEqual([])
  })
})
