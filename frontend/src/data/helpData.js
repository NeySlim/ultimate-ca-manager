/**
 * The help's text, loaded on demand so the console's main chunk does not carry it: the English
 * quick help and guides (helpContent.js, helpGuides.js) as one chunk, and each translated page as
 * its own (helpLoader.js). Each load is made once and kept.
 */
import { useEffect, useState } from 'react'
import { HELP_TRANSLATED_LANGUAGES } from './helpLanguages'
import { loadHelpPage } from './helpLoader'

let english = null
let englishLoad = null

/** The English help once loaded ({ helpContent, helpGuides }), else null. */
export const englishHelp = () => english

/** Loads the English help; a failed load is tried again on the next call. */
export function loadEnglishHelp() {
  if (english) return Promise.resolve(english)
  englishLoad ||= Promise.all([import('./helpContent'), import('./helpGuides')])
    .then(([c, g]) => (english = { helpContent: c.helpContent, helpGuides: g.helpGuides }))
    .catch((e) => { englishLoad = null; throw e })
  return englishLoad
}

/** The English help, loading it when `active`; null until it arrives. */
export function useEnglishHelp(active = true) {
  const [help, setHelp] = useState(english)
  useEffect(() => {
    if (!active || help) return undefined
    let live = true
    loadEnglishHelp().then((h) => { if (live) setHelp(h) }).catch(() => {})
    return () => { live = false }
  }, [active, help])
  return help
}

/** The language of the help for an interface language: its own when translated, else null (English). */
export function helpLanguage(lang) {
  const key = lang?.substring(0, 2)
  return HELP_TRANSLATED_LANGUAGES.includes(key) ? key : null
}

const pages = {}
/** One translated page ({ helpContent, helpGuides }), or null when the language has no help or the page no file. */
export function loadTranslatedPage(langKey, pageKey) {
  if (!langKey || !pageKey) return Promise.resolve(null)
  const at = `${langKey}/${pageKey}`
  pages[at] ||= loadHelpPage(langKey, pageKey).then((m) => m.default).catch(() => { delete pages[at]; return null })
  return pages[at]
}

/** The translated pages of `keys` for a language: { key: page | null }. */
export async function loadTranslatedPages(langKey, keys) {
  const all = await Promise.all(keys.map((k) => (langKey ? loadTranslatedPage(langKey, k) : null)))
  return Object.fromEntries(keys.map((k, i) => [k, all[i]]))
}
