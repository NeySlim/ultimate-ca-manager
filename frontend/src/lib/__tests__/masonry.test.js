/** Masonry of the overview grid: row spans from the cards' own heights, the DOM order untouched. */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { masonrySpans, packGrid } from '../masonry'

describe('masonrySpans', () => {
  it('gives each card its height plus one gap, in rows of one pixel', () => {
    expect(masonrySpans([300, 900.2, 480], 20)).toEqual({ unit: 1, spans: [320, 921, 500] })
  })

  it('coarsens the rows rather than pass the line limit of a browser', () => {
    const { unit, spans } = masonrySpans([9000, 9000, 500], 20)
    expect(unit).toBe(3)
    expect(spans).toEqual([3007, 3007, 174])
    expect(spans.reduce((a, b) => a + b, 0)).toBeLessThan(10000)
  })

  it('never gives a span the grid would refuse', () => {
    expect(masonrySpans([0, 0], 0)).toEqual({ unit: 1, spans: [1, 1] })
  })
})

describe('packGrid', () => {
  afterEach(() => { document.body.innerHTML = '' })

  it('writes the span of each slot from the card it holds and leaves the order alone', () => {
    document.body.innerHTML = '<div id="g" style="column-gap: 20px"><div><section id="a"></section></div><div><section id="b"></section></div></div>'
    const grid = document.getElementById('g')
    const heights = { a: 300, b: 640 }
    vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function rect() { return { height: heights[this.id] ?? 0 } })
    packGrid(grid)
    vi.restoreAllMocks()
    expect([...grid.children].map((s) => s.style.gridRowEnd)).toEqual(['span 320', 'span 660'])
    expect(grid.style.gridAutoRows).toBe('1px')
    expect(grid.hasAttribute('data-masonry')).toBe(true)
    expect([...grid.querySelectorAll('section')].map((s) => s.id)).toEqual(['a', 'b'])
  })
})
