/**
 * A `<Badge>` size or variant that Badge does not know adds no class: the badge
 * renders without padding or colour, and nothing complains.
 */
import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'
import { BADGE_SIZES, BADGE_VARIANTS } from '../Badge'

const SRC = path.resolve(__dirname, '../..')

function sourceFiles(dir, acc = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name !== '__tests__' && entry.name !== 'node_modules') sourceFiles(full, acc)
    } else if (/\.jsx$/.test(entry.name)) {
      acc.push(full)
    }
  }
  return acc
}

function unknownLiterals(prop, known) {
  const found = []
  for (const file of sourceFiles(SRC)) {
    const text = fs.readFileSync(file, 'utf8')
    for (const tag of text.matchAll(/<Badge\b[^>]*?>/gs)) {
      const m = tag[0].match(new RegExp(`\\b${prop}="([^"]+)"`))
      if (m && !(m[1] in known)) {
        const line = text.slice(0, tag.index).split('\n').length
        found.push(`${m[1]} at ${path.relative(SRC, file)}:${line}`)
      }
    }
  }
  return found
}

describe('Badge props used in the source', () => {
  it('every literal size is one Badge defines', () => {
    expect(unknownLiterals('size', BADGE_SIZES)).toEqual([])
  })

  it('every literal variant is one Badge defines', () => {
    expect(unknownLiterals('variant', BADGE_VARIANTS)).toEqual([])
  })
})
