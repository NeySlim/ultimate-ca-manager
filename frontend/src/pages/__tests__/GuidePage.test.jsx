/**
 * The guide in a tab of its own: one chapter at a time, its anchor reached once the text is in,
 * the contents grouped as the registry with the current chapter and section marked, the page of
 * the chapter for who may open it, the English help with its notice where there is no translation,
 * and every chapter at once for printing.
 */
import { describe, it, expect, vi, beforeAll, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent, within, act } from '@testing-library/react'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'

const h = vi.hoisted(() => ({ lang: 'en', perms: [], load: vi.fn() }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (key === 'guide.tabTitle' ? `${opts.chapter} · Guide · UCM` : key),
    i18n: { language: h.lang, resolvedLanguage: h.lang },
  }),
}))
vi.mock('../../data/helpLoader', () => ({ loadHelpPage: (...a) => h.load(...a) }))
vi.mock('../../hooks/usePermission', () => ({
  usePermission: () => ({ isAdmin: () => h.perms.includes('*'), hasPermission: (p) => h.perms.includes('*') || h.perms.includes(p) }),
}))

import GuidePage from '../GuidePage'
import { guideHeadings } from '../../components/help'
import { loadEnglishHelp } from '../../data/helpData'
import { GUIDE_CHAPTERS } from '../../navigation/guide'
import { helpGuides } from '../../data/helpGuides'
import { helpContent } from '../../data/helpContent'

function Where() {
  const l = useLocation()
  return <div data-testid="where">{l.pathname + l.search + l.hash}</div>
}
const show = (path) => render(
  <MemoryRouter initialEntries={[path]}>
    <Routes>
      <Route path="/guide" element={<GuidePage />} />
      <Route path="/guide/:chapter" element={<GuidePage />} />
      <Route path="*" element={<p>elsewhere</p>} />
    </Routes>
    <Where />
  </MemoryRouter>,
)
const where = () => screen.getByTestId('where').textContent
const toc = () => screen.getByRole('navigation', { name: 'guide.tocLabel' })
const onPage = () => screen.getByRole('navigation', { name: 'guide.onThisPage' })
const article = () => document.getElementById('guide-article')
const casHeads = () => guideHeadings('cas', helpGuides.cas.content).filter((x) => x.level <= 3)

beforeAll(async () => { await loadEnglishHelp() })
beforeEach(() => {
  h.lang = 'en'
  h.perms = []
  h.load.mockReset()
  Element.prototype.scrollIntoView = vi.fn()
  window.scrollTo = vi.fn()
})
afterEach(() => { delete Element.prototype.scrollIntoView; delete window.scrollTo })

describe('GuidePage: a chapter and its anchor', () => {
  it('opens a chapter with its title as the page\'s h1 and its sections as h2 and h3', async () => {
    show('/guide/cas')
    const title = await screen.findByRole('heading', { level: 1 })
    expect(title).toHaveTextContent(helpGuides.cas.title)
    const article = document.getElementById('guide-article')
    const [first] = casHeads()
    expect(within(article).getAllByRole('heading', { level: 2 })[0]).toHaveAttribute('id', first.id)
    expect(document.title).toBe(`${helpGuides.cas.title} · Guide · UCM`)
  })

  it('gives the tab its title back when the page is left', async () => {
    document.title = 'Before · UCM'
    const { unmount } = show('/guide/cas')
    await screen.findByRole('heading', { level: 1 })
    expect(document.title).toBe(`${helpGuides.cas.title} · Guide · UCM`)
    // A reader view takes its title from og:title: the chapter's, without the tab's « · Guide · UCM »
    expect(document.head.querySelector('meta[property="og:title"]')).toHaveAttribute('content', helpGuides.cas.title)
    unmount()
    expect(document.title).toBe('Before · UCM')
    expect(document.head.querySelector('meta[property="og:title"]')).toBeNull()
  })

  it('holds in its article the way to the chapter, its title, its subtitle and its text, nothing else', async () => {
    h.perms = ['*']
    show('/guide/cas')
    await screen.findByRole('heading', { level: 1 })
    const main = document.getElementById('main')
    const crumbs = within(article()).getByRole('navigation', { name: 'guide.breadcrumbLabel' })
    expect([...crumbs.querySelectorAll('li')].map((li) => li.textContent)).toEqual(['common.navPki', 'common.cas'])
    expect(crumbs.querySelector('[aria-current="page"]')).toHaveTextContent('common.cas')
    expect(crumbs.compareDocumentPosition(screen.getByRole('heading', { level: 1 })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    // The chapter's actions, its neighbours and its sections are the article's siblings in main, the actions first
    const open = screen.getByRole('link', { name: 'guide.openPage' })
    const print = screen.getByRole('button', { name: 'guide.printChapter' })
    const pager = screen.getByRole('navigation', { name: 'guide.pagerLabel' })
    for (const node of [open, print, pager, onPage(), screen.getByRole('link', { name: 'guide.printAll' })]) {
      expect(article().contains(node)).toBe(false)
      expect(main.contains(node)).toBe(true)
    }
    expect(open.compareDocumentPosition(article()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(print.compareDocumentPosition(article()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(article().querySelector('button, select')).toBeNull()
  })

  it('names "General" in the way to a chapter outside the registry\'s groups', async () => {
    show('/guide/navigation')
    await screen.findByRole('heading', { level: 1 })
    const crumbs = within(article()).getByRole('navigation', { name: 'guide.breadcrumbLabel' })
    expect([...crumbs.querySelectorAll('li')].map((li) => li.textContent)).toEqual(['guide.general', 'commands.categories.navigation'])
  })

  it('scrolls the document, not a column of its own', async () => {
    show('/guide/cas')
    await screen.findByRole('heading', { level: 1 })
    expect(document.querySelector('.guide-scroll')).toBeNull()
  })

  it('reaches the section of the anchor and gives it the focus', async () => {
    const target = casHeads().filter((x) => x.level === 2)[2]
    show(`/guide/cas#${target.id}`)
    await screen.findByRole('heading', { level: 1 })
    const node = document.getElementById(target.id)
    await waitFor(() => expect(document.activeElement).toBe(node))
    expect(node.scrollIntoView).toHaveBeenCalled()
    expect(within(onPage()).getByRole('link', { name: target.text })).toHaveAttribute('aria-current', 'true')
  })

  it('/guide opens the chapter of the section asked for, else the first chapter', async () => {
    const target = casHeads()[1]
    const { unmount } = show(`/guide#${target.id}`)
    await waitFor(() => expect(where()).toBe(`/guide/cas#${target.id}`))
    unmount()
    show('/guide')
    await waitFor(() => expect(where()).toBe(`/guide/${GUIDE_CHAPTERS[0].key}`))
  })

  it('sends an unknown or retired chapter to the first one', async () => {
    const { unmount } = show('/guide/nope')
    await waitFor(() => expect(where()).toBe('/guide/navigation'))
    unmount()
    show('/guide/importExport')
    await waitFor(() => expect(where()).toBe('/guide/navigation'))
  })
})

describe('GuidePage: the contents', () => {
  it('groups the chapters as the registry and marks the one read', async () => {
    show('/guide/acme')
    await screen.findByRole('heading', { level: 1 })
    const heads = [...toc().querySelectorAll('.guide-toc-head')].map((x) => x.textContent)
    expect(heads).toEqual(['guide.general', 'common.navPki', 'common.navProtocols', 'common.navGovernance', 'common.navAdmin'])
    const current = toc().querySelectorAll('a[aria-current="page"]')
    expect(current).toHaveLength(1)
    expect(current[0]).toHaveAttribute('href', '/guide/acme')
    // Every chapter is offered, the retired one is not; the chapters without a page today are there
    const hrefs = [...toc().querySelectorAll('a[href^="/guide/"]')].map((a) => a.getAttribute('href'))
    expect(hrefs).toEqual(GUIDE_CHAPTERS.map((c) => `/guide/${c.key}`))
    for (const k of ['systemLogs', 'sso', 'security', 'msca']) expect(hrefs).toContain(`/guide/${k}`)
    expect(hrefs).not.toContain('/guide/importExport')
  })

  it('lists the chapters alone at the left, without their sections', async () => {
    show('/guide/acme')
    await screen.findByRole('heading', { level: 1 })
    expect(toc().querySelectorAll('a[href^="#"]')).toHaveLength(0)
    expect(toc().querySelectorAll('.guide-toc-sections')).toHaveLength(0)
  })

  it('lists the ## and ### of the chapter read on this page, each level marked, not its ####', async () => {
    show('/guide/acme')
    await screen.findByRole('heading', { level: 1 })
    const all = guideHeadings('acme', helpGuides.acme.content).filter((x) => x.level <= 3)
    const listed = [...onPage().querySelectorAll('a')]
    expect(listed.map((a) => a.getAttribute('href'))).toEqual(all.map((x) => `#${x.id}`))
    expect(listed.map((a) => a.dataset.level)).toEqual(all.map((x) => String(x.level)))
    expect(new Set(listed.map((a) => a.className))).toEqual(new Set(['guide-onpage-h2', 'guide-onpage-h3']))
    // A ### sits in the list of the ## above it
    const sub = listed.find((a) => a.dataset.level === '3')
    expect(sub.closest('ul').closest('li').querySelector(':scope > a').dataset.level).toBe('2')
    // The same list folds above the article where there is no room for the column
    const fold = document.querySelector('details.guide-onpage-fold')
    expect(fold.querySelector('summary')).toHaveTextContent('guide.onThisPage')
    expect([...fold.querySelectorAll('a')].map((a) => a.getAttribute('href'))).toEqual(all.map((x) => `#${x.id}`))
    expect(fold.compareDocumentPosition(article()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('has no section list for the navigation chapter, a quick help', async () => {
    show('/guide/navigation')
    await screen.findByRole('heading', { level: 1 })
    expect(screen.queryByRole('navigation', { name: 'guide.onThisPage' })).toBeNull()
  })

  it('follows the reading: the last heading above the bar\'s foot is the current section', async () => {
    show('/guide/cas')
    await screen.findByRole('heading', { level: 1 })
    const bar = document.querySelector('.guide-head')
    const heads = casHeads().filter((x) => x.level <= 3)
    // Under the sticky bar (62 px): the third heading at 90 px is passed, the fourth at 130 px is not
    const tops = Object.fromEntries(heads.map((x, i) => [x.id, i < 3 ? -100 + i * 95 : 130 + i]))
    const spy = vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function rect() {
      const top = this === bar ? 0 : (tops[this.id] ?? 900)
      const height = this === bar ? 62 : 20
      return { top, bottom: top + height, left: 0, right: 0, width: 0, height, x: 0, y: top }
    })
    fireEvent.scroll(window)
    expect(within(onPage()).getByRole('link', { name: heads[2].text })).toHaveAttribute('aria-current', 'true')
    expect(within(onPage()).getByRole('link', { name: heads[3].text })).not.toHaveAttribute('aria-current')
    spy.mockRestore()
  })

  it('jumps to a section from the contents and puts it in the address', async () => {
    show('/guide/cas')
    await screen.findByRole('heading', { level: 1 })
    const target = casHeads()[3]
    fireEvent.click(within(onPage()).getByRole('link', { name: target.text }))
    await waitFor(() => expect(where()).toBe(`/guide/cas#${target.id}`))
    expect(document.activeElement).toBe(document.getElementById(target.id))
  })

  it('on a phone, the select goes to a chapter and the folded On this page to a section', async () => {
    show('/guide/cas')
    await screen.findByRole('heading', { level: 1 })
    window.scrollTo.mockClear()
    fireEvent.change(screen.getByLabelText('guide.jumpChapter'), { target: { value: 'tsa' } })
    await waitFor(() => expect(where()).toBe('/guide/tsa'))
    await screen.findByRole('heading', { level: 1, name: helpGuides.tsa.title })
    // Another chapter opens at its top: the document scrolls back
    expect(window.scrollTo).toHaveBeenCalledWith(0, 0)
    const target = guideHeadings('tsa', helpGuides.tsa.content)[1]
    const fold = document.querySelector('details.guide-onpage-fold')
    fireEvent.click(within(fold).getByRole('link', { name: target.text }))
    await waitFor(() => expect(where()).toBe(`/guide/tsa#${target.id}`))
  })
})

describe('GuidePage: the foot of a chapter', () => {
  it('offers the page of the chapter to who may open it, and only then', async () => {
    h.perms = ['read:acme']
    const { unmount } = show('/guide/acme')
    await screen.findByRole('heading', { level: 1 })
    expect(screen.getByRole('link', { name: 'guide.openPage' })).toHaveAttribute('href', '/acme')
    unmount()
    h.perms = []
    show('/guide/acme')
    await screen.findByRole('heading', { level: 1 })
    expect(screen.queryByRole('link', { name: 'guide.openPage' })).toBeNull()
  })

  it('opens a settings tab for its chapter, to an administrator', async () => {
    h.perms = ['*']
    show('/guide/security')
    await screen.findByRole('heading', { level: 1 })
    expect(screen.getByRole('link', { name: 'guide.openPage' })).toHaveAttribute('href', '/settings?tab=security')
  })

  it('links the previous and next chapters in reading order', async () => {
    const i = GUIDE_CHAPTERS.findIndex((c) => c.key === 'cas')
    show('/guide/cas')
    await screen.findByRole('heading', { level: 1 })
    const pager = screen.getByRole('navigation', { name: 'guide.pagerLabel' })
    expect(within(pager).getByRole('link', { name: /guide\.previous/ })).toHaveAttribute('href', `/guide/${GUIDE_CHAPTERS[i - 1].key}`)
    expect(within(pager).getByRole('link', { name: /guide\.next/ })).toHaveAttribute('href', `/guide/${GUIDE_CHAPTERS[i + 1].key}`)
  })

  it('leads back to the console', async () => {
    show('/guide/cas')
    await screen.findByRole('heading', { level: 1 })
    expect(screen.getByRole('link', { name: 'help.back' })).toHaveAttribute('href', '/')
  })
})

describe('GuidePage: the navigation chapter', () => {
  it('is the quick help of the navigation', async () => {
    show('/guide/navigation')
    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent(helpContent.navigation.title)
    const grid = document.querySelector('#guide-article .help-grid')
    expect(grid).toBeTruthy()
    expect(grid).toHaveTextContent(helpContent.navigation.sections[0].title)
    expect(grid).toHaveTextContent('Open in a new tab')
  })
})

describe('GuidePage: languages', () => {
  it.each(['de', 'ja', 'uk'])('shows English with the notice for %s, without loading a translation', async (lang) => {
    h.lang = lang
    show('/guide/cas')
    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent(helpGuides.cas.title)
    expect(screen.getByText('help.englishOnlyNotice')).toBeTruthy()
    expect(article().contains(screen.getByText('help.englishOnlyNotice'))).toBe(false)
    expect(article()).toHaveAttribute('lang', 'en')
    expect(h.load).not.toHaveBeenCalled()
  })

  it('marks an English chapter as English', async () => {
    show('/guide/cas')
    await screen.findByRole('heading', { level: 1 })
    expect(article()).toHaveAttribute('lang', 'en')
  })

  it('reads a translated chapter, and reaches its anchor only once the translation is in', async () => {
    h.lang = 'fr'
    let resolve
    h.load.mockImplementation(() => new Promise((r) => { resolve = r }))
    const target = casHeads()[2]
    show(`/guide/cas#${target.id}`)
    await waitFor(() => expect(h.load).toHaveBeenCalledWith('fr', 'cas'))
    expect(screen.queryByText('help.englishOnlyNotice')).toBeNull()
    expect(document.getElementById(target.id)).toBeNull()
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled()
    const translated = helpGuides.cas.content.replace(/^(#{2,3}) (.+)$/gm, '$1 FR $2')
    await act(async () => { resolve({ default: { helpGuides: { title: 'Autorités', content: translated } } }) })
    expect(await screen.findByRole('heading', { level: 1, name: 'Autorités' })).toBeTruthy()
    const node = document.getElementById(target.id)
    expect(node.textContent).toBe(`FR ${target.text}`)
    await waitFor(() => expect(document.activeElement).toBe(node))
    expect(article()).toHaveAttribute('lang', 'fr')
  })

  it('marks as English a chapter its language has no text for', async () => {
    h.lang = 'fr'
    h.load.mockRejectedValue(new Error('no file'))
    show('/guide/tsa')
    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent(helpGuides.tsa.title)
    expect(article()).toHaveAttribute('lang', 'en')
  })
})

describe('GuidePage: the words of a search', () => {
  it('stay marked in the chapter opened from a result, not in the contents', async () => {
    show('/guide/cas?q=Root%20ca')
    await screen.findByRole('heading', { level: 1 })
    const article = document.getElementById('guide-article')
    const found = [...article.querySelectorAll('mark.guide-hit')].map((m) => m.textContent.toLowerCase())
    expect(found.length).toBeGreaterThan(3)
    expect(new Set(found)).toEqual(new Set(['root', 'ca']))
    expect(toc().querySelector('mark')).toBeNull()
  })

  // Each language below is read by one test only: a translated page is loaded once per language and kept
  it('are marked whatever their accents in a translated chapter', async () => {
    h.lang = 'zh'
    h.load.mockResolvedValue({ default: { helpGuides: { title: 'Autorités', content: '## Autorité racine\nUne autorité signe.' } } })
    show('/guide/cas?q=autorite')
    await screen.findByRole('heading', { level: 1, name: 'Autorités' })
    expect([...document.querySelectorAll('#guide-article mark')].map((m) => m.textContent)).toEqual(['Autorité', 'autorité'])
  })

  it('loads no index before the search is used, every chapter at its first focus', async () => {
    h.lang = 'ru'
    h.load.mockResolvedValue({ default: { helpGuides: { title: 'Autorités', content: '## Vue\ntexte' } } })
    show('/guide/cas')
    await screen.findByRole('heading', { level: 1, name: 'Autorités' })
    expect(h.load.mock.calls.map((c) => c[1])).toEqual(['cas'])
    fireEvent.focus(screen.getByRole('searchbox', { name: 'guide.searchLabel' }))
    await waitFor(() => expect(new Set(h.load.mock.calls.map((c) => c[1]))).toEqual(new Set(GUIDE_CHAPTERS.map((c) => c.key))))
  })
})

describe('GuidePage: printing', () => {
  it('lays every chapter one after the other for the whole guide', async () => {
    const print = vi.spyOn(window, 'print').mockImplementation(() => {})
    show('/guide?print=all')
    await waitFor(() => expect(document.querySelectorAll('.guide-print-chapter')).toHaveLength(GUIDE_CHAPTERS.length))
    const chapters = [...document.querySelectorAll('.guide-print-chapter')].map((a) => a.dataset.chapter)
    expect(chapters).toEqual(GUIDE_CHAPTERS.map((c) => c.key))
    expect(new Set([...document.querySelectorAll('.guide-print-chapter')].map((x) => x.getAttribute('lang')))).toEqual(new Set(['en']))
    expect(document.querySelector('.guide-toc')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'guide.print' }))
    expect(print).toHaveBeenCalled()
    print.mockRestore()
  })

  it('offers the whole guide from a chapter', async () => {
    show('/guide/cas')
    await screen.findByRole('heading', { level: 1 })
    expect(screen.getByRole('link', { name: 'guide.printAll' })).toHaveAttribute('href', '/guide?print=all')
  })
})
