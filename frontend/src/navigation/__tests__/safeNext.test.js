/** Parcours 18: the return target after sign-in is an internal known page or nothing. */
import { describe, it, expect } from 'vitest'
import { safeNext, loginUrl } from '../safeNext'

describe('safeNext', () => {
  it.each([
    '//evil.example', '//evil.example/certificates', '/\\evil.example', 'https://evil.example/',
    'javascript:alert(1)', '/unknown-page', '/certificates/../../etc', '/%2F%2Fevil', '/certificates%0d%0a',
    '/login', '/login?next=/certificates', 'certificates', '', null, undefined, 42, '/ certificates',
    '/certificates\nSet-Cookie:x', '/' + 'a'.repeat(600),
  ])('refuses %j', (value) => {
    expect(safeNext(value)).toBeNull()
  })

  it.each(['/certificates', '/dashboard', '/acme?tab=orders&order=4', '/certificates?x=1#top', '/groups'])('keeps %s', (v) => {
    expect(safeNext(v)).toBe(v)
  })
})

describe('loginUrl', () => {
  it('carries a known page and leaves the landing page out', () => {
    expect(loginUrl('/certificates', '?status=expiring')).toBe('/login?next=%2Fcertificates%3Fstatus%3Dexpiring')
    expect(loginUrl('/', '')).toBe('/login')
    expect(loginUrl('/dashboard', '')).toBe('/login')
    expect(loginUrl('/nowhere', '')).toBe('/login')
  })
})
