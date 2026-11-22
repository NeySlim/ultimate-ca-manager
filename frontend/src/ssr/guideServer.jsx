/**
 * The guide's chapters drawn at build time by the console itself (scripts/prerender-guide.js):
 * the whole App at /guide/<chapter> for a session not yet checked, which the server sends only
 * to a valid one, and the client's first render reproduces (ssr/takeOver.js).
 */
import React from 'react'
import { renderToString } from 'react-dom/server'
import { StaticRouter } from 'react-router-dom'
import App from '../App'
import i18n from '../i18n'
import { chapterText } from '../components/help'
import { HELP_TRANSLATED_LANGUAGES } from '../data/helpLanguages'
import { helpLanguage, loadEnglishHelp, loadTranslatedPage } from '../data/helpData'
import { GUIDE_CHAPTERS, guideChapter } from '../navigation/guide'
import { GuidePage } from '../navigation/pages'
import { setServedPage } from '../lib/servedPage'

/** The languages of the help; every other interface language reads the English one. */
export const LANGUAGES = ['en', ...HELP_TRANSLATED_LANGUAGES]
export const CHAPTERS = GUIDE_CHAPTERS.map((c) => c.key)

/** { html, title, chapterTitle } of one chapter in one language: #root's content and the tab's titles. */
export async function renderChapter(lang, chapter) {
  const current = guideChapter(chapter)
  if (!current || !LANGUAGES.includes(lang)) throw new Error(`guide prerender: no chapter ${lang}/${chapter}`)
  await i18n.changeLanguage(lang)
  const help = helpLanguage(lang)
  const [, english, page] = await Promise.all([GuidePage.preload(), loadEnglishHelp(), loadTranslatedPage(help, chapter)])
  const path = `/guide/${chapter}`
  setServedPage(path)
  const html = renderToString(
    <React.StrictMode>
      <App Router={StaticRouter} location={path} />
    </React.StrictMode>,
  )
  setServedPage(null)
  // The titles GuidePage gives the tab (useTabTitle), from the same text
  const chapterTitle = chapterText(chapter, english, help ? page : null, help)?.title || i18n.t(current.labelKey)
  return { html, title: i18n.t('guide.tabTitle', { chapter: chapterTitle }), chapterTitle }
}
