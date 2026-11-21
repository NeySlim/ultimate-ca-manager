/**
 * The index of the whole guide for its search: every section of every chapter in plain text,
 * in the reading language with the English help where a chapter has no translation.
 */
import { loadEnglishHelp, loadTranslatedPages } from '../../data/helpData'
import { GUIDE_CHAPTERS } from '../../navigation/guide'
import { mergeHelpContent } from './content'
import { chapterSections, indexEntries, quickSections } from './search'

const indexes = {}

/** The index of every chapter in a help language (null: English), built once per language. */
export function loadGuideIndex(lang) {
  const at = lang || 'en'
  indexes[at] ||= Promise.all([loadEnglishHelp(), loadTranslatedPages(lang, GUIDE_CHAPTERS.map((c) => c.key))]).then(([english, pages]) => (
    GUIDE_CHAPTERS.flatMap((c) => {
      const page = pages[c.key]
      if (c.key === 'navigation') {
        const quick = mergeHelpContent(english.helpContent.navigation, page?.helpContent)
        return indexEntries(c.key, quick.title, quickSections(quick))
      }
      const en = english.helpGuides[c.key]
      if (!en) return []
      const title = page?.helpGuides?.title || en.title
      return indexEntries(c.key, title, chapterSections(c.key, title, page?.helpGuides?.content || en.content, en.content))
    })
  )).catch((e) => { delete indexes[at]; throw e })
  return indexes[at]
}
