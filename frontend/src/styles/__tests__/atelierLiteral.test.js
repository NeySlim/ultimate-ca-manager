/**
 * Literal copy of the Atelier mockup. styles/atelier/maquette.css is the mockup's whole style.css;
 * the only changes allowed are mechanical (each selector under .atl, a theme root written the
 * product's way, the font file at the product's path). Every rule, blanks aside, is the mockup's,
 * in its order, none more and none less; the mockup's rules on its document are carried by
 * tokens.css (variables) and scope.css (what they pass down). The icons are its paths, verbatim.
 * The fixtures are the approved mockup files (sha256 of its manifest).
 */
import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'
import crypto from 'crypto'
import {
  FIXTURES, ASSETS, mockup, copiedRules, documentRules, parseRules, splitSelectors, checkCopy, checkWhole,
  declarations, cascade, sameValue, THEMES, INHERITED, DOCUMENT_ONLY,
} from './atelierCopy'

const sha256 = (file) => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')
const COPIES = path.resolve(__dirname, '../atelier')
const ICONS = path.resolve(__dirname, '../../components/atelier/icons.js')
const PUBLIC = path.resolve(__dirname, '../../../public')
const MOCKUP_SHA256 = {
  'style.css': '176c01929728433d0ed1e8d0c445c0b20870091c6c9ee148f6335dcc26358d92',
  'icons.js': 'aa622666fa1d339a56f9fb19473a9e8a910dfe3f6678ce09fc7b7350cd90180f',
}
// Not copies: the scope rules, the maintainer's deviations, what the product adds
const NOT_COPIES = new Set(['scope.css', 'adjust.css', 'extensions.css'])
// Variables the mockup's markup sets in a style attribute (app.js), not its stylesheet
const MARKUP_VARS = ['--chain-cols', '--weeks']
// The document's own decoration in Aurore; the product's shell draws its own (components/shell)
const DECORATION = [':root[data-theme|=aurore] body::before', ':root[data-theme=aurore-light] body::before']

const read = (file) => fs.readFileSync(file, 'utf8')
const copies = fs.readdirSync(COPIES).filter((f) => f.endsWith('.css') && !NOT_COPIES.has(f))
const MAQUETTE = read(path.join(COPIES, 'maquette.css'))
const tokens = parseRules(read(path.resolve(__dirname, '../tokens.css')))
const scope = parseRules(read(path.join(COPIES, 'scope.css')))

describe('the Atelier mockup, copied literally', () => {
  it('reads the approved mockup files', () => {
    for (const [file, sum] of Object.entries(MOCKUP_SHA256)) expect(sha256(path.join(FIXTURES, file)), file).toBe(sum)
    expect(mockup.length).toBeGreaterThan(1000)
  })

  it('has one copy only, the whole stylesheet', () => {
    expect(copies).toEqual(['maquette.css'])
  })

  it('maquette.css: every rule of the mockup, under .atl, in its order, none more, none less', () => {
    expect(parseRules(MAQUETTE)).toHaveLength(copiedRules.length)
    expect(checkWhole(MAQUETTE)).toEqual([])
    expect(checkCopy(MAQUETTE)).toEqual([])
  })

  it('catches a changed value, a rule removed, a rule added, a rule moved, a rule out of scope', () => {
    const rule = '.atl .audit-summary{display:flex;align-items:center;gap:20px;font-size:12px;color:var(--muted);margin-bottom:17px}'
    expect(MAQUETTE).toContain(rule)
    const changed = checkWhole(MAQUETTE.replace(rule, rule.replace('gap:20px', 'gap:21px')))
    expect(changed).toHaveLength(2)
    expect(changed.join('\n')).toMatch(/not in the mockup.*gap:21px[\s\S]*missing from the copy.*gap:20px/)
    expect(checkWhole(MAQUETTE.replace(rule, ''))).toEqual([expect.stringMatching(/^missing from the copy: \.audit-summary\{/)])
    expect(checkWhole(`${MAQUETTE}\n.atl .audit-summary{display:none}`)).toEqual([expect.stringMatching(/^not in the mockup.*display:none/)])
    expect(checkWhole(`${rule}\n${MAQUETTE.replace(rule, '')}`)).toHaveLength(2)
    expect(checkWhole(MAQUETTE.replace(rule, rule.replace('.atl ', '')))[0]).toMatch(/^not under \.atl: \.audit-summary/)
    expect(checkWhole(MAQUETTE.replace('.atl *{box-sizing:border-box}', '*{box-sizing:border-box}'))[0]).toMatch(/^not under \.atl: \*/)
    // the mechanical changes, undone, are refused: a mockup theme root, the mockup's font path
    const root = ':root[data-theme="atelier"][data-mode="light"] .atl .btn.primary{color:#fff}'
    expect(MAQUETTE).toContain(root)
    expect(checkWhole(MAQUETTE.replace(root, ':root[data-theme=light] .atl .btn.primary{color:#fff}'))[0]).toMatch(/^not under \.atl/)
    const [[mockAsset, productAsset]] = ASSETS
    expect(MAQUETTE).toContain(productAsset)
    expect(checkWhole(MAQUETTE.replace(productAsset, "url('/assets/"))).toHaveLength(2)
    expect(mockAsset).not.toBe(productAsset)
  })

  it('still checks a partial copy rule by rule (changed value, out of scope, out of order, theme root)', () => {
    expect(checkCopy('.atl .audit-summary{display:flex;align-items:center;gap:20px;font-size:12px;color:var(--muted);margin-bottom:17px}')).toEqual([])
    expect(checkCopy('.atl .audit-summary{display:flex;align-items:center;gap:21px;font-size:12px;color:var(--muted);margin-bottom:17px}')).toHaveLength(1)
    expect(checkCopy('.audit-summary{display:flex;align-items:center;gap:20px;font-size:12px;color:var(--muted);margin-bottom:17px}')).toHaveLength(1)
    expect(checkCopy('.atl .audit-type{display:flex;align-items:center;gap:10px}\n.atl .audit-summary{display:flex;align-items:center;gap:20px;font-size:12px;color:var(--muted);margin-bottom:17px}')).toHaveLength(1)
    expect(checkCopy(':root[data-theme="atelier"][data-mode="light"] .atl .btn.primary{color:#fff}')).toEqual([])
    expect(checkCopy(':where(:root[data-theme|=aurore]) .atl :focus-visible{outline:2px solid var(--accent);box-shadow:0 0 0 5px rgba(107,120,224,.25)}')).toEqual([])
    expect(checkCopy(':root[data-theme=light] .atl .btn.primary{color:#fff}')).toHaveLength(1)
  })

  it('serves the mockup\'s font file at the product\'s path', () => {
    const face = copiedRules.find((r) => r.sel === '@font-face')
    const file = face.body.match(/url\('\.\.\/assets\/([^']+)'\)/)[1]
    expect(fs.existsSync(path.join(PUBLIC, 'fonts', file)), file).toBe(true)
  })

  it('leaves out only the rules on the mockup\'s document, each property accounted for', () => {
    expect(documentRules.length + copiedRules.length).toBe(mockup.length)
    expect(documentRules.flatMap((r) => splitSelectors(r.sel)).filter((s) => s.includes('::'))).toEqual(DECORATION)
    for (const r of documentRules.filter((x) => !x.sel.includes('::'))) {
      for (const [prop] of declarations(r.body)) {
        const known = prop.startsWith('--') || INHERITED.has(prop) || DOCUMENT_ONLY.has(prop)
        expect(known, `${r.sel}{${prop}} is neither a variable, inherited, nor the document's`).toBe(true)
      }
    }
  })

  for (const theme of Object.keys(THEMES)) {
    const { mock, product } = THEMES[theme]
    const atRoot = cascade(documentRules, mock)
    const atBody = { ...atRoot, ...cascade(documentRules, ['', ...mock.map((r) => `${r} `)], 'body') }
    const inProduct = cascade(tokens, product)

    it(`${theme}: every variable of the mockup's root is in tokens.css with the same value`, () => {
      const vars = Object.entries(atRoot).filter(([k]) => k.startsWith('--'))
      expect(vars.length).toBeGreaterThan(15)
      for (const [k, v] of vars) expect(sameValue(inProduct[k] ?? 'missing'), `${theme} ${k}`).toBe(sameValue(v))
    })

    it(`${theme}: what the mockup's document passes down reaches .atl unchanged`, () => {
      const zone = { ...inProduct, ...cascade(scope, ['', ...product.map((r) => `${r} `)], '.atl') }
      const inherited = Object.entries(atBody).filter(([k]) => INHERITED.has(k))
      expect(inherited.map(([k]) => k).sort()).toEqual([...INHERITED].sort())
      for (const [k, v] of inherited) expect(sameValue(zone[k] ?? 'missing'), `${theme} ${k}`).toBe(sameValue(v))
    })
  }

  it('gives back the hidden attribute under the revert, at its weight and after it', () => {
    // all:revert drops the browser's [hidden] (a presentational hint in Chromium): a hidden panel would show
    const revert = scope.findIndex((r) => /all:revert/.test(r.body))
    const hidden = scope.findIndex((r) => r.sel === '.atl :where([hidden]:not([hidden=until-found]))' && /^display:none;?$/.test(r.body.trim()) && !r.media)
    expect(revert).toBeGreaterThanOrEqual(0)
    expect(hidden).toBeGreaterThan(revert)
  })

  it('keeps what the product adds under the zone scope', () => {
    const added = parseRules(read(path.join(COPIES, 'extensions.css')))
    expect(added.length).toBeGreaterThan(0)
    // The rules on the scope itself: a dialog drawn outside a zone carries `.atl` without a box;
    // the sign-in pages' zone fills the window and scrolls itself, as the guide's page does
    const onScope = new Set(['.atl.atl-island', '.atl.atl-auth', '.atl.guide-app'])
    for (const r of added) for (const sel of r.sel.split(',')) expect(sel.trim().startsWith('.atl ') || onScope.has(sel.trim()), sel).toBe(true)
  })

  it('takes every descendant but icons back to the browser, with no panel left to the product', () => {
    const revert = scope.find((r) => /all:\s*revert/.test(r.body))
    // the element, its ::before and its ::after; an icon keeps its presentation attributes
    expect(splitSelectors(revert.sel)).toEqual(['', '::before', '::after'].map((pseudo) => `.atl :where(:not(svg,svg *))${pseudo}`))
  })

  it('uses no variable that neither tokens.css nor the copy nor the markup sets', () => {
    const used = new Set([...read(path.join(FIXTURES, 'style.css')).matchAll(/var\((--[\w-]+)/g)].map((m) => m[1]))
    const onRoot = new Set(documentRules.flatMap((r) => declarations(r.body).map(([k]) => k)).filter((k) => k.startsWith('--')))
    const local = new Set(copiedRules.flatMap((r) => declarations(r.body).map(([k]) => k)).filter((k) => k.startsWith('--')))
    expect([...used].filter((v) => !onRoot.has(v) && !local.has(v)).sort()).toEqual(MARKUP_VARS)
  })

  it('draws the mockup\'s icons with its paths, verbatim', () => {
    const block = (src, head) => {
      const start = src.indexOf(head)
      return src.slice(src.indexOf('{', start), src.indexOf('};', start) + 1)
    }
    const theirs = block(read(path.join(FIXTURES, 'icons.js')), 'const paths = {')
    const ours = block(read(ICONS), 'export const PATHS = {')
    expect(ours).toBe(theirs)
  })
})
