/**
 * The search over the whole guide: its index loaded at the first focus, in the reading language,
 * every word required whatever the case and the accents, results by chapter with an excerpt and
 * the words marked, the arrows, Enter and Escape, the count announced, a message without result.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'

const h = vi.hoisted(() => ({ load: vi.fn() }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, o) => (o?.count != null ? `${key}:${o.count}` : key), i18n: { language: 'en', resolvedLanguage: 'en' } }),
}))
vi.mock('../../../data/helpLoader', () => ({ loadHelpPage: (...a) => h.load(...a) }))
vi.mock('../../../data/helpData', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, loadEnglishHelp: vi.fn(actual.loadEnglishHelp) }
})

import { GuideSearch } from '../GuideSearch'
import { loadGuideIndex } from '../guideIndex'
import { loadEnglishHelp } from '../../../data/helpData'
import { queryTerms, searchIndex } from '../search'

function Where() {
  const l = useLocation()
  return <div data-testid="where">{l.pathname + l.search + l.hash}</div>
}
const show = (lang = null) => render(
  <MemoryRouter initialEntries={['/guide/cas']}>
    <Routes><Route path="/guide/:chapter" element={<GuideSearch lang={lang} />} /></Routes>
    <Where />
  </MemoryRouter>,
)
const field = () => screen.getByRole('searchbox', { name: 'guide.searchLabel' })
const type = (value) => { fireEvent.focus(field()); fireEvent.change(field(), { target: { value } }) }
const results = () => [...document.querySelectorAll('.guide-result')]
const status = () => screen.getByRole('status').textContent

beforeEach(() => {
  h.load.mockReset()
  h.load.mockRejectedValue(new Error('no file'))
})

describe('GuideSearch', () => {
  it('loads nothing until the field is first focused', async () => {
    loadEnglishHelp.mockClear()
    show()
    expect(loadEnglishHelp).not.toHaveBeenCalled()
    fireEvent.focus(field())
    expect(loadEnglishHelp).toHaveBeenCalled()
  })

  it('finds every section holding all the words, whatever the case, and announces the count', async () => {
    const index = await loadGuideIndex(null)
    const expected = searchIndex(index, queryTerms('certificate authority'))
    expect(expected.length).toBeGreaterThan(1)
    show()
    type('CERTIFICATE Authority')
    await waitFor(() => expect(results().length).toBe(Math.min(expected.length, 60)))
    expect(status()).toBe(`guide.results:${expected.length}`)
    const heads = [...document.querySelectorAll('.guide-results-head')].map((x) => x.textContent)
    expect(new Set(heads).size).toBe(heads.length)
    expect(results()[0].querySelectorAll('mark.guide-hit').length).toBeGreaterThan(0)
  })

  it('folds the accents of the query and of the text, in the reading language', async () => {
    h.load.mockImplementation((lang, key) => (key === 'cas'
      ? Promise.resolve({ default: { helpGuides: { title: 'Autorités', content: '## Révocation\nLa liste de révocation que publie l’autorité, mise à jour chaque nuit.' } } })
      : Promise.reject(new Error('none'))))
    show('fr')
    type('revocation AUTORITE')
    await waitFor(() => expect(results()).toHaveLength(1))
    const [r] = results()
    expect(r.closest('.guide-results-group').querySelector('.guide-results-head').textContent).toBe('Autorités')
    expect(r.querySelector('.name').textContent).toBe('Révocation')
    expect([...r.querySelectorAll('mark')].map((m) => m.textContent)).toEqual(['Révocation', 'révocation', 'autorité'])
    expect(r.querySelector('.guide-excerpt').textContent).toContain('liste de révocation')
  })

  it('says so when no section holds every word', async () => {
    show()
    type('certificate zzzqqq')
    expect(await screen.findByText('guide.noResults', { selector: '.guide-results p' })).toBeTruthy()
    expect(status()).toBe('guide.noResults')
    expect(results()).toHaveLength(0)
  })

  it('opens a result on a click, the words in the address for the chapter to mark them', async () => {
    show()
    type('ocsp responder')
    await waitFor(() => expect(results().length).toBeGreaterThan(0))
    const index = await loadGuideIndex(null)
    const [first] = searchIndex(index, queryTerms('ocsp responder'))
    fireEvent.click(results()[0])
    expect(screen.getByTestId('where').textContent).toBe(`/guide/${first.chapter}?q=ocsp%20responder${first.id ? `#${first.id}` : ''}`)
    expect(document.querySelector('.guide-results')).toBeNull()
  })

  it('moves with the arrows, opens with Enter, closes with Escape', async () => {
    show()
    type('acme account')
    await waitFor(() => expect(results().length).toBeGreaterThan(1))
    fireEvent.keyDown(field(), { key: 'ArrowDown' })
    expect(document.activeElement).toBe(results()[0])
    fireEvent.keyDown(results()[0], { key: 'ArrowDown' })
    expect(document.activeElement).toBe(results()[1])
    fireEvent.keyDown(results()[1], { key: 'ArrowUp' })
    expect(document.activeElement).toBe(results()[0])
    fireEvent.keyDown(results()[0], { key: 'ArrowUp' })
    expect(document.activeElement).toBe(field())
    fireEvent.keyDown(results()[0], { key: 'Escape' })
    expect(document.querySelector('.guide-results')).toBeNull()
    expect(document.activeElement).toBe(field())
    fireEvent.change(field(), { target: { value: 'acme account' } })
    fireEvent.keyDown(field(), { key: 'Enter' })
    expect(screen.getByTestId('where').textContent).toMatch(/^\/guide\/[^?]+\?q=acme%20account/)
  })

  it('names the results region and its chapters', async () => {
    show()
    type('crl')
    const region = await screen.findByRole('region', { name: 'guide.resultsLabel' })
    await waitFor(() => expect(within(region).getAllByRole('heading', { level: 2 }).length).toBeGreaterThan(0))
  })
})
