/** No declared font size below 12px in index.css, tokens.css or tailwind.config.js. */
import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'
import tailwindConfig from '../../../tailwind.config.js'

const SRC = path.resolve(__dirname, '../..')
const MIN_PX = 12

const toPx = (n, unit) => (unit === 'rem' ? n * 16 : n)

function cssSizes(file) {
  const css = fs.readFileSync(path.join(SRC, file), 'utf8')
  return [...css.matchAll(/font-size:\s*([0-9.]+)(px|rem)\b/g)].map((m) => ({
    where: file,
    px: toPx(parseFloat(m[1]), m[2]),
    text: m[0],
  }))
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
  const all = [...cssSizes('index.css'), ...cssSizes('styles/tokens.css'), ...tailwindSizes()]

  it('reads a non-trivial number of declarations', () => {
    expect(all.length).toBeGreaterThan(4)
  })

  it(`declares nothing below ${MIN_PX}px`, () => {
    const small = all.filter((s) => s.px < MIN_PX).map((s) => `${s.where}: ${s.text}`)
    expect(small).toEqual([])
  })
})
