import { describe, it, expect, vi, afterEach } from 'vitest'
import { strongPassword } from '../../e2e/support/password'

// The runs the server's password policy refuses (four in a row, either direction).
const SEQUENCES = ['abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', '0123456789', 'qwertyuiop', 'asdfghjkl', 'zxcvbnm']

function refusedRun(password) {
  for (let i = 0; i + 4 <= password.length; i++) {
    const run = password.slice(i, i + 4)
    if (new Set(run).size === 1) return run
    const back = [...run].reverse().join('')
    if (SEQUENCES.some(s => s.includes(run) || s.includes(back))) return run
  }
  return null
}

describe('the password the browser tests give their users', () => {
  afterEach(() => vi.restoreAllMocks())

  it.each([
    ['repeated dice', '0.aaaaaaaaaaaa', 'lz4k9x2p'],
    ['sequential dice', '0.3456789abcde', 'lz4k9x2p'],
    ['sequential clock', '0.k2j8x1m4q7w3', 'abcdefgh'],
    ['repeated clock', '0.k2j8x1m4q7w3', 'mzzzzzz0'],
    ['empty dice', '0', 'qwertyui'],
  ])('passes the policy with %s', (_name, dice, clock) => {
    vi.spyOn(Math, 'random').mockReturnValue({ toString: () => dice })
    vi.spyOn(Date, 'now').mockReturnValue(parseInt(clock, 36))
    const password = strongPassword()
    expect(refusedRun(password)).toBeNull()
    expect(password).toMatch(/[a-z]/)
    expect(password).toMatch(/[A-Z]/)
    expect(password).toMatch(/[0-9]/)
    expect(password).toMatch(/!/)
    expect(password.length).toBeGreaterThanOrEqual(12)
  })
})
