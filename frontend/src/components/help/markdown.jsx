/**
 * The guides' Markdown (helpGuides.js and its translations) in the mockup's help vocabulary, shared
 * by the help dialog and any page that shows a guide.
 */
import { Notice } from '../atelier/Form'
import { HelpLink } from './HelpLink'

const FENCE = /^\s*```/
const HEADING = /^(#{2,4}) (.+)/
const ITEM = /^(\s*)([-*]|\d+\.)\s+(.*)$/
const TABLE_RULE = /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/
const NOTICE_MARK = /^(⚠️?|💡)\s*/u
// [label](target), the target with one level of parentheses at most
const LINK = /\[([^\]\n]+)\]\(((?:[^()\s]|\([^()\s]*\))+)\)/

// The headings outside code blocks, in order: { level, text } with the text still in Markdown
function headingsOf(md) {
  const out = []
  let fenced = false
  for (const line of (md || '').split('\n')) {
    if (FENCE.test(line)) { fenced = !fenced; continue }
    const h = !fenced && line.match(HEADING)
    if (h) out.push({ level: h[1].length, text: h[2].trim() })
  }
  return out
}

/** A heading's text as a URL fragment: ASCII lower case, words joined by '-'. */
export function headingSlug(text) {
  const slug = plainText(text).normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase()
    .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
  return slug || 'section'
}

/** The text of a line of Markdown without its marks: links keep their label. */
export function plainText(text) {
  return (text || '').replace(new RegExp(LINK.source, 'g'), '$1').replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/`([^`]+)`/g, '$1').replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '$1').trim()
}

/**
 * The headings of a chapter: { level (2 to 4), text, id }. The id is `<chapter>-<slug>` of the
 * English heading at the same position, so a link to a section holds in every language.
 */
export function guideHeadings(chapter, md, englishMd = md) {
  const english = englishMd === md ? null : headingsOf(englishMd)
  const seen = new Map()
  return headingsOf(md).map((h, i) => {
    const base = `${chapter}-${headingSlug((english?.[i] || h).text)}`
    const n = (seen.get(base) || 0) + 1
    seen.set(base, n)
    return { level: h.level, text: plainText(h.text), id: n > 1 ? `${base}-${n}` : base }
  })
}

/**
 * The guide's markdown: one section per `## ` heading (the whole text when it has none). `heading`
 * is the index of the section's heading in guideHeadings(), null for the headless one.
 */
export function guideSections(md) {
  const sections = []
  let current = null
  let fenced = false
  let count = 0
  for (const line of (md || '').split('\n')) {
    if (FENCE.test(line)) fenced = !fenced
    const h = !fenced && !FENCE.test(line) && line.match(HEADING)
    if (h && h[1].length === 2) {
      current = { title: h[2].trim(), lines: [], heading: count++ }
      sections.push(current)
      continue
    }
    if (h) count++
    if (current) current.lines.push(line)
  }
  return sections.length ? sections : [{ title: '', lines: (md || '').split('\n'), heading: null }]
}

/**
 * Paragraphs, headings, tables, lists, quotes and code of the guide. ids: the chapter's heading ids,
 * first: the index among them of the first heading in these lines; levelOffset: added to the level.
 */
export function renderMarkdown(lines, { ids = [], first = 0, levelOffset = 0 } = {}) {
  const out = []
  let heading = first
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    const at = i
    if (line.trim() === '') { i++; continue }
    if (FENCE.test(line)) {
      const code = []
      i++
      while (i < lines.length && !FENCE.test(lines[i])) code.push(lines[i++])
      i++
      out.push(<pre key={`c${at}`} className="code-preview">{code.join('\n')}</pre>)
      continue
    }
    const h = line.match(HEADING)
    if (h) {
      const depth = h[1].length
      const Tag = `h${Math.min(6, depth + levelOffset)}`
      // `guide-text` keeps the heading in a reader view, which drops one whose id reads as clutter (intermediate: media)
      out.push(<Tag key={`h${at}`} id={ids[heading]} className={`help-h${depth} guide-text`} tabIndex={-1}>{inline(h[2].trim())}</Tag>)
      heading++
      i++
      continue
    }
    if (line.trim().startsWith('|') && TABLE_RULE.test(lines[i + 1] || '')) {
      const rows = []
      const align = cells(lines[i + 1]).map((c) => (/^:-+:$/.test(c) ? 'center' : /-:$/.test(c) ? 'right' : undefined))
      const head = cells(line)
      i += 2
      while (i < lines.length && lines[i].trim().startsWith('|')) rows.push(cells(lines[i++]))
      out.push(table(head, rows, align, `t${at}`))
      continue
    }
    if (line.trim().startsWith('> ')) {
      const quote = []
      while (i < lines.length && lines[i].trim().startsWith('> ')) quote.push(lines[i++].trim().replace(/^>\s?/, ''))
      out.push(note(quote.join(' '), `q${at}`))
      continue
    }
    if (ITEM.test(line)) {
      const [list, next] = parseList(lines, i)
      out.push(listNode(list, `l${at}`))
      i = next
      continue
    }
    out.push(NOTICE_MARK.test(line.trim()) ? note(line.trim(), `n${at}`) : <p key={at}>{inline(line)}</p>)
    i++
  }
  return out
}

// A quote or a line led by ⚠ (a warning) or 💡: the notice's own icon stands for the symbol
function note(text, key) {
  const mark = text.match(NOTICE_MARK)
  const body = mark ? text.slice(mark[0].length) : text
  return <Notice key={key} tone={mark && mark[1].startsWith('⚠') ? 'warn' : undefined}>{inline(body)}</Notice>
}

// The cells of a table row, split on the '|' outside code spans
function cells(row) {
  const out = ['']
  let code = false
  const text = row.trim().replace(/^\|/, '').replace(/\|$/, '')
  for (let k = 0; k < text.length; k++) {
    const ch = text[k]
    if (ch === '\\' && text[k + 1] === '|') { out[out.length - 1] += '|'; k++; continue }
    if (ch === '`') code = !code
    if (ch === '|' && !code) out.push('')
    else out[out.length - 1] += ch
  }
  return out.map((c) => c.trim())
}

// The mockup's comparison table, in its own scroll box: a wide table scrolls there, not the page
function table(head, rows, align, key) {
  return (
    <div key={key} className="compare-scroll help-table" tabIndex={0}>
      <table className="compare-table">
        <thead><tr>{head.map((c, k) => <th key={k} scope="col" style={align[k] && { textAlign: align[k] }}>{inline(c)}</th>)}</tr></thead>
        <tbody>
          {rows.map((row, r) => (
            <tr key={r}>{head.map((_, k) => <td key={k} style={align[k] && { textAlign: align[k] }}>{inline(row[k] ?? '')}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// One list at the indent of its first item: deeper items nest in the item above, a list of the
// other kind or a shallower item ends it. An ordered list keeps the number its first item gives.
function parseList(lines, start) {
  const head = lines[start].match(ITEM)
  const indent = head[1].length
  const ordered = /\d/.test(head[2])
  const items = []
  let i = start
  while (i < lines.length) {
    const m = lines[i].match(ITEM)
    if (!m) {
      const deeper = lines[i].match(/^(\s+)\S/)
      if (items.length && deeper && deeper[1].length > indent && !FENCE.test(lines[i])) {
        items[items.length - 1].text += ` ${lines[i].trim()}`
        i++
        continue
      }
      break
    }
    const depth = m[1].length
    if (depth < indent) break
    if (depth > indent) {
      if (!items.length) break
      const [child, next] = parseList(lines, i)
      items[items.length - 1].children.push(child)
      i = next
      continue
    }
    if (/\d/.test(m[2]) !== ordered) break
    items.push({ text: m[3], number: parseInt(m[2], 10), children: [] })
    i++
  }
  return [{ ordered, start: ordered ? items[0].number : 1, items }, i]
}

function listNode(list, key) {
  const Tag = list.ordered ? 'ol' : 'ul'
  return (
    <Tag key={key} start={list.start !== 1 ? list.start : undefined}>
      {list.items.map((it, j) => (
        <li key={j}>{inline(it.text)}{it.children.map((child, k) => listNode(child, k))}</li>
      ))}
    </Tag>
  )
}

// Internal paths only (not '//host' nor '/\host', which browsers read as another host), and https
const internalTarget = (to) => /^\/(?![/\\])/.test(to)
const externalTarget = (to) => /^https:\/\/[^\s/\\]/i.test(to)

/** **bold**, `code`, *italic* and [label](target): a target other than a path or https stays text as written. */
export function inline(text) {
  const parts = []
  let rest = text
  let key = 0
  while (rest) {
    const found = [[/\*\*(.+?)\*\*/, 'b'], [/`([^`]+)`/, 'c'], [/(?<!\*)\*([^*]+)\*(?!\*)/, 'i'], [LINK, 'a']]
      .map(([re, kind]) => [rest.match(re), kind]).filter(([m]) => m).sort((a, b) => a[0].index - b[0].index)[0]
    if (!found) { parts.push(rest); break }
    const [m, kind] = found
    if (m.index > 0) parts.push(rest.slice(0, m.index))
    if (kind === 'b') parts.push(<strong key={key++}>{m[1]}</strong>)
    else if (kind === 'c') parts.push(<span key={key++} className="mono">{m[1]}</span>)
    else if (kind === 'i') parts.push(<em key={key++}>{m[1]}</em>)
    else if (internalTarget(m[2])) parts.push(<HelpLink key={key++} to={m[2]}>{m[1]}</HelpLink>)
    else if (externalTarget(m[2])) parts.push(<a key={key++} className="text-link" href={m[2]} target="_blank" rel="noopener noreferrer">{m[1]}</a>)
    else parts.push(m[0])
    rest = rest.slice(m.index + m[0].length)
  }
  return parts.length === 1 ? parts[0] : parts
}
