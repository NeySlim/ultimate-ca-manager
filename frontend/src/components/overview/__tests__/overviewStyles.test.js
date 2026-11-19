/**
 * The stylesheet as the browser's own parser reads it: three columns from 1280 px, two from
 * 1024, one below; a card keeps its own height; motion stops on request.
 */
import { describe, it, expect, beforeAll, afterAll } from 'vitest'
import fs from 'fs'
import path from 'path'

let style
let sheet
beforeAll(() => {
  style = document.createElement('style')
  style.textContent = fs.readFileSync(path.resolve(__dirname, '../overview.css'), 'utf8')
  document.head.appendChild(style)
  sheet = style.sheet
})
afterAll(() => { style.remove() })

const media = (text) => [...sheet.cssRules].filter((r) => r.media && r.media.mediaText.replace(/\s/g, '') === text.replace(/\s/g, ''))
const rule = (rules, selector) => [...rules].find((r) => r.selectorText === selector)
const columns = (value) => {
  const repeat = /^repeat\((\d+),/.exec(value)
  return repeat ? Number(repeat[1]) : value.split(/\s+(?![^(]*\))/).length
}

describe('overview grid', () => {
  it('is one column by default, two from 1024 px, three from 1280 px', () => {
    expect(columns(rule(sheet.cssRules, '.ov-grid').style.getPropertyValue('grid-template-columns'))).toBe(1)
    const [two] = media('(min-width: 1024px)')
    const [three] = media('(min-width: 1280px)')
    expect(columns(rule(two.cssRules, '.ov-grid').style.getPropertyValue('grid-template-columns'))).toBe(2)
    expect(columns(rule(three.cssRules, '.ov-grid').style.getPropertyValue('grid-template-columns'))).toBe(3)
  })

  it('a card never stretches to the height of its neighbour', () => {
    const grid = document.createElement('div')
    grid.className = 'ov-grid'
    document.body.appendChild(grid)
    expect(getComputedStyle(grid).alignItems).toBe('start')
    grid.remove()
  })

  it('once measured, the cards pack by column: dense flow, and the row gap is part of each span', () => {
    const packed = rule(sheet.cssRules, '.ov-grid[data-masonry]').style
    expect(packed.getPropertyValue('grid-auto-flow')).toBe('row dense')
    expect(packed.getPropertyValue('row-gap')).toBe('0')
  })

  it('the page takes the whole width it is given', () => {
    const page = rule(sheet.cssRules, '.ov-page').style
    expect(page.getPropertyValue('flex')).toMatch(/^1\b/)
    expect(page.getPropertyValue('max-width')).toBe('')
  })

  it('the queue takes the whole row and a wide card two columns of three', () => {
    const [two] = media('(min-width: 1024px)')
    const [three] = media('(min-width: 1280px)')
    expect(rule(two.cssRules, '.ov-slot[data-span="full"]').style.getPropertyValue('grid-column').replace(/\s/g, '')).toBe('1/-1')
    expect(rule(three.cssRules, '.ov-slot[data-span="wide"]').style.getPropertyValue('grid-column')).toBe('span 2')
  })

  it('a compliance figure keeps its own height: its grid does not stretch to the algorithms beside it', () => {
    expect(rule(sheet.cssRules, '.ov-tiles').style.getPropertyValue('align-content')).toBe('start')
    expect(rule(sheet.cssRules, '.ov-compliance').style.getPropertyValue('align-items')).toBe('start')
    expect(columns(rule(sheet.cssRules, '.ov-compliance.has-algo').style.getPropertyValue('grid-template-columns'))).toBe(2)
  })

  it('stops its animations when the user asks for reduced motion', () => {
    const [reduced] = media('(prefers-reduced-motion: reduce)')
    const stopped = [...reduced.cssRules].filter((r) => r.style.getPropertyValue('animation') === 'none').map((r) => r.selectorText).join(', ')
    const animated = [...sheet.cssRules].filter((r) => r.style?.getPropertyValue('animation')).map((r) => r.selectorText)
    expect(animated.length).toBeGreaterThan(0)
    for (const selector of animated) expect(stopped).toContain(selector)
  })
})
