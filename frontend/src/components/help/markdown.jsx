/**
 * The guides' Markdown (helpGuides.js and its translations) in the mockup's help vocabulary, shared
 * by the help dialog and any page that shows a guide.
 */
import { Notice } from '../atelier/Form'

// The guide's markdown: one section per `## ` heading (the whole text when it has none)
export function guideSections(md) {
  const sections = []
  let current = null
  for (const line of (md || '').split('\n')) {
    const h2 = line.match(/^## (.+)/)
    if (h2) {
      current = { title: h2[1].trim(), lines: [] }
      sections.push(current)
    } else if (current) current.lines.push(line)
  }
  return sections.length ? sections : [{ title: '', lines: (md || '').split('\n') }]
}

// Paragraphs, lists, sub-headings, quotes and code of the guide, in the mockup's help vocabulary
export function renderLines(lines) {
  const out = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (line.trim() === '') { i++; continue }
    const sub = line.match(/^#{3,4} (.+)/)
    if (sub) { out.push(<p key={i}><strong>{inline(sub[1].trim())}</strong></p>); i++; continue }
    if (line.trim().startsWith('```')) {
      const code = []
      const at = i
      i++
      while (i < lines.length && !lines[i].trim().startsWith('```')) code.push(lines[i++])
      i++
      out.push(<pre key={`c${at}`} className="code-preview">{code.join('\n')}</pre>)
      continue
    }
    if (line.trim().startsWith('> ')) {
      const quote = []
      const at = i
      while (i < lines.length && lines[i].trim().startsWith('> ')) quote.push(lines[i++].trim().replace(/^>\s?/, ''))
      out.push(<Notice key={`q${at}`}>{inline(quote.join(' '))}</Notice>)
      continue
    }
    const list = [[/^\s*[-*]\s/, 'ul'], [/^\d+\.\s/, 'ol']].find(([re]) => re.test(line))
    if (list) {
      const [re, Tag] = list
      const items = []
      const at = i
      while (i < lines.length && re.test(lines[i])) items.push(lines[i++].replace(re, ''))
      out.push(<Tag key={`l${at}`}>{items.map((it, j) => <li key={j}>{inline(it)}</li>)}</Tag>)
      continue
    }
    out.push(<p key={i}>{inline(line)}</p>)
    i++
  }
  return out
}

// **bold**, `code` and *italic*
export function inline(text) {
  const parts = []
  let rest = text
  let key = 0
  while (rest) {
    const found = [[/\*\*(.+?)\*\*/, 'b'], [/`([^`]+)`/, 'c'], [/(?<!\*)\*([^*]+)\*(?!\*)/, 'i']]
      .map(([re, kind]) => [rest.match(re), kind]).filter(([m]) => m).sort((a, b) => a[0].index - b[0].index)[0]
    if (!found) { parts.push(rest); break }
    const [m, kind] = found
    if (m.index > 0) parts.push(rest.slice(0, m.index))
    parts.push(kind === 'b' ? <strong key={key++}>{m[1]}</strong> : kind === 'c' ? <span key={key++} className="mono">{m[1]}</span> : <em key={key++}>{m[1]}</em>)
    rest = rest.slice(m.index + m[0].length)
  }
  return parts.length === 1 ? parts[0] : parts
}
