/**
 * The guide's chapter drawn at build time (ssr/guideServer.jsx) is taken over by the console as it
 * stands: the same nodes, no hydration warning, the account's rights added once React holds it.
 * A page the client would draw otherwise (another language, a query) is drawn afresh.
 */
import { describe, it, expect, vi, beforeAll, beforeEach, afterEach } from 'vitest'
import { act } from '@testing-library/react'
import React from 'react'
import { hydrateRoot } from 'react-dom/client'

const h = vi.hoisted(() => ({ verify: null }))

vi.mock('../../services/auth.service', () => ({ authService: { getCurrentUser: () => h.verify() } }))
vi.mock('../../hooks/useWebSocket', () => ({
  WebSocketProvider: ({ children }) => children,
  useWebSocket: () => ({ subscribe: () => () => {}, isConnected: false, connectionState: 'disconnected' }),
  ConnectionState: { CONNECTING: 'connecting', CONNECTED: 'connected', DISCONNECTED: 'disconnected' },
}))

import App from '../../App'
import i18n from '../../i18n'
import { renderChapter } from '../guideServer'
import { takeOverServedGuide } from '../takeOver'
import { setServedPage } from '../../lib/servedPage'

let container
let root
let errors

async function drawn(lang, chapter) {
  const { html, title, chapterTitle } = await renderChapter(lang, chapter)
  // The head the server sends with the chapter (scripts/prerender-guide.js)
  document.title = title
  const meta = document.createElement('meta')
  meta.setAttribute('property', 'og:title')
  meta.setAttribute('content', chapterTitle)
  document.head.appendChild(meta)
  container = document.createElement('div')
  container.id = 'root'
  container.dataset.guide = `${lang}/${chapter}`
  container.innerHTML = html
  document.body.appendChild(container)
  window.history.pushState({}, '', `/guide/${chapter}`)
  return container
}

async function hydrate() {
  // Only what the browser would see: the server render's own dev warnings are not the page's
  errors.mockClear()
  await act(async () => { root = hydrateRoot(container, <React.StrictMode><App /></React.StrictMode>) })
  await act(async () => { await new Promise((r) => setTimeout(r, 0)) })
}

const signedIn = (permissions) => () => Promise.resolve({ data: { authenticated: true, user: { id: 1, username: 'reader' }, permissions, preferences: {} } })

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn()
  window.scrollTo = vi.fn()
})
beforeEach(() => {
  window.scrollTo.mockClear()
  h.verify = () => new Promise(() => {})
  errors = vi.spyOn(console, 'error')
  vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
})
afterEach(async () => {
  if (root) await act(async () => root.unmount())
  root = null
  container?.remove()
  document.head.querySelectorAll('meta[property="og:title"]').forEach((m) => m.remove())
  setServedPage(null)
  errors.mockRestore()
  vi.unstubAllGlobals()
  window.history.pushState({}, '', '/')
  await i18n.changeLanguage('en')
})

describe('the guide drawn at build time', () => {
  it.each([['en', 'cas'], ['fr', 'cas'], ['zh', 'acme'], ['ru', 'navigation']])('holds the chapter %s/%s, its title and sections, without the rights', async (lang, chapter) => {
    const { html, title, chapterTitle } = await renderChapter(lang, chapter)
    const page = document.createElement('div')
    page.innerHTML = html
    const h1 = page.querySelector('#guide-article h1')
    expect(h1.textContent).toBe(chapterTitle)
    expect(title).toBe(i18n.t('guide.tabTitle', { chapter: chapterTitle }))
    expect(page.querySelector('#guide-article').getAttribute('lang')).toBe(lang)
    expect(page.querySelectorAll('#guide-article h2, #guide-article .help-grid h3').length).toBeGreaterThan(3)
    if (chapter !== 'navigation') expect(page.querySelector('.guide-onpage a[href^="#"]')).not.toBeNull()
    expect(page.querySelector('.guide-wait')).toBeNull()
    // Labels of the language served
    expect(page.querySelector('.guide-toc').getAttribute('aria-label')).toBe(i18n.getFixedT(lang)('guide.tocLabel'))
    expect(page.querySelector('.guide-actions a')).toBeNull()
  })

  it('leaves the page of the chapter out even where no right is needed to open it', async () => {
    const { html } = await renderChapter('en', 'account')
    const page = document.createElement('div')
    page.innerHTML = html
    expect(page.querySelector('.guide-actions a')).toBeNull()
    expect(page.textContent).not.toContain(i18n.t('guide.openPage'))
  })
})

describe('the console takes the drawn chapter over', () => {
  it.each([['en', 'cas'], ['fr', 'acme'], ['ru', 'navigation'], ['zh', 'cas']])('keeps the nodes of %s/%s and warns of nothing', async (lang, chapter) => {
    await drawn(lang, chapter)
    const title = container.querySelector('#guide-title')
    const body = container.querySelector('#guide-article').lastElementChild
    expect(await takeOverServedGuide(container, window.location)).toBe(true)
    await hydrate()
    expect(errors).not.toHaveBeenCalled()
    expect(container.querySelector('#guide-title')).toBe(title)
    expect(container.querySelector('#guide-article').lastElementChild).toBe(body)
    expect(title.isConnected).toBe(true)
    // The page may have been scrolled before React took it over: it is left where it is
    expect(window.scrollTo).not.toHaveBeenCalled()
    expect(document.title).toBe(i18n.t('guide.tabTitle', { chapter: title.textContent }))
    // The server's og:title is the one kept, not a second one
    const metas = document.head.querySelectorAll('meta[property="og:title"]')
    expect([...metas].map((m) => m.getAttribute('content'))).toEqual([title.textContent])
  })

  it('adds the page of the chapter once the session says what the account may open', async () => {
    let answer
    h.verify = () => new Promise((resolve) => { answer = resolve })
    // ACME's page needs read:acme: no way to it before the session says the account has it
    await drawn('en', 'acme')
    expect(await takeOverServedGuide(container, window.location)).toBe(true)
    await hydrate()
    expect(container.querySelector('.guide-actions a')).toBeNull()
    await act(async () => { answer(await signedIn(['*'])()) })
    expect(container.querySelector('.guide-actions a')?.getAttribute('href')).toBe('/acme')
    expect(errors).not.toHaveBeenCalled()
  })

  it('marks the section of the address once React holds the page', async () => {
    await drawn('en', 'cas')
    const id = container.querySelectorAll('#guide-article h2')[2].id
    window.history.replaceState({}, '', `/guide/cas#${id}`)
    expect(await takeOverServedGuide(container, window.location)).toBe(true)
    await hydrate()
    expect(errors).not.toHaveBeenCalled()
    expect(container.querySelector(`.guide-onpage a[href="#${id}"]`).getAttribute('aria-current')).toBe('true')
  })

  it('searches the words typed in the drawn field before it took the page over, and keeps them', async () => {
    await drawn('en', 'navigation')
    const field = container.querySelector('#guide-search')
    field.focus()
    field.value = 'REVOCATION crl'
    expect(await takeOverServedGuide(container, window.location)).toBe(true)
    await hydrate()
    await act(async () => { await new Promise((r) => setTimeout(r, 50)) })
    expect(errors).not.toHaveBeenCalled()
    expect(container.querySelector('#guide-search')).toBe(field)
    expect(field.value).toBe('REVOCATION crl')
    expect(container.querySelectorAll('#guide-results .guide-result').length).toBeGreaterThan(0)
  })

  it.each([
    ['another language', async () => { await i18n.changeLanguage('de') }, '/guide/cas'],
    ['a query', async () => {}, '/guide/cas?q=crl'],
    ['another chapter', async () => {}, '/guide/acme'],
  ])('draws afresh under %s', async (_, change, address) => {
    await drawn('en', 'cas')
    await change()
    window.history.replaceState({}, '', address)
    expect(await takeOverServedGuide(container, window.location)).toBe(false)
  })

  it.each(['', 'en', 'en/cas/x', 'en/nothing', 'en/'])('draws afresh for the mark "%s"', async (mark) => {
    await drawn('en', 'cas')
    container.dataset.guide = mark
    expect(await takeOverServedGuide(container, window.location)).toBe(false)
  })
})
