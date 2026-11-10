// Reads src/styles/tokens.css into resolved colours, one entry per family x mode.
// Resolves var(--x) inside a block and color-mix(in srgb, A p%, B) to hex.
import fs from 'fs'
import path from 'path'

const TOKENS_CSS = path.resolve(__dirname, '../../styles/tokens.css')

export const FAMILIES = ['atelier', 'aurore', 'purple', 'sunset']
export const MODES = ['dark', 'light']
export const TOKEN_NAMES = [
  'bg', 'panel', 'raised', 'hover', 'text', 'muted', 'line', 'control', 'accent', 'selected',
  'good', 'goodbg', 'warn', 'warn-fill', 'warnbg', 'bad', 'badbg', 'grad-a', 'grad-b', 'glow',
  'on-accent',
]
// Compatibility aliases resolved against each palette (defined in the shared :root block).
export const ALIAS_NAMES = ['text-tertiary']

export function hexToRgb(hex) {
  const h = hex.replace('#', '')
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16))
}

export function rgbToHex(rgb) {
  return '#' + rgb.map((v) => Math.round(v).toString(16).padStart(2, '0')).join('')
}

function splitArgs(s) {
  const out = []
  let depth = 0
  let cur = ''
  for (const ch of s) {
    if (ch === '(') depth++
    if (ch === ')') depth--
    if (ch === ',' && depth === 0) { out.push(cur.trim()); cur = '' } else cur += ch
  }
  out.push(cur.trim())
  return out
}

function resolve(value, decls) {
  const v = value.trim()
  const ref = v.match(/^var\(--([a-z-]+)\)$/)
  if (ref) return resolve(decls[ref[1]], decls)
  if (v.startsWith('color-mix(')) {
    const [space, a, b] = splitArgs(v.slice(v.indexOf('(') + 1, v.lastIndexOf(')')))
    if (space !== 'in srgb') throw new Error(`unsupported colour space: ${space}`)
    const pa = a.match(/^(.*)\s+([0-9.]+)%$/)
    const ca = hexToRgb(resolve(pa[1], decls))
    const cb = hexToRgb(resolve(b, decls))
    const p = parseFloat(pa[2]) / 100
    return rgbToHex(ca.map((x, i) => x * p + cb[i] * (1 - p)))
  }
  return v.toLowerCase()
}

export function parseTokens(css = fs.readFileSync(TOKENS_CSS, 'utf8')) {
  const result = {}
  const aliasDecls = {}
  for (const block of css.matchAll(/(:root[^{]*)\{([^}]*)\}/g)) {
    if (/data-theme/.test(block[1])) continue
    for (const d of block[2].matchAll(/--([a-z-]+):\s*([^;]+);/g)) aliasDecls[d[1]] = d[2].trim()
  }
  for (const block of css.matchAll(/(:root[^{]*)\{([^}]*)\}/g)) {
    const selectors = block[1]
    const decls = {}
    for (const d of block[2].matchAll(/--([a-z-]+):\s*([^;]+);/g)) decls[d[1]] = d[2].trim()
    if (!decls.bg) continue
    for (const sel of selectors.split(',')) {
      const m = sel.match(/data-theme="([a-z]+)"\]\[data-mode="([a-z]+)"/)
      if (!m) continue
      const resolved = {}
      for (const name of TOKEN_NAMES) {
        resolved[name] = name === 'glow' ? decls[name] : resolve(decls[name], decls)
      }
      const all = { ...aliasDecls, ...decls }
      for (const name of ALIAS_NAMES) resolved[name] = resolve(all[name], all)
      result[`${m[1]}-${m[2]}`] = resolved
    }
  }
  return result
}

function channel(v) {
  const c = v / 255
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
}

export function luminance(hex) {
  const [r, g, b] = hexToRgb(hex)
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
}

export function contrast(a, b) {
  const x = luminance(a)
  const y = luminance(b)
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05)
}
