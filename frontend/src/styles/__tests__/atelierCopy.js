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
  // a font face or keyframes has no selector to scope: it is copied as it is
  if (/^@(font-face|keyframes\s)/.test(s)) return s
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

// The mockup's font file and where the product serves the same file (public/fonts)
export const ASSETS = [["url('../assets/", "url('/fonts/"]]
const toMockBody = (body) => ASSETS.reduce((b, [mock, product]) => b.split(product).join(mock), body)

const norm = (s) => s.replace(/\s+/g, ' ').replace(/\s*([{};:,>])\s*/g, '$1').trim()
const ruleKey = (media, sel) => `${norm(media)}|${splitSelectors(sel).map(norm).join(',')}`

/** A rule of the mockup on its document only: every selector is :root, html or body (or a pseudo-element of body), under an optional theme root. */
export function isDocumentRule(r) {
  return !r.sel.startsWith('@') && splitSelectors(r.sel).every((s) => {
    const m = s.match(ROOT)
    const rest = s.slice(m ? m[0].length : 0).trim()
    return (m && m[0] && rest === '') || /^(html|body)(::?[a-z-]+)?$/.test(rest)
  })
}

export const mockup = parseRules(fs.readFileSync(path.join(FIXTURES, 'style.css'), 'utf8'))
/** What a whole copy holds: every rule of the mockup but those on its document. */
export const copiedRules = mockup.filter((r) => !isDocumentRule(r))
export const documentRules = mockup.filter(isDocumentRule)
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
    const body = norm(toMockBody(r.body))
    const same = candidates.find((c) => norm(c.body) === body && c.i > last) || candidates.find((c) => norm(c.body) === body)
    if (!same) { problems.push(`differs from the mockup: ${r.media} ${r.sel}{${r.body}} ≠ {${candidates[0].body}}`); continue }
    if (same.i <= last) problems.push(`out of the mockup's order: ${r.sel}`)
    last = same.i
  }
  return problems
}

/**
 * Problems of a whole copy: its rules, back to the mockup's form, must be exactly copiedRules in
 * order. A rule missing, added, changed or moved is reported (a longest common subsequence aligns both).
 */
export function checkWhole(text) {
  const label = (r) => `${r.media ? `${r.media} ` : ''}${r.sel}{${r.body}}`
  const theirs = copiedRules.map((r) => `${ruleKey(r.media, r.sel)}{${norm(r.body)}`)
  const rules = parseRules(text)
  const ours = rules.map((r) => {
    const back = splitSelectors(r.sel).map(unscope)
    return back.some((s) => s === null) ? null : `${ruleKey(r.media, back.join(','))}{${norm(toMockBody(r.body))}`
  })
  const n = theirs.length
  const m = ours.length
  const lcs = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1))
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) lcs[i][j] = theirs[i] === ours[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1])
  }
  const problems = []
  let i = 0
  let j = 0
  while (i < n || j < m) {
    if (i < n && j < m && theirs[i] === ours[j]) { i++; j++ } else if (j < m && (i === n || lcs[i][j + 1] >= lcs[i + 1][j])) {
      problems.push(ours[j] === null ? `not under .atl: ${rules[j].sel}` : `not in the mockup (or not here in its order): ${label(rules[j])}`); j++
    } else { problems.push(`missing from the copy: ${label(copiedRules[i])}`); i++ }
  }
  return problems
}

// What a document rule of the mockup carries, by property: custom properties live in tokens.css;
// inherited ones must reach .atl with the same value; the others style the document, which is the shell's.
export const INHERITED = new Set(['color-scheme', 'font-family', 'font-size', 'color'])
export const DOCUMENT_ONLY = new Set(['height', 'min-height', 'margin', 'overflow', 'background', 'isolation'])

/** `prop:value` declarations of a rule body, in order. */
export function declarations(body) {
  const out = []
  let depth = 0
  let cur = ''
  for (const c of `${body};`) {
    if (c === '(') depth++
    if (c === ')') depth--
    if (c === ';' && depth === 0) {
      const k = cur.indexOf(':')
      if (k > 0) out.push([cur.slice(0, k).trim(), cur.slice(k + 1).trim()])
      cur = ''
    } else cur += c
  }
  return out
}

// The four themes: the mockup's root for each, the product's (data-theme / data-mode on <html>)
export const THEMES = {
  dark: { mock: [':root'], product: [':root', ':root[data-theme="atelier"][data-mode="dark"]'] },
  light: { mock: [':root', ':root[data-theme=light]'], product: [':root', ':root[data-theme="atelier"][data-mode="light"]', ':root[data-mode="light"]'] },
  aurore: { mock: [':root', ':root[data-theme=aurore]', ':root[data-theme|=aurore]'], product: [':root', ':root[data-theme="aurore"][data-mode="dark"]', ':root[data-theme|=aurore]'] },
  'aurore-light': { mock: [':root', ':root[data-theme=aurore-light]', ':root[data-theme|=aurore]'], product: [':root', ':root[data-theme="aurore"][data-mode="light"]', ':root[data-theme|=aurore]', ':root[data-mode="light"]'] },
}
const specificity = (root) => (root.match(/\[/g) || []).length

/** Declarations that reach an element under `roots` (selectors written `<root>` + `suffix`), by specificity then order. */
export function cascade(rules, roots, suffix = '') {
  const hits = []
  rules.forEach((r, order) => {
    if (r.media) return
    for (const s of splitSelectors(r.sel)) {
      const root = roots.find((x) => s === x + suffix)
      if (root !== undefined) hits.push({ spec: specificity(root), order, r })
    }
  })
  hits.sort((a, b) => a.spec - b.spec || a.order - b.order)
  const out = {}
  for (const { r } of hits) for (const [k, v] of declarations(r.body)) out[k] = v
  return out
}

/** A value written two ways the same (#fff / #ffffff, rgba(1, 2, 3, 0.30) / rgba(1,2,3,.30)). */
export function sameValue(v) {
  return v.toLowerCase().replace(/\s+/g, '').replace(/([(,])0\./g, '$1.')
    .replace(/#([0-9a-f])([0-9a-f])([0-9a-f])(?![0-9a-f])/g, '#$1$1$2$2$3$3')
}

