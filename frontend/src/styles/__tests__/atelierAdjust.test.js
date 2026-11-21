/**
 * The maintainer's deviations from the Atelier mockup (styles/atelier/adjust.css): loaded with
 * the global styles, every selector under :root so it outranks the copied rule it amends
 * whatever the order in which the zones' stylesheets load, and no copied rule among them.
 */
import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'
import { parseRules, splitSelectors, checkCopy } from './atelierCopy'

const ADJUST = path.resolve(__dirname, '../atelier/adjust.css')
const INDEX = path.resolve(__dirname, '../../index.css')

describe('the deviations from the mockup', () => {
  const text = fs.readFileSync(ADJUST, 'utf8')
  const rules = parseRules(text)

  it('are loaded with the global styles', () => {
    expect(fs.readFileSync(INDEX, 'utf8')).toMatch(/@import '\.\/styles\/atelier\/adjust\.css';/)
  })

  it('put every selector under :root', () => {
    expect(rules.length).toBeGreaterThan(0)
    const loose = rules.flatMap((r) => splitSelectors(r.sel)).filter((s) => !s.startsWith(':root '))
    expect(loose).toEqual([])
  })

  it('copy no rule of the mockup (a copy lives with the copies)', () => {
    for (const r of rules) {
      const asCopy = `${r.media ? `${r.media}{` : ''}${splitSelectors(r.sel).map((s) => s.replace(/^:root /, '')).join(',')}{${r.body}}${r.media ? '}' : ''}`
      expect(checkCopy(asCopy), asCopy).not.toEqual([])
    }
  })
})
