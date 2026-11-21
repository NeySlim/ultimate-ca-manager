/** The guide's chapters: every guide and the navigation help once, grouped as the registry, each with its page. */
import { describe, it, expect } from 'vitest'
import { helpGuides } from '../../data/helpGuides'
import { helpContent } from '../../data/helpContent'
import { GUIDE_CHAPTERS, RETIRED_CHAPTERS, chapterOfAnchor, guideGroups, guideHref, openPagePath, guideChapter } from '../guide'
import { isKnownPath } from '../registry'

const nobody = { isAdmin: () => false, hasPermission: () => false }
const admin = { isAdmin: () => true, hasPermission: () => true }
const only = (...perms) => ({ isAdmin: () => false, hasPermission: (p) => perms.includes(p) })

describe('guide chapters', () => {
  it('lists every guide but the retired ones, and the navigation help, once each', () => {
    const keys = GUIDE_CHAPTERS.map((c) => c.key)
    expect(new Set(keys).size).toBe(keys.length)
    const expected = [...Object.keys(helpGuides).filter((k) => !RETIRED_CHAPTERS.includes(k)), 'navigation']
    expect([...keys].sort()).toEqual(expected.sort())
    expect(keys).not.toContain('importExport')
    expect(helpContent.navigation).toBeTruthy()
  })

  it('puts the console as a whole first, then the registry groups in their order', () => {
    const groups = guideGroups()
    expect(groups.map((g) => g.id)).toEqual(['general', 'pki', 'protocols', 'governance', 'admin'])
    expect(groups[0].labelKey).toBe('guide.general')
    expect(groups[0].chapters.map((c) => c.key)).toEqual(['navigation', 'dashboard', 'account', 'security'])
    expect(groups[1].chapters.map((c) => c.key).slice(0, 2)).toEqual(['certificates', 'cas'])
    const admin = groups.find((g) => g.id === 'admin').chapters.map((c) => c.key)
    expect(admin.slice(admin.indexOf('settings'), admin.indexOf('settings') + 3)).toEqual(['settings', 'sso', 'msca'])
    expect(admin).toContain('systemLogs')
    for (const c of GUIDE_CHAPTERS) expect(c.labelKey, c.key).toBeTruthy()
  })

  it('links a chapter to its page only for an account that may open it', () => {
    expect(openPagePath(guideChapter('acme'), only('read:acme'))).toBe('/acme')
    expect(openPagePath(guideChapter('acme'), nobody)).toBeNull()
    expect(openPagePath(guideChapter('certificates'), nobody)).toBe('/certificates')
    expect(openPagePath(guideChapter('sshCas'), only('read:ssh_cas'))).toBe('/ssh/cas')
    expect(openPagePath(guideChapter('systemLogs'), admin)).toBe('/logs')
    expect(openPagePath(guideChapter('security'), admin)).toBe('/settings?tab=security')
    expect(openPagePath(guideChapter('msca'), admin)).toBe('/settings?tab=microsoftCA')
    expect(openPagePath(guideChapter('sso'), only('read:settings'))).toBeNull()
    expect(openPagePath(guideChapter('navigation'), admin)).toBeNull()
  })

  it('finds the chapter of a heading id, the longest key first', () => {
    expect(chapterOfAnchor('user-certificates-overview').key).toBe('user-certificates')
    expect(chapterOfAnchor('cas-overview').key).toBe('cas')
    expect(chapterOfAnchor('nowhere-at-all')).toBeNull()
    expect(chapterOfAnchor('')).toBeNull()
  })

  it('gives the guide\'s address of a help key, and its section', () => {
    expect(guideHref('acme')).toBe('/guide/acme')
    expect(guideHref('cas', 'cas-overview')).toBe('/guide/cas#cas-overview')
    expect(guideHref('importExport')).toBe('/guide')
    expect(guideHref(undefined)).toBe('/guide')
  })

  it('is a page a sign-in may come back to', () => {
    expect(isKnownPath('/guide')).toBe(true)
    expect(isKnownPath('/guide/cas')).toBe(true)
    expect(isKnownPath('/guide/cas/more')).toBe(false)
  })
})
