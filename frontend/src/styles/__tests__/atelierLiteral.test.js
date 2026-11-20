/**
 * Literal copy of the Atelier mockup. The zones redrawn from the mockup copy its style.css rules
 * into styles/atelier/<zone>.css; the only change allowed is mechanical (each selector under .atl,
 * a theme root written the product's way). Every copied rule must be, blanks aside, the mockup's
 * rule with the same media and selector, in the mockup's order. The icons are its paths, verbatim.
 * The fixtures are the approved mockup files (sha256 of its manifest).
 */
import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'
import crypto from 'crypto'
import { FIXTURES, mockup, parseRules, checkCopy } from './atelierCopy'

const sha256 = (file) => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')
const COPIES = path.resolve(__dirname, '../atelier')
const ICONS = path.resolve(__dirname, '../../components/atelier/icons.js')
const MOCKUP_SHA256 = {
  'style.css': '176c01929728433d0ed1e8d0c445c0b20870091c6c9ee148f6335dcc26358d92',
  'icons.js': 'aa622666fa1d339a56f9fb19473a9e8a910dfe3f6678ce09fc7b7350cd90180f',
}
// Not copies: the scope rules themselves
const NOT_COPIES = new Set(['scope.css'])

const copies = fs.readdirSync(COPIES).filter((f) => f.endsWith('.css') && !NOT_COPIES.has(f))

describe('the Atelier mockup, copied literally', () => {
  it('reads the approved mockup files', () => {
    for (const [file, sum] of Object.entries(MOCKUP_SHA256)) expect(sha256(path.join(FIXTURES, file)), file).toBe(sum)
    expect(mockup.length).toBeGreaterThan(1000)
  })

  it('has copied zones to check', () => {
    expect(copies).toContain('activity.css')
  })

  for (const file of copies) {
    it(`${file}: every rule is the mockup's, under .atl, in the mockup's order`, () => {
      const text = fs.readFileSync(path.join(COPIES, file), 'utf8')
      expect(parseRules(text).length).toBeGreaterThan(0)
      expect(checkCopy(text)).toEqual([])
    })
  }

  it('catches a changed value, a rule out of scope and a rule out of order', () => {
    expect(checkCopy('.atl .audit-summary{display:flex;align-items:center;gap:20px;font-size:12px;color:var(--muted);margin-bottom:17px}')).toEqual([])
    expect(checkCopy('.atl .audit-summary{display:flex;align-items:center;gap:21px;font-size:12px;color:var(--muted);margin-bottom:17px}')).toHaveLength(1)
    expect(checkCopy('.audit-summary{display:flex;align-items:center;gap:20px;font-size:12px;color:var(--muted);margin-bottom:17px}')).toHaveLength(1)
    expect(checkCopy('.atl .audit-type{display:flex;align-items:center;gap:10px}\n.atl .audit-summary{display:flex;align-items:center;gap:20px;font-size:12px;color:var(--muted);margin-bottom:17px}')).toHaveLength(1)
    expect(checkCopy(':root[data-theme="atelier"][data-mode="light"] .atl .btn.primary{color:#fff}')).toEqual([])
    expect(checkCopy(':where(:root[data-theme|=aurore]) .atl :focus-visible{outline:2px solid var(--accent);box-shadow:0 0 0 5px rgba(107,120,224,.25)}')).toEqual([])
    expect(checkCopy(':root[data-theme=light] .atl .btn.primary{color:#fff}')).toHaveLength(1)
  })

  it('draws the mockup\'s icons with its paths, verbatim', () => {
    const block = (src, head) => {
      const start = src.indexOf(head)
      return src.slice(src.indexOf('{', start), src.indexOf('};', start) + 1)
    }
    const theirs = block(fs.readFileSync(path.join(FIXTURES, 'icons.js'), 'utf8'), 'const paths = {')
    const ours = block(fs.readFileSync(ICONS, 'utf8'), 'export const PATHS = {')
    expect(ours).toBe(theirs)
  })
})
