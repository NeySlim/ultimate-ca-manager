/**
 * The guides' Markdown: tables, nested and continued lists, real headings with ids taken from the
 * English text, internal and external links only, quotes whose ⚠ or 💡 the notice icon replaces.
 */
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { guideHeadings, guideSections, inline, renderMarkdown } from '../markdown'
import { GuideContent } from '../GuideContent'

const draw = (node) => render(<MemoryRouter>{node}</MemoryRouter>).container
const md = (...lines) => draw(<div>{renderMarkdown(lines)}</div>)
const texts = (nodes) => [...nodes].map((n) => n.textContent)

describe('guide markdown', () => {
  it('draws a table as a table, in a container that scrolls', () => {
    const c = md('| Operation | Online | Offline |', '|---|:---:|---|', '| Issue | Allowed | **Blocked** |', '| OCSP | Allowed | Cached `nextUpdate` |')
    const table = c.querySelector('.compare-scroll > table.compare-table')
    expect(table).toBeTruthy()
    expect(texts(table.querySelectorAll('thead th'))).toEqual(['Operation', 'Online', 'Offline'])
    expect(table.querySelectorAll('thead th')[0]).toHaveAttribute('scope', 'col')
    const rows = table.querySelectorAll('tbody tr')
    expect(rows).toHaveLength(2)
    expect(texts(rows[0].querySelectorAll('td'))).toEqual(['Issue', 'Allowed', 'Blocked'])
    expect(rows[0].querySelector('td strong')).toHaveTextContent('Blocked')
    expect(rows[1].querySelector('td .mono')).toHaveTextContent('nextUpdate')
    expect(c.querySelector('p')).toBeNull()
  })

  it('nests an indented list in its item and keeps one numbered list around it', () => {
    const c = md('1. Open', '2. Choose:', '   - **PEM**: text', '   - PKCS#12', '3. Download')
    const ol = c.querySelectorAll(':scope > div > ol')
    expect(ol).toHaveLength(1)
    const items = ol[0].querySelectorAll(':scope > li')
    expect(items).toHaveLength(3)
    expect(texts(items[1].querySelectorAll(':scope > ul > li'))).toEqual(['PEM: text', 'PKCS#12'])
    expect(items[2]).toHaveTextContent('Download')
  })

  it('continues the numbering of a list cut by a bullet or a paragraph', () => {
    const c = md('1. first', '2. second', '- aside', '3. third', '', 'A paragraph', '', '4. fourth')
    const ols = c.querySelectorAll('ol')
    expect(ols).toHaveLength(3)
    expect(ols[0].getAttribute('start')).toBeNull()
    expect(ols[1]).toHaveAttribute('start', '3')
    expect(ols[2]).toHaveAttribute('start', '4')
    expect(c.querySelector('ul')).toHaveTextContent('aside')
  })

  it('draws ##, ### and #### as h2, h3 and h4 whose ids come from the English text by position', () => {
    const en = '## Overview\nText\n### Root CA\n#### Set up\n## Root CA'
    const fr = '## Présentation\nTexte\n### AC racine\n#### Mise en place\n## AC racine'
    const ids = (c) => [...c.querySelectorAll('h2,h3,h4')].map((h) => [h.tagName, h.id, h.textContent])
    const enDom = draw(<GuideContent chapter="cas" markdown={en} />)
    const frDom = draw(<GuideContent chapter="cas" markdown={fr} englishMarkdown={en} />)
    expect(ids(enDom)).toEqual([
      ['H2', 'cas-overview', 'Overview'], ['H3', 'cas-root-ca', 'Root CA'], ['H4', 'cas-set-up', 'Set up'], ['H2', 'cas-root-ca-2', 'Root CA'],
    ])
    expect(ids(frDom).map(([tag, id]) => [tag, id])).toEqual(ids(enDom).map(([tag, id]) => [tag, id]))
    expect(ids(frDom)[2][2]).toBe('Mise en place')
    expect(guideHeadings('cas', fr, en)).toEqual([
      { level: 2, text: 'Présentation', id: 'cas-overview' },
      { level: 3, text: 'AC racine', id: 'cas-root-ca' },
      { level: 4, text: 'Mise en place', id: 'cas-set-up' },
      { level: 2, text: 'AC racine', id: 'cas-root-ca-2' },
    ])
  })

  it('reads no heading inside a code block', () => {
    const doc = '## Use\n```\n## not a heading\n# comment\n```\n## Next'
    expect(guideHeadings('x', doc).map((h) => h.text)).toEqual(['Use', 'Next'])
    expect(guideSections(doc).map((s) => s.title)).toEqual(['Use', 'Next'])
  })

  it('shifts the heading levels for a host whose own title is the h2', () => {
    const c = draw(<GuideContent chapter="cas" markdown={'## A\n### B\n#### C'} levelOffset={1} />)
    expect([...c.querySelectorAll('h3,h4,h5')].map((h) => h.tagName)).toEqual(['H3', 'H4', 'H5'])
    expect(c.querySelector('h2')).toBeNull()
  })

  it('links inside the application with the router and outside with a new tab', () => {
    const c = draw(<p>{inline('See [Certificates](/certificates?tab=all) and [RFC 8555](https://www.rfc-editor.org/rfc/rfc8555).')}</p>)
    const [inside, outside] = c.querySelectorAll('a')
    expect(inside).toHaveAttribute('href', '/certificates?tab=all')
    expect(inside).not.toHaveAttribute('target')
    expect(inside).toHaveTextContent('Certificates')
    expect(outside).toHaveAttribute('href', 'https://www.rfc-editor.org/rfc/rfc8555')
    expect(outside).toHaveAttribute('target', '_blank')
    expect(outside).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('refuses any other target: javascript:, data:, http:, another host, raw HTML: all stay text as written', () => {
    const source = '[a](javascript:alert(1)) [b](data:text/html,x) [c](http://x.test) [d](//evil.test) [e](/\\evil.test) <img src=x onerror=alert(1)>'
    const c = draw(<p>{inline(source)}</p>)
    expect(c.querySelector('a')).toBeNull()
    expect(c.querySelector('img')).toBeNull()
    expect(c.textContent).toBe(source)
  })

  it('draws a quote led by ⚠ as a warning notice and by 💡 as a notice, the symbol not repeated', () => {
    const c = md('> ⚠ Passwords are **not recoverable**.', '', '> 💡 Hold is temporary.', '', '⚠️ A bare warning line')
    const notes = c.querySelectorAll('.notice')
    expect(notes).toHaveLength(3)
    expect(notes[0]).toHaveClass('warn')
    expect(notes[0].textContent).toBe('Passwords are not recoverable.')
    expect(notes[1]).not.toHaveClass('warn')
    expect(notes[1].textContent).toBe('Hold is temporary.')
    expect(notes[2]).toHaveClass('warn')
    expect(notes[2].textContent).toBe('A bare warning line')
  })
})
