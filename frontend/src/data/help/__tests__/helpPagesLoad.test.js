/**
 * Every translated help page parses: the panel imports them one at a time,
 * so a broken file breaks the build and that page's help, nothing else.
 */
import { describe, it, expect } from 'vitest'

const pages = import.meta.glob('../*/*.js')

describe('translated help pages', () => {
  it('finds the pages', () => {
    expect(Object.keys(pages).length).toBeGreaterThan(200)
  })

  it.each(Object.keys(pages))('%s loads', async (path) => {
    const page = await pages[path]()
    expect(page.default).toBeTruthy()
  })
})
