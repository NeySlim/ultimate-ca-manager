/** The bar's room plan: stylesheet padding when it fits, then tighter padding, then pinned labels, then the pins fold. */
import { describe, it, expect } from 'vitest'
import { planNavRoom, FLOOR } from '../useNavRoom'

const link = (content, mock = 12) => ({ content, mock, pinned: false, label: 0 })
const pin = (content, label, mock = 12) => ({ content, mock, pinned: true, label })
// Five fixed links of 100 px of content, 5 px apart: 520 px, 640 with 12 px each side
const fixed = () => Array.from({ length: 5 }, () => link(100))

describe('planNavRoom', () => {
  it('keeps the stylesheet padding when everything fits', () => {
    expect(planNavRoom({ room: 640, gap: 5, links: fixed() })).toEqual({ pad: null, fold: false })
  })

  it('tightens the padding by as much as the room lacks, never past the stylesheet value', () => {
    expect(planNavRoom({ room: 600, gap: 5, links: fixed() })).toEqual({ pad: 8, fold: false })
    expect(planNavRoom({ room: 630, gap: 5, links: [...fixed().slice(0, 4), link(100, 9)] })).toEqual({ pad: 9, fold: false })
  })

  it('stops the padding at the floor and lets the pinned labels give way', () => {
    // 5 fixed + one pin of 16 px icon, 8 px gap and 150 px label: content 520 + 5 + 174 = 699
    const links = [...fixed(), pin(174, 150)]
    expect(planNavRoom({ room: 699 + 12 * FLOOR - 100, gap: 5, links })).toEqual({ pad: FLOOR, fold: false })
  })

  it('folds the pinned links away when even their icons do not fit, the rest planned alone', () => {
    const links = [...fixed(), pin(40, 0), pin(40, 0), pin(40, 0)]
    expect(planNavRoom({ room: 620, gap: 5, links })).toEqual({ pad: 10, fold: true })
    expect(planNavRoom({ room: 700, gap: 5, links: fixed() })).toEqual({ pad: null, fold: false })
  })

  it('never tightens past the floor: three icon-only pins that would need 3 px fold away instead', () => {
    // 5 x 100 + 3 x 16 + 7 gaps of 5 = 583 px of content, 48 px left for 16 sides
    const links = [...fixed(), pin(16, 0), pin(16, 0), pin(16, 0)]
    expect(planNavRoom({ room: 631, gap: 5, links })).toEqual({ pad: 11.1, fold: true })
  })

  it('keeps the floor when nothing can fold', () => {
    expect(planNavRoom({ room: 400, gap: 5, links: fixed() })).toEqual({ pad: FLOOR, fold: false })
  })
})
