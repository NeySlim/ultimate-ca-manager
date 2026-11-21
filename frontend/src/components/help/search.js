/**
 * The guide's search: an index of every section in plain text, matched without case nor accents
 * (NFD folding), every word of the query required, an excerpt around the first one.
 */
import { guideHeadings, plainText } from './markdown'

const FENCE = /^\s*```/
const HEADING = /^(#{2,4}) (.+)/
const MARKS = /\p{M}/gu

/** A text folded for matching (lower case, no accents), with the index in the text of each folded character. */
export function foldWithMap(text) {
  let folded = ''
  const map = []
  for (let i = 0; i < text.length;) {
    const ch = String.fromCodePoint(text.codePointAt(i))
    const f = ch.normalize('NFD').replace(MARKS, '').toLowerCase()
    for (let k = 0; k < f.length; k++) { folded += f[k]; map.push(i) }
    i += ch.length
  }
  map.push(text.length)
  return { folded, map }
}

export const fold = (text) => foldWithMap(text || '').folded

/** The words of a query, folded; empty when shorter than two characters. */
export function queryTerms(query) {
  const q = fold(query).trim()
  if (q.length < 2) return []
  return [...new Set(q.split(/\s+/).filter(Boolean))]
}

/** The ranges [start, end) of the text where a term occurs, merged and in order. */
export function termRanges(text, terms) {
  if (!text || !terms?.length) return []
  const { folded, map } = foldWithMap(text)
  const ranges = []
  for (const term of terms) {
    for (let at = folded.indexOf(term); at >= 0; at = folded.indexOf(term, at + term.length)) {
      ranges.push([map[at], map[at + term.length]])
    }
  }
  ranges.sort((a, b) => a[0] - b[0])
  const merged = []
  for (const r of ranges) {
    const last = merged[merged.length - 1]
    if (last && r[0] <= last[1]) last[1] = Math.max(last[1], r[1])
    else merged.push([...r])
  }
  return merged
}

// A line of Markdown as reading text: no list mark, quote, table rule or cell bars
function plainLine(line) {
  const t = line.trim()
  if (/^\|?\s*:?-{3,}/.test(t)) return ''
  return plainText(t.replace(/^>\s?/, '').replace(/^([-*]|\d+\.)\s+/, '').replace(/^\|/, '').replace(/\|$/, '').replace(/\s*\|\s*/g, ' · '))
}

/** The sections of a guide chapter: { id, title, text } per heading, the text before the first one under the chapter's title. */
export function chapterSections(chapter, title, markdown, english) {
  const ids = guideHeadings(chapter, markdown, english)
  const sections = [{ id: null, title, lines: [] }]
  let fenced = false
  let n = 0
  for (const line of (markdown || '').split('\n')) {
    if (FENCE.test(line)) { fenced = !fenced; continue }
    const h = !fenced && line.match(HEADING)
    if (h) {
      sections.push({ id: ids[n]?.id || null, title: ids[n]?.text || plainText(h[2]), lines: [] })
      n++
      continue
    }
    const text = fenced ? line.trim() : plainLine(line)
    if (text) sections[sections.length - 1].lines.push(text)
  }
  return sections
    .map((s) => ({ id: s.id, title: s.title, text: s.lines.join(' ') }))
    .filter((s) => s.id || s.text)
}

/** The sections of a quick help (the navigation chapter): its overview, then a section per part. */
export function quickSections(quick) {
  const item = (it) => (typeof it === 'object' ? [it.label, it.text].filter(Boolean).join(': ') : it)
  const parts = [{ id: null, title: quick.title, text: [quick.subtitle, quick.overview].filter(Boolean).join(' ') }]
  for (const s of quick.sections || []) {
    const text = [s.content, ...(s.items || []).map(item), ...(s.definitions || []).map((d) => `${d.term}: ${d.description}`), s.example]
    parts.push({ id: null, title: s.title, text: text.filter(Boolean).join(' ') })
  }
  for (const list of [quick.tips, quick.warnings]) if (list?.length) parts.push({ id: null, title: quick.title, text: list.join(' ') })
  return parts
}

/** An index entry per section: { chapter, chapterTitle, id, title, text, haystack }. */
export function indexEntries(chapter, chapterTitle, sections) {
  return sections.map((s) => ({ chapter, chapterTitle, id: s.id, title: s.title, text: s.text, haystack: fold(`${s.title}\n${s.text}`) }))
}

/** The sections holding every term, in the index's order. */
export function searchIndex(index, terms) {
  if (!terms.length) return []
  return index.filter((e) => terms.every((t) => e.haystack.includes(t)))
}

/** Results by chapter, in the index's order: [{ chapter, chapterTitle, results }]. */
export function groupByChapter(results) {
  const groups = []
  for (const r of results) {
    const last = groups[groups.length - 1]
    if (last?.chapter === r.chapter) last.results.push(r)
    else groups.push({ chapter: r.chapter, chapterTitle: r.chapterTitle, results: [r] })
  }
  return groups
}

/** About `size` characters of the text around the first term found in it, cut at words, with … where cut. */
export function excerpt(text, terms, size = 160) {
  if (!text) return ''
  const first = termRanges(text, terms)[0]
  const at = first ? first[0] : 0
  let start = Math.max(0, at - Math.floor(size / 3))
  let end = Math.min(text.length, start + size)
  if (start > 0) { const sp = text.indexOf(' ', start); if (sp >= 0 && sp < at) start = sp + 1 }
  if (end < text.length) { const sp = text.lastIndexOf(' ', end); if (sp > at) end = sp }
  return `${start > 0 ? '…' : ''}${text.slice(start, end)}${end < text.length ? '…' : ''}`
}
