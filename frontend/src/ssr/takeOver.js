/**
 * The guide's chapter the server drew in #root (data-guide="<lang>/<chapter>") is taken over as it
 * stands when the client would draw the same: same address without a query, same language, the page
 * and its text loaded first so the first render holds them. Otherwise the client draws afresh.
 */
import i18n from '../i18n'
import { GuidePage } from '../navigation/pages'
import { guideChapter } from '../navigation/guide'
import { helpLanguage, loadEnglishHelp, loadTranslatedPage, translatedPageNow } from '../data/helpData'
import { setServedPage } from '../lib/servedPage'

const initialized = () => (i18n.isInitialized ? Promise.resolve() : new Promise((resolve) => i18n.on('initialized', resolve)))

/** Whether the page in `container` is taken over (hydrated); false draws afresh. */
export async function takeOverServedGuide(container, location = window.location) {
  const [lang, chapter, extra] = (container?.dataset.guide || '').split('/')
  if (!lang || !chapter || extra !== undefined || !guideChapter(chapter)) return false
  const path = `/guide/${chapter}`
  if (location.pathname !== path || location.search) return false
  await initialized()
  if ((i18n.resolvedLanguage || i18n.language) !== lang) return false
  const help = helpLanguage(lang)
  await Promise.all([GuidePage.preload(), loadEnglishHelp(), loadTranslatedPage(help, chapter)])
  // A translation that failed to load would draw the English text over the server's
  if (help && !translatedPageNow(help, chapter)) return false
  setServedPage(path)
  return true
}
