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
const casHeads = () => guideHeadings('cas', helpGuides.cas.content).filter((x) => x.level <= 3)

beforeAll(async () => { await loadEnglishHelp() })
beforeEach(() => {
  h.lang = 'en'
  h.perms = []
  h.load.mockReset()
  Element.prototype.scrollIntoView = vi.fn()
})
afterEach(() => { delete Element.prototype.scrollIntoView })

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

  it('reaches the section of the anchor and gives it the focus', async () => {
    const target = casHeads().filter((x) => x.level === 2)[2]
    show(`/guide/cas#${target.id}`)
    await screen.findByRole('heading', { level: 1 })
    const node = document.getElementById(target.id)
    await waitFor(() => expect(document.activeElement).toBe(node))
    expect(node.scrollIntoView).toHaveBeenCalled()
    expect(within(toc()).getByRole('link', { name: target.text })).toHaveAttribute('aria-current', 'true')
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

  it('lists the ## and ### of the chapter read under it, not its ####', async () => {
    show('/guide/acme')
    await screen.findByRole('heading', { level: 1 })
    const listed = [...toc().querySelectorAll('.guide-toc-sections a')].map((a) => a.getAttribute('href'))
    expect(listed).toEqual(guideHeadings('acme', helpGuides.acme.content).filter((x) => x.level <= 3).map((x) => `#${x.id}`))
    expect(toc().querySelectorAll('.guide-toc-sections')).toHaveLength(1)
  })

  it('follows the reading: the last heading above the column\'s top is the current section', async () => {
    show('/guide/cas')
    await screen.findByRole('heading', { level: 1 })
    const box = document.querySelector('.guide-scroll')
    const heads = casHeads().filter((x) => x.level <= 3)
    const tops = Object.fromEntries(heads.map((x, i) => [x.id, i < 3 ? -100 + i * 10 : 500 + i]))
    const spy = vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function rect() {
      const top = this === box ? 0 : (tops[this.id] ?? 900)
      return { top, bottom: top + 20, left: 0, right: 0, width: 0, height: 20, x: 0, y: top }
    })
    fireEvent.scroll(box)
    expect(within(toc()).getByRole('link', { name: heads[2].text })).toHaveAttribute('aria-current', 'true')
    spy.mockRestore()
  })

  it('jumps to a section from the contents and puts it in the address', async () => {
    show('/guide/cas')
    await screen.findByRole('heading', { level: 1 })
    const target = casHeads()[3]
    fireEvent.click(within(toc()).getByRole('link', { name: target.text }))
    await waitFor(() => expect(where()).toBe(`/guide/cas#${target.id}`))
    expect(document.activeElement).toBe(document.getElementById(target.id))
  })

  it('on a phone, the selects go to a chapter and to a section', async () => {
    show('/guide/cas')
    await screen.findByRole('heading', { level: 1 })
    fireEvent.change(screen.getByLabelText('guide.jumpChapter'), { target: { value: 'tsa' } })
    await waitFor(() => expect(where()).toBe('/guide/tsa'))
    await screen.findByRole('heading', { level: 1, name: helpGuides.tsa.title })
    const target = guideHeadings('tsa', helpGuides.tsa.content)[1]
    fireEvent.change(screen.getByLabelText('guide.jumpSection'), { target: { value: target.id } })
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
    expect(h.load).not.toHaveBeenCalled()
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
  })
})

describe('GuidePage: printing', () => {
  it('lays every chapter one after the other for the whole guide', async () => {
    const print = vi.spyOn(window, 'print').mockImplementation(() => {})
    show('/guide?print=all')
    await waitFor(() => expect(document.querySelectorAll('.guide-print-chapter')).toHaveLength(GUIDE_CHAPTERS.length))
    const chapters = [...document.querySelectorAll('.guide-print-chapter')].map((a) => a.dataset.chapter)
    expect(chapters).toEqual(GUIDE_CHAPTERS.map((c) => c.key))
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
