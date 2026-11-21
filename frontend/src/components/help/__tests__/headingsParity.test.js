/**
 * A heading's id is the English one at the same position: each translated guide must have the
 * English headings, same count and same levels, for a shared link to land in every language.
 */
import { describe, it, expect } from 'vitest'
import { helpGuides } from '../../../data/helpGuides'
import { HELP_TRANSLATED_LANGUAGES } from '../../../data/helpLanguages'
import { guideHeadings } from '../markdown'

const files = import.meta.glob('../../../data/help/*/*.js', { eager: true })
const translated = (lang, key) => files[`../../../data/help/${lang}/${key}.js`]?.default?.helpGuides?.content

const cases = HELP_TRANSLATED_LANGUAGES.flatMap((lang) => Object.keys(helpGuides).map((key) => [lang, key]))

describe('guide headings per language', () => {
  it('has English headings with unique ids in every chapter', () => {
    for (const [key, guide] of Object.entries(helpGuides)) {
      const ids = guideHeadings(key, guide.content).map((h) => h.id)
      expect(ids.length, key).toBeGreaterThan(0)
      expect(new Set(ids).size, key).toBe(ids.length)
    }
  })

  it.each(cases)('%s/%s has the English headings, same count and levels', (lang, key) => {
    const tr = translated(lang, key)
    expect(tr, `${lang}/${key} has no guide`).toBeTruthy()
    const levels = (md) => guideHeadings(key, md).map((h) => h.level)
    expect(levels(tr)).toEqual(levels(helpGuides[key].content))
  })
})
