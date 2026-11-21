/**
 * The `-opNN` utilities are hand-written in `src/index.css`; Tailwind does not
 * generate them. A typo, or a variant nobody declared, yields a class name that
 * produces no CSS at all — the tint, border or hover feedback silently does not
 * render, and nothing in the build complains.
 *
 * This test derives the used classes from the source and fails when one has no
 * matching rule. It is the lint the audit asked for (DUP-FE-019).
 */
import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'

const SRC = path.resolve(__dirname, '../..')

/** Every `.foo-opNN` / `.hover\:foo-opNN` selector declared in index.css. */
function declaredClasses() {
  const css = fs.readFileSync(path.join(SRC, 'index.css'), 'utf8')
  const found = new Set()
  for (const m of css.matchAll(/\.((?:[a-zA-Z0-9_-]+\\:)*[a-zA-Z0-9_-]*-op[0-9]+)/g)) {
    found.add(m[1].replace(/\\/g, ''))
  }
  return found
}

function sourceFiles(dir, acc = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name === '__tests__' || entry.name === 'node_modules') continue
      sourceFiles(full, acc)
    } else if (/\.jsx?$/.test(entry.name)) {
      acc.push(full)
    }
  }
  return acc
}

/** Class tokens ending in `-opNN`, keeping any `hover:` / `enabled:hover:` prefix. */
function usedClasses() {
  const used = new Map()
  for (const file of sourceFiles(SRC)) {
    fs.readFileSync(file, 'utf8').split('\n').forEach((line, i) => {
      for (const m of line.matchAll(/(?<![a-zA-Z0-9_\-:[])((?:[a-z][a-z0-9-]*:)*[a-zA-Z0-9_-]*-op[0-9]+)/g)) {
        if (!used.has(m[1])) used.set(m[1], [])
        used.get(m[1]).push(`${path.relative(SRC, file)}:${i + 1}`)
      }
    })
  }
  return used
}

describe('opacity utilities (-opNN)', () => {
  it('every -opNN class used in the source is declared in index.css', () => {
    const declared = declaredClasses()
    const used = usedClasses()

    const undeclared = [...used.keys()]
      .filter((cls) => !declared.has(cls))
      .map((cls) => `${cls} — used at ${used.get(cls).join(', ')}`)

    expect(
      undeclared,
      `These classes produce no CSS; the style they promise never renders:\n  ${undeclared.join('\n  ')}`
    ).toEqual([])
  })

  it('finds a non-trivial number of classes, so the scan itself cannot silently pass', () => {
    // Guards against a regex or path change turning the test above into a no-op. The count falls as
    // pages move to the mockup's rules, so the floor only asks that the scan still finds some.
    expect(declaredClasses().size).toBeGreaterThan(20)
    expect(usedClasses().size).toBeGreaterThan(20)
  })
})
