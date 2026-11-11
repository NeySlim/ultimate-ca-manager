import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, it, expect } from 'vitest'

// Selectors whose only user was the removed pre-Atelier dashboard must not linger.
const css = readFileSync(resolve(__dirname, '../../index.css'), 'utf8')

describe('orphan selectors', () => {
  it.each(['hero-gradient', 'stat-card-danger', 'stat-card-enhanced', 'animate-pulse-soft'])(
    '.%s is gone', (name) => {
      expect(css).not.toContain(`.${name}`)
    })
  it('pulse-soft keyframes are gone', () => {
    expect(css).not.toMatch(/@keyframes pulse-soft\b/)
  })
})
