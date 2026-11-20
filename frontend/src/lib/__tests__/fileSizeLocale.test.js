import { describe, it, expect } from 'vitest'
import { formatBytes, formatPercent, serverUtcToIso } from '../fileSize'

describe('formatBytes', () => {
  it('writes the size in the reader units', () => {
    expect(formatBytes(2.5 * 1024 * 1024, 'en')).toBe('2.5 MB')
    expect(formatBytes(2.5 * 1024 * 1024, 'fr')).toBe('2,5\u00a0Mo')
    expect(formatPercent(55.8, 'fr')).toBe('55,8\u00a0%')
    expect(formatPercent(55.8, 'en')).toBe('55.8%')
    expect(formatBytes(1536, 'en')).toBe('2 kB')
    expect(formatBytes(0, 'en')).toBe('0 byte')
  })
})

describe('serverUtcToIso', () => {
  it('reads the server UTC stamp as an instant', () => {
    expect(serverUtcToIso('2026-11-20 10:05:00 UTC')).toBe('2026-11-20T10:05:00Z')
    expect(new Date(serverUtcToIso('2026-11-20 10:05:00 UTC')).getTime()).toBe(Date.UTC(2026, 10, 20, 10, 5))
    expect(serverUtcToIso('nope')).toBe('nope')
  })
})
