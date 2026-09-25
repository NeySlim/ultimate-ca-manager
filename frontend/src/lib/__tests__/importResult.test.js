import { describe, it, expect } from 'vitest'
import { soleImported } from '../importResult'

const result = (ids) => ({ imported_ids: { cas: [], certificates: [], csrs: [], ...ids } })

describe('soleImported', () => {
  it('names the one object an import created', () => {
    expect(soleImported(result({ cas: [4] }))).toEqual({ type: 'ca', id: 4 })
    expect(soleImported(result({ certificates: [7] }))).toEqual({ type: 'certificate', id: 7 })
    expect(soleImported(result({ csrs: [9] }))).toEqual({ type: 'csr', id: 9 })
  })

  it('names none when several were created, across types or not', () => {
    expect(soleImported(result({ cas: [1], certificates: [2] }))).toBeNull()
    expect(soleImported(result({ certificates: [2, 3] }))).toBeNull()
  })

  it('names none when nothing was created', () => {
    expect(soleImported(result({}))).toBeNull()
    expect(soleImported({ keys_matched: 1 })).toBeNull()
    expect(soleImported(undefined)).toBeNull()
  })
})
