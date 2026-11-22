import { mergeHelpContent } from './content'

/**
 * A guide chapter's text in the reading language: { title, subtitle, quick, lang } or { title, markdown, english, lang };
 * lang is the language of the text shown, `en` where the translation has none.
 */
export function chapterText(key, english, page, lang) {
  if (!english) return null
  if (key === 'navigation') {
    const quick = english.helpContent.navigation && mergeHelpContent(english.helpContent.navigation, page?.helpContent)
    return quick && { title: quick.title, subtitle: quick.subtitle, quick, lang: lang && page?.helpContent ? lang : 'en' }
  }
  const en = english.helpGuides[key]
  if (!en) return null
  const tr = page?.helpGuides
  return { title: tr?.title || en.title, markdown: tr?.content || en.content, english: en.content, lang: lang && tr?.content ? lang : 'en' }
}
