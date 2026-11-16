/**
 * A help title is a name, not a quotation: no section title or guide heading
 * (en and every translated language) opens or closes with a quotation mark; quotes in the body stay.
 */
import { describe, it, expect } from 'vitest'
import { helpContent } from '../helpContent'
import { helpGuides } from '../helpGuides'
import { HELP_TRANSLATED_LANGUAGES } from '../helpLanguages'

const pages = import.meta.glob('../help/*/*.js', { eager: true })
const QUOTE = /^["'“”‘’«»「」『』]|["'“”‘’«»「」『』]$/

function titles(node, out = []) {
  if (Array.isArray(node)) node.forEach((n) => titles(n, out))
  else if (node && typeof node === 'object') {
    for (const [key, value] of Object.entries(node)) {
      if (key === 'title' && typeof value === 'string') out.push(value.trim())
      else if (typeof value === 'string') {
        for (const m of value.matchAll(/^#{1,6}\s+(.+)$/gm)) out.push(m[1].trim())
      } else titles(value, out)
    }
  }
  return out
}

const sources = {
  en: [helpContent, helpGuides],
  ...Object.fromEntries(HELP_TRANSLATED_LANGUAGES.map((code) => [code, Object.entries(pages)
    .filter(([path]) => path.includes(`/help/${code}/`)).map(([, mod]) => mod.default)])),
}

describe('help titles carry no surrounding quotation marks', () => {
  it.each(Object.keys(sources))('%s', (code) => {
    const found = titles(sources[code])
    expect(found.length).toBeGreaterThan(50)
    expect(found.filter((t) => QUOTE.test(t))).toEqual([])
  })
})
