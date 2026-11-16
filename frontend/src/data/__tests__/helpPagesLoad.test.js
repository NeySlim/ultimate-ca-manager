/**
 * Every translated help page parses: the panel imports them one at a time,
 * so a broken file breaks the build and that page's help, nothing else.
 */
import { describe, it, expect } from 'vitest'
import { HELP_TRANSLATED_LANGUAGES } from '../helpLanguages'

const pages = import.meta.glob('../help/*/*.js')
const dirOf = (p) => p.split('/')[2]

describe('translated help pages', () => {
  it('finds pages for exactly the translated help languages', () => {
    expect([...new Set(Object.keys(pages).map(dirOf))].sort()).toEqual([...HELP_TRANSLATED_LANGUAGES].sort())
  })

  it.each(HELP_TRANSLATED_LANGUAGES)('%s has the same pages as French', (code) => {
    const names = (c) => Object.keys(pages).filter((p) => dirOf(p) === c).map((p) => p.split('/').pop()).sort()
    expect(names(code)).toEqual(names('fr'))
  })

  it('finds the pages', () => {
    expect(Object.keys(pages).length).toBeGreaterThan(60)
  })

  it.each(Object.keys(pages))('%s loads', async (path) => {
    const page = await pages[path]()
    expect(page.default).toBeTruthy()
  })
})
