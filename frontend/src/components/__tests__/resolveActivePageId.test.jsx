/**
 * Tests for resolveActivePageId — the sidebar/mobile-nav highlight derives
 * the active item from the URL by path matching, not by a "first URL segment
 * === item id" naming convention.
 *
 * Regression: /key-recovery (nav id 'keyRecovery') and /ssh/cas|certificates
 * (nav ids 'ssh-cas'/'ssh-certificates') never highlighted, and scep-config /
 * est-config / tsa-config only worked through a hand-maintained lookup table.
 */
import { describe, it, expect } from 'vitest'
import { resolveActivePageId, navGroups } from '../Sidebar'

describe('resolveActivePageId', () => {
  it('maps / to the dashboard id (empty string)', () => {
    expect(resolveActivePageId('/')).toBe('')
  })

  it('resolves plain pages by exact path', () => {
    expect(resolveActivePageId('/certificates')).toBe('certificates')
    expect(resolveActivePageId('/cas')).toBe('cas')
    expect(resolveActivePageId('/crl-ocsp')).toBe('crl-ocsp')
  })

  it('resolves ids that do not match their URL segment', () => {
    expect(resolveActivePageId('/scep-config')).toBe('scep')
    expect(resolveActivePageId('/est-config')).toBe('est')
    expect(resolveActivePageId('/tsa-config')).toBe('tsa')
    expect(resolveActivePageId('/key-recovery')).toBe('keyRecovery')
  })

  it('resolves nested routes to their own nav item', () => {
    expect(resolveActivePageId('/ssh/cas')).toBe('ssh-cas')
    expect(resolveActivePageId('/ssh/certificates')).toBe('ssh-certificates')
  })

  it('highlights the parent section on detail pages', () => {
    expect(resolveActivePageId('/cas/42')).toBe('cas')
    expect(resolveActivePageId('/certificates/123')).toBe('certificates')
    expect(resolveActivePageId('/truststore/7')).toBe('truststore')
  })

  it('resolves a detail page under a nested nav path to the nested item', () => {
    expect(resolveActivePageId('/ssh/cas/123')).toBe('ssh-cas')
  })

  it('tolerates a trailing slash on a section path', () => {
    expect(resolveActivePageId('/cas/')).toBe('cas')
  })

  it('keeps /dashboard on the first-segment fallback (StatusFooter relies on it)', () => {
    expect(resolveActivePageId('/dashboard')).toBe('dashboard')
  })

  it('falls back to the first URL segment for pages without a nav item', () => {
    expect(resolveActivePageId('/settings')).toBe('settings')
    expect(resolveActivePageId('/account')).toBe('account')
    expect(resolveActivePageId('/user-certificates')).toBe('user-certificates')
  })

  it('every nav item path resolves to that item’s own id', () => {
    // The invariant the old naming convention could not keep: adding a nav
    // entry whose id differs from its URL segment must fail here instead of
    // silently breaking the highlight in the browser.
    for (const group of navGroups) {
      for (const item of group.children) {
        expect(
          resolveActivePageId(item.path),
          `nav item '${item.id}' (path ${item.path}) does not resolve to itself`
        ).toBe(item.id)
      }
    }
  })
})
