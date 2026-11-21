/**
 * The help of the current page in the mockup's help(): its wide modal(), the sections in a
 * .help-grid, Revenir à la console at the foot. The product keeps its two readings of a page
 * (Quick help, Guide) behind a segmented switch, and the guide its search and its contents line.
 */
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AtelierDialog } from '../atelier/AtelierDialog'
import { Toolbar, SearchField } from '../atelier/Toolbar'
import { ModalActions, Notice } from '../atelier/Form'
import { QuickHelp } from '../help/QuickHelp'
import { mergeHelpContent } from '../help/content'
import { guideSections, renderLines } from '../help/markdown'
import { helpContent as defaultHelpData } from '../../data/helpContent'
import { helpGuides as defaultHelpGuides } from '../../data/helpGuides'
import { HELP_TRANSLATED_LANGUAGES } from '../../data/helpLanguages'
import { loadHelpPage } from '../../data/helpLoader'

const sectionCache = {}
// One translated page per language and page, loaded on demand; a superseded load never lands
function useHelpTranslation(lang, pageKey) {
  const [translation, setTranslation] = useState(null)
  const langKey = lang?.substring(0, 2)
  useEffect(() => {
    if (!pageKey || !HELP_TRANSLATED_LANGUAGES.includes(langKey)) {
      setTranslation(null)
      return
    }
    const cacheKey = `${langKey}/${pageKey}`
    if (sectionCache[cacheKey]) {
      setTranslation(sectionCache[cacheKey])
      return
    }
    setTranslation(null)
    let live = true
    loadHelpPage(langKey, pageKey)
      .then(mod => {
        sectionCache[cacheKey] = mod.default
        if (live) setTranslation(mod.default)
      })
      .catch(() => {})
    return () => { live = false }
  }, [langKey, pageKey])
  return translation
}

/** open: shown; pageKey: the entry of helpContent / helpGuides; returnTo: the id that takes the focus back. */
export function HelpDialog({ open, onClose, pageKey, returnTo }) {
  const { t, i18n } = useTranslation()
  const translation = useHelpTranslation(i18n.resolvedLanguage, open ? pageKey : null)
  const langKey = i18n.resolvedLanguage?.substring(0, 2)
  const englishNotice = !!langKey && langKey !== 'en' && !HELP_TRANSLATED_LANGUAGES.includes(langKey)

  const quick = useMemo(() => {
    const en = pageKey ? defaultHelpData[pageKey] : null
    return en ? mergeHelpContent(en, translation?.helpContent) : null
  }, [pageKey, translation])

  const guide = useMemo(() => {
    const en = pageKey ? defaultHelpGuides[pageKey] : null
    if (!en) return null
    const tr = translation?.helpGuides
    return tr ? { ...en, title: tr.title || en.title, content: tr.content || en.content } : en
  }, [pageKey, translation])

  if (!open || (!quick && !guide)) return null
  return (
    <AtelierDialog title={quick?.title || guide?.title || t('common.help')} subtitle={quick?.subtitle || undefined}
      size="wide" onClose={onClose} returnTo={returnTo} testId="help-dialog">
      <HelpBody key={pageKey} quick={quick} guide={guide} englishNotice={englishNotice} />
      <ModalActions>
        <button type="button" className="btn primary" data-action="close-modal" onClick={onClose}>{t('help.back')}</button>
      </ModalActions>
    </AtelierDialog>
  )
}

function HelpBody({ quick, guide, englishNotice }) {
  const { t } = useTranslation()
  const [tab, setTab] = useState(guide ? 'guide' : 'quick')
  const [query, setQuery] = useState('')
  const both = !!quick && !!guide
  return (
    <>
      {englishNotice && <Notice>{t('help.englishOnlyNotice')}</Notice>}
      {(both || tab === 'guide') && (
        <Toolbar>
          {both && (
            <div className="segmented" role="group" aria-label={t('help.views')}>
              <button type="button" aria-pressed={tab === 'quick'} onClick={() => setTab('quick')}>{t('help.quickHelp')}</button>
              <button type="button" aria-pressed={tab === 'guide'} onClick={() => setTab('guide')}>{t('help.guide')}</button>
            </div>
          )}
          {tab === 'guide' && (
            <SearchField id="help-search" name="helpSearch" label={t('help.searchLabel')} placeholder={t('help.searchPlaceholder')}
              value={query} onChange={setQuery} />
          )}
        </Toolbar>
      )}
      {tab === 'quick' ? <QuickHelp content={quick} /> : <GuideHelp markdown={guide.content} query={query} />}
    </>
  )
}

function GuideHelp({ markdown, query }) {
  const { t } = useTranslation()
  const sections = useMemo(() => guideSections(markdown), [markdown])
  const q = query.trim().toLowerCase()
  const shown = sections
    .map((s, i) => ({ ...s, i }))
    .filter((s) => !q || s.title.toLowerCase().includes(q) || s.lines.some((l) => l.toLowerCase().includes(q)))
  const jump = (e, i) => {
    e.preventDefault()
    const head = document.getElementById(`help-section-${i}`)
    head?.scrollIntoView({ block: 'start' })
    head?.focus({ preventScroll: true })
  }
  return (
    <>
      {shown.length > 2 && (
        <p className="small muted help-toc">
          {t('help.contentsLead')}
          {shown.map((s, k) => (
            <span key={s.i}>{k > 0 && ', '}<a className="text-link" href={`#help-section-${s.i}`} onClick={(e) => jump(e, s.i)}>{s.title}</a></span>
          ))}
        </p>
      )}
      {shown.length === 0 ? <p className="muted">{t('help.noMatch')}</p> : (
        <div className="help-grid">
          {shown.map((s) => (
            <section key={s.i}>
              {s.title && <h3 id={`help-section-${s.i}`} tabIndex={-1}>{s.title}</h3>}
              {renderLines(s.lines)}
            </section>
          ))}
        </div>
      )}
    </>
  )
}

export default HelpDialog
