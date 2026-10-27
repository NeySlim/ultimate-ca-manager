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

// The opening tag ends at the first `>` outside braces: `v > 0` or an arrow
// function inside a prop must not end it.
function openingTags(text) {
  const tags = []
  for (const m of text.matchAll(/<Badge\b/g)) {
    let depth = 0
    for (let i = m.index; i < text.length; i++) {
      const c = text[i]
      if (c === '{') depth++
      else if (c === '}') depth--
      else if (c === '>' && depth === 0) {
        tags.push({ tag: text.slice(m.index, i + 1), index: m.index })
        break
      }
    }
  }
  return tags
}

function unknownLiterals(prop, known) {
  const literal = new RegExp(`\\b${prop}=(?:\\{\\s*)?(["'])([^"']+)\\1`)
  const found = []
  for (const file of sourceFiles(SRC)) {
    const text = fs.readFileSync(file, 'utf8')
    for (const { tag, index } of openingTags(text)) {
      const m = tag.match(literal)
      if (m && !(m[2] in known)) {
        const line = text.slice(0, index).split('\n').length
        found.push(`${m[2]} at ${path.relative(SRC, file)}:${line}`)
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
