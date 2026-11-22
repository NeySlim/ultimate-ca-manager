/** Open-object strip: how many tabs fit, and which go to the « +N » menu. */
import { describe, it, expect } from 'vitest'
import { tabsThatFit, splitTabs, splitByWidth, MORE_W } from '../tabFit'

describe('tabsThatFit', () => {
  it('keeps every tab while they all fit, or while nothing is measured yet', () => {
    expect(tabsThatFit(1000, 120, 8)).toBe(Infinity)
    expect(tabsThatFit(0, 120, 30)).toBe(Infinity)
    expect(tabsThatFit(undefined, 120, 30)).toBe(Infinity)
  })

  it('gives up the width of the « +N » button when they overflow, one tab at least', () => {
    expect(tabsThatFit(400, 96, 6)).toBe(Math.floor((400 - MORE_W) / 96))
    expect(tabsThatFit(100, 96, 3)).toBe(1)
  })
})

describe('splitTabs', () => {
  const keys = ['a', 'b', 'c', 'd', 'e']

  it('shows all of them when they fit', () => {
    expect(splitTabs(keys, 'e', Infinity)).toEqual({ shown: keys, hidden: [] })
  })

  it('leaves the rest to the menu in their order', () => {
    expect(splitTabs(keys, 'a', 2)).toEqual({ shown: ['a', 'b'], hidden: ['c', 'd', 'e'] })
  })

  it('always shows the active tab, in the last slot', () => {
    expect(splitTabs(keys, 'e', 2)).toEqual({ shown: ['a', 'e'], hidden: ['b', 'c', 'd'] })
    expect(splitTabs(keys, 'd', 1)).toEqual({ shown: ['d'], hidden: ['a', 'b', 'c', 'e'] })
  })
})

describe('splitByWidth', () => {
  const keys = ['a', 'b', 'c', 'd']
  const widths = { a: 100, b: 100, c: 100, d: 100 }
  it('shows every tab that fits, and all of them while unmeasured', () => {
    expect(splitByWidth(keys, widths, 'a', 400, 60)).toEqual({ shown: keys, hidden: [] })
    expect(splitByWidth(keys, {}, 'a', 100, 60)).toEqual({ shown: keys, hidden: [] })
    expect(splitByWidth(keys, widths, 'a', 0, 60)).toEqual({ shown: keys, hidden: [] })
  })
  it('keeps the first ones beside the « More » button', () => {
    expect(splitByWidth(keys, widths, 'a', 300, 60)).toEqual({ shown: ['a', 'b'], hidden: ['c', 'd'] })
  })
  it('puts the active one beyond in the last place, keeping its room', () => {
    expect(splitByWidth(keys, widths, 'd', 300, 60)).toEqual({ shown: ['a', 'd'], hidden: ['b', 'c'] })
    expect(splitByWidth(keys, { ...widths, d: 250 }, 'd', 300, 60)).toEqual({ shown: ['d'], hidden: ['a', 'b', 'c'] })
  })
})
