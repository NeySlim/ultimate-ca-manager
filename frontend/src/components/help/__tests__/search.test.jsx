/**
 * The guide's search: case and accents folded, every word required, sections in plain text,
 * an excerpt around the first word, the words marked on the rendered text only.
 */
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { chapterSections, excerpt, fold, foldWithMap, indexEntries, queryTerms, searchIndex, termRanges, groupByChapter } from '../search'
import { highlightTree, markText } from '../highlight'
import { GuideContent } from '../GuideContent'
import { QuickHelp } from '../QuickHelp'

const draw = (node) => render(<MemoryRouter>{node}</MemoryRouter>).container
const marks = (c) => [...c.querySelectorAll('mark.guide-hit')].map((m) => m.textContent)

describe('folding', () => {
  it('folds case and accents and keeps the position of each character', () => {
    expect(fold('Révocation ÉTENDUE')).toBe('revocation etendue')
    expect(fold('Ärger Ünïcode çà')).toBe('arger unicode ca')
    const { folded, map } = foldWithMap('aÉb')
    expect(folded).toBe('aeb')
    expect(map).toEqual([0, 1, 2, 3])
  })

  it('takes the words of a query, two characters at least', () => {
    expect(queryTerms('  Autorité   RACINE ')).toEqual(['autorite', 'racine'])
    expect(queryTerms('a')).toEqual([])
    expect(queryTerms('crl crl')).toEqual(['crl'])
  })

  it('finds the ranges of the words in the original text, accents kept', () => {
    const text = 'La Révocation et la révocation'
    expect(termRanges(text, ['revocation']).map(([a, b]) => text.slice(a, b))).toEqual(['Révocation', 'révocation'])
    expect(termRanges('décomposé', ['decompose'])).toEqual([[0, 9]])
    // a decomposed accent (e + U+0301) is one more character in the text, none in the folded form
    const nfd = 'Révocation'
    expect(termRanges(nfd, ['revocation'])).toEqual([[0, nfd.length]])
  })
})

describe('index and matching', () => {
  const md = ['Intro line about **roots**.', '## Overview', 'A *root* CA signs.', '| Col | Val |', '|---|---|', '| Key | RSA |',
    '### Revocation', '- Publish the CRL', '```', '## not a heading', '```', '## Second', 'Nothing here'].join('\n')
  const sections = chapterSections('cas', 'Authorities', md, md)

  it('cuts a chapter at its headings, in plain text, with the ids of the guide', () => {
    expect(sections.map((s) => [s.id, s.title])).toEqual([
      [null, 'Authorities'], ['cas-overview', 'Overview'], ['cas-revocation', 'Revocation'], ['cas-second', 'Second'],
    ])
    expect(sections[0].text).toBe('Intro line about roots.')
    expect(sections[1].text).toBe('A root CA signs. Col · Val Key · RSA')
    expect(sections[2].text).toContain('Publish the CRL')
    expect(sections[2].text).toContain('## not a heading')
  })

  it('requires every word, whatever the case and the accents', () => {
    const index = indexEntries('cas', 'Authorities', sections)
    expect(searchIndex(index, queryTerms('ROOT signs')).map((e) => e.id)).toEqual(['cas-overview'])
    expect(searchIndex(index, queryTerms('révocation crl')).map((e) => e.id)).toEqual(['cas-revocation'])
    expect(searchIndex(index, queryTerms('root nothing'))).toEqual([])
    expect(searchIndex(index, queryTerms('second'))).toHaveLength(1)
  })

  it('groups the results by chapter in order', () => {
    const r = [{ chapter: 'a', chapterTitle: 'A' }, { chapter: 'a', chapterTitle: 'A' }, { chapter: 'b', chapterTitle: 'B' }]
    expect(groupByChapter(r).map((g) => [g.chapter, g.results.length])).toEqual([['a', 2], ['b', 1]])
  })

  it('cuts an excerpt around the first word, at words', () => {
    const text = `${'alpha '.repeat(40)}the needle sits here ${'omega '.repeat(40)}`.trim()
    const e = excerpt(text, ['needle'], 80)
    expect(e).toContain('needle')
    expect(e.startsWith('…')).toBe(true)
    expect(e.endsWith('…')).toBe(true)
    expect(e.length).toBeLessThanOrEqual(82)
    expect(excerpt('short text', ['short'])).toBe('short text')
  })
})

describe('marking the words', () => {
  it('marks a string, accents and case kept', () => {
    const c = draw(<p>{markText('Une Révocation, une révocation.', ['revocation'])}</p>)
    expect(marks(c)).toEqual(['Révocation', 'révocation'])
    expect(c.textContent).toBe('Une Révocation, une révocation.')
  })

  it('marks the rendered text of a chapter, not its Markdown: links, code and tables keep their shape', () => {
    const md = ['## Root CA', 'A **root** signs; see [the roots](/cas) and `root.pem`.', '| Kind | Note |', '|---|---|', '| Root | offline |'].join('\n')
    const c = draw(<GuideContent chapter="cas" markdown={md} highlight={['root']} />)
    expect(marks(c)).toEqual(['Root', 'root', 'root', 'root', 'Root'])
    expect(c.querySelector('h2#cas-root-ca mark')).toBeTruthy()
    expect(c.querySelector('a.text-link').getAttribute('href')).toBe('/cas')
    expect(c.querySelector('a.text-link').textContent).toBe('the roots')
    expect(c.querySelector('.mono').textContent).toBe('root.pem')
    expect(c.querySelector('table td mark')).toHaveTextContent('Root')
    expect(c.textContent).not.toContain('**')
  })

  it('leaves the chapter as it is without words', () => {
    const c = draw(<GuideContent chapter="cas" markdown={'## Root\ntext'} highlight={[]} />)
    expect(marks(c)).toEqual([])
    expect(highlightTree('plain', [])).toBe('plain')
  })

  it('marks a quick help, its items included', () => {
    const quick = { title: 'Nav', overview: 'The top bar', sections: [{ title: 'Bar', items: ['Top item', { label: 'Pin', text: 'keeps a top page' }] }] }
    const c = draw(<QuickHelp content={quick} highlight={['top']} />)
    expect(marks(c)).toEqual(['top', 'Top', 'top'])
  })
})
