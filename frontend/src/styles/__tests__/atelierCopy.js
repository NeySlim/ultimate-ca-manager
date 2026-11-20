/**
 * Reads the Atelier mockup's style.css (the approved copy in fixtures/atelier) and checks a stylesheet
 * copied from it: same rules, values untouched, selectors under .atl, the mockup's order.
 */
import fs from 'fs'
import path from 'path'

export const FIXTURES = path.resolve(__dirname, 'fixtures/atelier')

function stripComments(src) {
  let out = ''
  for (let i = 0; i < src.length;) {
    const c = src[i]
    if (c === '"' || c === "'") {
      let j = i + 1
      while (j < src.length && src[j] !== c) j += src[j] === '\\' ? 2 : 1
      out += src.slice(i, j + 1); i = j + 1
    } else if (src.startsWith('/*', i)) {
      const j = src.indexOf('*/', i + 2)
      i = j < 0 ? src.length : j + 2
    } else { out += c; i++ }
  }
  return out
}

function blockEnd(src, start) {
  let depth = 0
  for (let i = start; i < src.length; i++) {
    const c = src[i]
    if (c === '"' || c === "'") {
      let j = i + 1
      while (j < src.length && src[j] !== c) j += src[j] === '\\' ? 2 : 1
      i = j; continue
    }
    if (c === '{') depth++
    else if (c === '}' && --depth === 0) return i
  }
  throw new Error('unbalanced braces')
}

/** Flat rules: { media, sel, body }; @media / @container / @supports blocks are flattened into `media`. */
export function parseRules(src, media = '', out = []) {
  if (!out.length && media === '') src = stripComments(src)
  let i = 0
  while (i < src.length) {
    const j = src.indexOf('{', i)
    if (j < 0) break
    const head = src.slice(i, j).trim()
    const k = blockEnd(src, j)
    const body = src.slice(j + 1, k)
    if (/^@(media|container|supports)/.test(head)) parseRules(body, head, out)
    else out.push({ media, sel: head, body: body.trim() })
    i = k + 1
  }
  return out
}

export function splitSelectors(sel) {
  const parts = []
  let depth = 0
  let cur = ''
  for (const c of sel) {
    if (c === '(' || c === '[') depth++
    if (c === ')' || c === ']') depth--
    if (c === ',' && depth === 0) { parts.push(cur.trim()); cur = '' } else cur += c
  }
  parts.push(cur.trim())
  return parts
}

// The mockup's theme roots and the product's; [data-theme|=aurore] is the same on both sides
const THEME_ROOTS = [
  [':root[data-theme=aurore-light]', ':root[data-theme="aurore"][data-mode="light"]'],
  [':root[data-theme=aurore]', ':root[data-theme="aurore"][data-mode="dark"]'],
  [':root[data-theme=light]', ':root[data-theme="atelier"][data-mode="light"]'],
]
// A theme root: :root[...] or :where(:root[...])
const ROOT = /^(?::where\(:root(?:\[[^\]]*\])*\)|:root(?:\[[^\]]*\])*)/
const toMockRoot = (root) => (THEME_ROOTS.find(([, product]) => product === root) || [root])[0]

/** A scoped selector back to the mockup's, or null when it is not under .atl. */
export function unscope(sel) {
  const s = sel.trim()
  if (s.startsWith('.atl ')) return s.slice(5)
  const m = s.match(ROOT)
  if (!m || !m[0]) return null
  const rest = s.slice(m[0].length)
  if (rest !== ' .atl' && !/^ \.atl[ >+~]/.test(rest)) return null
  const inner = m[0].startsWith(':where(') ? m[0].slice(7, -1) : m[0]
  // a mockup theme root left as it is would never match the product's <html>
  if (THEME_ROOTS.some(([mock]) => mock === inner)) return null
  const mockRoot = m[0].startsWith(':where(') ? `:where(${toMockRoot(inner)})` : toMockRoot(inner)
  return mockRoot + rest.slice(5)
}

const norm = (s) => s.replace(/\s+/g, ' ').replace(/\s*([{};:,>])\s*/g, '$1').trim()
const ruleKey = (media, sel) => `${norm(media)}|${splitSelectors(sel).map(norm).join(',')}`

export const mockup = parseRules(fs.readFileSync(path.join(FIXTURES, 'style.css'), 'utf8'))
const index = new Map()
mockup.forEach((r, i) => {
  const key = ruleKey(r.media, r.sel)
  if (!index.has(key)) index.set(key, [])
  index.get(key).push({ ...r, i })
})

/** Problems of one copied stylesheet: unscoped selectors, rules absent or different, order. */
export function checkCopy(text) {
  const problems = []
  let last = -1
  for (const r of parseRules(text)) {
    const back = splitSelectors(r.sel).map(unscope)
    if (back.some((s) => s === null)) { problems.push(`not under .atl: ${r.sel}`); continue }
    const candidates = index.get(ruleKey(r.media, back.join(','))) || []
    if (!candidates.length) { problems.push(`no such rule in the mockup: ${r.media} ${back.join(',')}`); continue }
    const same = candidates.find((c) => norm(c.body) === norm(r.body) && c.i > last) || candidates.find((c) => norm(c.body) === norm(r.body))
    if (!same) { problems.push(`differs from the mockup: ${r.media} ${r.sel}{${r.body}} ≠ {${candidates[0].body}}`); continue }
    if (same.i <= last) problems.push(`out of the mockup's order: ${r.sel}`)
    last = same.i
  }
  return problems
}

