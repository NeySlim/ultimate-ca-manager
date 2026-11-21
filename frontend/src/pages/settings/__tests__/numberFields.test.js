/** A number typed in a text field: empty stays empty, an unreadable entry stays as typed, never a default. */
import { describe, it, expect } from 'vitest'
import { shownNumber, typedNumber } from '../numberFields'

const typed = (value, as) => typedNumber({ target: { value } }, as)

describe('number fields', () => {
  it('shows a stored number through its unit, empty for nothing, the text for an unreadable entry', () => {
    expect(shownNumber(3600, (s) => s / 60)).toBe(60)
    expect(shownNumber('3600', (s) => s / 60)).toBe(60)
    expect(shownNumber('', (s) => s / 60)).toBe('')
    expect(shownNumber(NaN)).toBe('')
    expect(shownNumber('12a', (s) => s / 60)).toBe('12a')
  })

  it('stores what is typed: a number through its unit, empty for nothing, the text otherwise', () => {
    expect(typed('15', (m) => m * 60)).toBe(900)
    expect(typed('  ', (m) => m * 60)).toBe('')
    expect(typed('1a', (m) => m * 60)).toBe('1a')
    expect(typed('-5')).toBe('-5')
  })
})
