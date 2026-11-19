/** Chart geometry: a curve that stays between its points, round axis tops, slices that fill the ring. */
import { describe, it, expect } from 'vitest'
import { donutSlices, monotonePath, niceMax, tickIndexes } from '../overviewChart'

const numbers = (d) => d.replace(/[MC]/g, ' ').trim().split(/[ ,]+/).map(Number)

describe('monotone path', () => {
  it('starts and ends on the first and last points', () => {
    const d = monotonePath([[0, 100], [50, 20], [100, 60]])
    expect(d.startsWith('M0,100C')).toBe(true)
    expect(d.endsWith('100,60')).toBe(true)
  })

  it('never leaves the range of its points: a zero stays the floor after a peak', () => {
    const points = [[0, 100], [10, 100], [20, 5], [30, 100], [40, 100], [50, 40], [60, 100]]
    const ys = numbers(monotonePath(points)).filter((_, i) => i % 2 === 1)
    expect(Math.max(...ys)).toBeLessThanOrEqual(100)
    expect(Math.min(...ys)).toBeGreaterThanOrEqual(5)
  })

  it('draws a flat line flat, one point as a move, nothing for no point', () => {
    expect(numbers(monotonePath([[0, 7], [5, 7], [10, 7]])).filter((_, i) => i % 2 === 1).every((y) => y === 7)).toBe(true)
    expect(monotonePath([[3, 4]])).toBe('M3,4')
    expect(monotonePath([])).toBe('')
  })
})

describe('axis', () => {
  it.each([[0, 4], [3, 4], [5, 6], [7, 8], [10, 10], [12, 20], [37, 40], [41, 60], [99, 100], [100, 100], [130, 200]])(
    'the top for %i is %i', (value, top) => { expect(niceMax(value)).toBe(top) })

  it('the middle tick of a count is a whole number', () => {
    for (let v = 0; v <= 1200; v += 1) {
      expect(niceMax(v)).toBeGreaterThanOrEqual(v)
      expect(Number.isInteger(niceMax(v) / 2), String(v)).toBe(true)
    }
  })

  it('spreads ticks from the first to the last index', () => {
    expect(tickIndexes(7, 7)).toEqual([0, 1, 2, 3, 4, 5, 6])
    expect(tickIndexes(30)).toEqual([0, 7, 15, 22, 29])
    expect(tickIndexes(3)).toEqual([0, 1, 2])
  })
})

describe('donut slices', () => {
  const C = 360
  it('skips a zero, keeps the order, and leaves a gap between two slices', () => {
    const slices = donutSlices([{ key: 'a', value: 3 }, { key: 'b', value: 0 }, { key: 'c', value: 1 }], C)
    expect(slices.map((s) => s.key)).toEqual(['a', 'c'])
    expect(slices[0].length).toBeCloseTo(268)
    expect(slices[1].offset).toBeCloseTo(271)
    expect(slices[1].length).toBeCloseTo(88)
  })

  it('a single state fills the ring without a gap; no value draws nothing', () => {
    expect(donutSlices([{ key: 'a', value: 9 }, { key: 'b', value: 0 }], C)).toEqual([{ key: 'a', value: 9, length: C, offset: 0 }])
    expect(donutSlices([{ key: 'a', value: 0 }], C)).toEqual([])
  })

  it('a tiny share still shows', () => {
    const [, small] = donutSlices([{ key: 'a', value: 100000 }, { key: 'b', value: 1 }], C)
    expect(small.length).toBeGreaterThanOrEqual(1)
  })
})
