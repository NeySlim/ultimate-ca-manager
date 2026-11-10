/**
 * Text drawn on an accent fill uses `text-on-accent` (var(--on-accent)), the colour the
 * contrast matrix checks; `text-white` on `bg-accent-primary` drops below 2:1 on dark palettes.
 */
import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'
import tailwindConfig from '../../../tailwind.config.js'

const SRC = path.resolve(__dirname, '../..')

function sourceFiles(dir, acc = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name !== '__tests__' && entry.name !== 'node_modules') sourceFiles(full, acc)
    } else if (/\.(jsx?|tsx?)$/.test(entry.name)) acc.push(full)
  }
  return acc
}

// Class strings where one variant (none, `file:`, `hover:` ...) pairs the accent fill with white text.
function whiteOnAccent(text) {
  const hits = []
  for (const m of text.matchAll(/'[^'\n]*'|"[^"\n]*"|`[^`]*`/g)) {
    const byVariant = new Map()
    for (const cls of m[0].slice(1, -1).split(/\s+/)) {
      const c = cls.replace(/^['"`]+|['"`]+$/g, '')
      const i = c.lastIndexOf(':')
      const variant = i < 0 ? '' : c.slice(0, i + 1)
      const base = c.slice(i + 1)
      if (!byVariant.has(variant)) byVariant.set(variant, new Set())
      byVariant.get(variant).add(base)
    }
    for (const [variant, set] of byVariant) {
      if (set.has('bg-accent-primary') && set.has('text-white')) {
        const line = text.slice(0, m.index).split('\n').length
        hits.push(`${line}${variant ? ` (${variant})` : ''}`)
      }
    }
  }
  return hits
}

describe('text on accent fills', () => {
  it('exposes text-on-accent to Tailwind as var(--on-accent)', () => {
    expect(tailwindConfig.theme.extend.colors['on-accent']).toBe('var(--on-accent)')
  })

  it('detects white text on the accent fill', () => {
    expect(whiteOnAccent(`x ? 'bg-accent-primary text-white' : 'y'`)).toHaveLength(1)
    expect(whiteOnAccent(`"file:bg-accent-primary file:text-white"`)).toHaveLength(1)
    expect(whiteOnAccent(`'bg-accent-primary text-on-accent'`)).toHaveLength(0)
  })

  it('no component puts text-white on bg-accent-primary', () => {
    const offenders = []
    for (const file of sourceFiles(SRC)) {
      for (const hit of whiteOnAccent(fs.readFileSync(file, 'utf8'))) {
        offenders.push(`${path.relative(SRC, file)}:${hit}`)
      }
    }
    expect(offenders).toEqual([])
  })
})
