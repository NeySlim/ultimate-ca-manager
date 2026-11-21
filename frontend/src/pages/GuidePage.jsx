/**
 * The whole guide in a tab of its own (/guide/:chapter#section): one chapter at a time, the
 * chapters at the left (the mockup's settings table of contents, its jump select on a phone), the
 * chapter in a reading column with its actions above it, its sections in a column « On this page »
 * at the right (folded above the chapter on a narrower screen), its neighbours at the foot.
 * The document scrolls, and the <article> holds the chapter's text alone, for the browsers' reader view.
 * /guide?print=all lays every chapter one after the other for the browser's PDF.
 * The page follows the console's language and theme; it has no picker of either.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, Navigate, useLocation, useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Icon } from '../components/atelier/Icon'
import { markSrc } from '../components/atelier/icons'
import { Notice } from '../components/atelier/Form'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { GuideContent, QuickHelp, guideHeadings, mergeHelpContent, queryTerms } from '../components/help'
import { GuideSearch } from '../components/help/GuideSearch'
import { helpLanguage, loadTranslatedPage, loadTranslatedPages, useEnglishHelp } from '../data/helpData'
import { GUIDE_CHAPTERS, chapterOfAnchor, guideChapter, guideGroups, openPagePath } from '../navigation/guide'
import { usePermission } from '../hooks/usePermission'

const plainClick = (e) => e.button === 0 && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey
const idOfHash = (hash) => { try { return decodeURIComponent((hash || '').slice(1)) } catch { return '' } }

/**
 * A chapter's text in the reading language: { title, subtitle, quick, lang } or { title, markdown, english, lang };
 * lang is the language of the text shown, `en` where the translation has none.
 */
function chapterText(key, english, page, lang) {
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

/**
 * The tab's title while the page is open, the one before given back when it is left; og:title names the
 * chapter alone for a reader view, which does not cut the tab's title at its « · ».
 */
function useTabTitle(title, chapterTitle) {
  const meta = useRef(null)
  useEffect(() => {
    const before = document.title
    meta.current = document.createElement('meta')
    meta.current.setAttribute('property', 'og:title')
    document.head.appendChild(meta.current)
    return () => {
      document.title = before
      meta.current.remove()
    }
  }, [])
  useEffect(() => {
    document.title = title
    meta.current.setAttribute('content', chapterTitle)
  }, [title, chapterTitle])
}

/** The ## of a chapter, each with the ### under it: [{ ...heading, children }]. */
function sectionTree(headings) {
  const tree = []
  for (const h of headings) {
    const parent = tree[tree.length - 1]
    if (h.level === 3 && parent) parent.children.push(h)
    else tree.push({ ...h, children: [] })
  }
  return tree
}

/** The sections of the chapter read, the one being read marked; a ### under its ##. */
function OnThisPage({ tree, active, onJump }) {
  const item = (h) => (
    <a href={`#${h.id}`} className={`guide-onpage-h${h.level}`} data-level={h.level} aria-current={active === h.id ? 'true' : undefined}
      onClick={(e) => { if (!plainClick(e)) return; e.preventDefault(); onJump(h.id) }}>{h.text}</a>
  )
  return (
    <ul className="guide-onpage-list">
      {tree.map((h) => (
        <li key={h.id}>
          {item(h)}
          {h.children.length > 0 && <ul>{h.children.map((c) => <li key={c.id}>{item(c)}</li>)}</ul>}
        </li>
      ))}
    </ul>
  )
}

// The interface language when the help has no translation in it: the English help says so
function useHelpLanguage() {
  const { i18n } = useTranslation()
  const resolved = i18n.resolvedLanguage || i18n.language || 'en'
  return { lang: helpLanguage(resolved), englishNotice: !resolved.startsWith('en') && !helpLanguage(resolved) }
}

export default function GuidePage() {
  const { chapter } = useParams()
  const { search, hash } = useLocation()
  const params = new URLSearchParams(search)
  if (!chapter) {
    if (params.get('print') === 'all') return <GuidePrintAll />
    // /guide: the chapter of the section asked for, else the first one
    const to = chapterOfAnchor(idOfHash(hash)) || GUIDE_CHAPTERS[0]
    return <Navigate to={`/guide/${to.key}${search}${hash}`} replace />
  }
  if (!guideChapter(chapter)) return <Navigate to="/guide" replace />
  return <GuideChapter chapter={chapter} />
}

/** The page's frame: the brand and the way back to the console, the search at the middle. */
function GuideHead({ children, barRef }) {
  const { t } = useTranslation()
  return (
    <header className="masthead guide-head" ref={barRef}>
      <Link to="/" className="brand"><img src={markSrc} width="28" height="32" alt="" /><strong>UCM</strong><span>{t('guide.title')}</span></Link>
      <div className="guide-head-tools">{children}</div>
      <Link to="/" className="btn guide-back"><Icon name="grid" /><span className="guide-back-label">{t('help.back')}</span></Link>
    </header>
  )
}

function GuideChapter({ chapter }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { hash, search } = useLocation()
  // The terms of the search that led here stay marked in the chapter
  const highlight = queryTerms(new URLSearchParams(search).get('q') || '')
  const { lang, englishNotice } = useHelpLanguage()
  const english = useEnglishHelp()
  const { isAdmin, hasPermission } = usePermission()
  const [translated, setTranslated] = useState({ at: null, page: null })
  const [active, setActive] = useState(idOfHash(hash) || null)
  const barRef = useRef(null)
  const titleRef = useRef(null)
  const arrived = useRef(false)

  useEffect(() => {
    if (!lang) return undefined
    let live = true
    loadTranslatedPage(lang, chapter).then((page) => { if (live) setTranslated({ at: `${lang}/${chapter}`, page }) })
    return () => { live = false }
  }, [lang, chapter])

  // The chapter is shown once its translation is there: an anchor is reached in the text the reader reads
  const ready = !!english && (!lang || translated.at === `${lang}/${chapter}`)
  const text = useMemo(() => (ready ? chapterText(chapter, english, lang ? translated.page : null, lang) : null), [ready, chapter, english, lang, translated])
  const headings = useMemo(() => (text?.markdown ? guideHeadings(chapter, text.markdown, text.english).filter((h) => h.level <= 3) : []), [chapter, text])
  const tree = useMemo(() => sectionTree(headings), [headings])
  const current = guideChapter(chapter)
  const label = (c) => t(c.labelKey)

  const chapterTitle = text?.title || label(current)
  useTabTitle(t('guide.tabTitle', { chapter: chapterTitle }), chapterTitle)

  // React Router does not scroll to an anchor: the section asked for is reached once the text is in,
  // and takes the focus; a chapter opened from the contents gives it to its title
  useEffect(() => {
    if (!text) return
    const id = idOfHash(hash)
    const target = id && document.getElementById(id)
    if (target) {
      target.scrollIntoView?.({ block: 'start' })
      target.focus({ preventScroll: true })
      setActive(id)
    } else {
      window.scrollTo(0, 0)
      if (arrived.current) titleRef.current?.focus({ preventScroll: true })
      setActive(null)
    }
    arrived.current = true
  }, [text, hash])

  // The sections follow the reading: the last heading above the sticky bar's foot (and a line) is the current one
  useEffect(() => {
    if (!headings.length) return undefined
    const onScroll = () => {
      const top = (barRef.current?.getBoundingClientRect().bottom ?? 0) + 34
      let at = null
      for (const h of headings) {
        const node = document.getElementById(h.id)
        if (!node) continue
        if (node.getBoundingClientRect().top <= top) at = h.id
        else break
      }
      setActive(at)
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [headings])

  const jump = (id) => {
    navigate({ hash: id }, { replace: false })
    const node = document.getElementById(id)
    node?.scrollIntoView?.({ block: 'start' })
    node?.focus({ preventScroll: true })
    setActive(id)
  }

  const index = GUIDE_CHAPTERS.findIndex((c) => c.key === chapter)
  const previous = GUIDE_CHAPTERS[index - 1]
  const next = GUIDE_CHAPTERS[index + 1]
  const page = openPagePath(current, { isAdmin, hasPermission })
  const groups = guideGroups()
  const group = groups.find((g) => g.id === current.group)

  return (
    <div className="atl guide-app">
      <a className="skip guide-skip" href="#guide-article" onClick={(e) => { e.preventDefault(); titleRef.current?.focus() }}>{t('guide.skip')}</a>
      <GuideHead barRef={barRef}><GuideSearch lang={lang} /></GuideHead>
      <div className="stage guide-stage">
        <div className="settings-layout guide-layout">
          <nav className="settings-toc guide-toc" aria-label={t('guide.tocLabel')}>
            {groups.map((g) => (
              <div key={g.id} className="guide-toc-group">
                <h2 className="guide-toc-head" id={`guide-group-${g.id}`}>{t(g.labelKey)}</h2>
                <ul aria-labelledby={`guide-group-${g.id}`}>
                  {g.chapters.map((c) => (
                    <li key={c.key}>
                      <Link to={`/guide/${c.key}`} aria-current={c.key === chapter ? 'page' : undefined}><span>{label(c)}</span></Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </nav>
          <main className="settings-main guide-main" id="main">
            {/* A phone has no room for the contents: a select of the chapters, another of the sections */}
            <div className="field settings-jump guide-jump">
              <label htmlFor="guide-jump-chapter">{t('guide.jumpChapter')}</label>
              <select id="guide-jump-chapter" value={chapter} onChange={(e) => navigate(`/guide/${e.target.value}`)}>
                {groups.map((g) => (
                  <optgroup key={g.id} label={t(g.labelKey)}>
                    {g.chapters.map((c) => <option key={c.key} value={c.key}>{label(c)}</option>)}
                  </optgroup>
                ))}
              </select>
            </div>
            {headings.length > 0 && (
              <div className="field settings-jump guide-jump">
                <label htmlFor="guide-jump-section">{t('guide.jumpSection')}</label>
                <select id="guide-jump-section" value={active || ''} onChange={(e) => e.target.value && jump(e.target.value)}>
                  <option value="">{text?.title}</option>
                  {headings.map((h) => <option key={h.id} value={h.id}>{h.level === 3 ? `  ${h.text}` : h.text}</option>)}
                </select>
              </div>
            )}
            {englishNotice && <Notice>{t('help.englishOnlyNotice')}</Notice>}
            {/* The chapter's actions at its top, outside the article a reader view keeps */}
            <div className="actions guide-actions">
              {page && <Link className="btn primary" to={page}><Icon name="right" />{t('guide.openPage')}</Link>}
              <button type="button" className="btn" onClick={() => window.print()}>{t('guide.printChapter')}</button>
            </div>
            {tree.length > 0 && (
              <>
                <nav className="guide-onpage" aria-labelledby="guide-onpage-title">
                  <h2 className="guide-onpage-head" id="guide-onpage-title">{t('guide.onThisPage')}</h2>
                  <OnThisPage tree={tree} active={active} onJump={jump} />
                </nav>
                {/* Short of room for the column: the same list folded above the chapter */}
                <details className="guide-onpage-fold">
                  <summary>{t('guide.onThisPage')}</summary>
                  <OnThisPage tree={tree} active={active} onJump={jump} />
                </details>
              </>
            )}
            <article className="panel guide-article" id="guide-article" aria-labelledby="guide-title" lang={text?.lang}>
              <nav className="guide-crumbs" aria-label={t('guide.breadcrumbLabel')}>
                <ol>
                  <li>{t(group?.labelKey || 'guide.general')}</li>
                  <li aria-current="page">{label(current)}</li>
                </ol>
              </nav>
              <h1 id="guide-title" ref={titleRef} tabIndex={-1}>{chapterTitle}</h1>
              {text?.subtitle && <p className="guide-subtitle">{text.subtitle}</p>}
              {!text ? (
                <div className="guide-wait" role="status" aria-label={t('common.loading')}><LoadingSpinner size="lg" /></div>
              ) : text.quick ? (
                <QuickHelp content={text.quick} highlight={highlight} />
              ) : (
                <div className="guide-body"><GuideContent chapter={chapter} markdown={text.markdown} englishMarkdown={text.english} levelOffset={0} highlight={highlight} /></div>
              )}
            </article>
            <footer className="guide-foot">
              <nav className="guide-pager" aria-label={t('guide.pagerLabel')}>
                {previous && <Link to={`/guide/${previous.key}`} rel="prev"><small>{t('guide.previous')}</small><span>{label(previous)}</span></Link>}
                {next && <Link to={`/guide/${next.key}`} rel="next" className="guide-next"><small>{t('guide.next')}</small><span>{label(next)}</span></Link>}
              </nav>
              <div className="actions guide-print">
                <Link className="btn" to="/guide?print=all">{t('guide.printAll')}</Link>
              </div>
            </footer>
          </main>
        </div>
      </div>
    </div>
  )
}

/** Every chapter one after the other, each starting a printed page. */
function GuidePrintAll() {
  const { t } = useTranslation()
  const { lang, englishNotice } = useHelpLanguage()
  const english = useEnglishHelp()
  const [pages, setPages] = useState({ at: null, all: {} })
  const keys = GUIDE_CHAPTERS.map((c) => c.key)

  useEffect(() => {
    if (!lang) return undefined
    let live = true
    loadTranslatedPages(lang, keys).then((all) => { if (live) setPages({ at: lang, all }) })
    return () => { live = false }
    // keys is the fixed list of chapters
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lang])

  useTabTitle(t('guide.tabTitle', { chapter: t('guide.wholeGuide') }), t('guide.wholeGuide'))

  const ready = !!english && (!lang || pages.at === lang)
  return (
    <div className="atl guide-app guide-all">
      <GuideHead>
        <button type="button" className="btn primary" onClick={() => window.print()} disabled={!ready}>{t('guide.print')}</button>
      </GuideHead>
      <div className="stage guide-stage">
        <main className="guide-main guide-all-main" id="main">
          {englishNotice && <Notice>{t('help.englishOnlyNotice')}</Notice>}
          {!ready ? (
            <div className="guide-wait" role="status" aria-label={t('common.loading')}><LoadingSpinner size="lg" /></div>
          ) : GUIDE_CHAPTERS.map((c) => {
            const text = chapterText(c.key, english, lang ? pages.all[c.key] : null, lang)
            if (!text) return null
            return (
              <article key={c.key} className="panel guide-article guide-print-chapter" aria-labelledby={`guide-title-${c.key}`} data-chapter={c.key} lang={text.lang}>
                <h1 id={`guide-title-${c.key}`}>{text.title}</h1>
                {text.subtitle && <p className="guide-subtitle">{text.subtitle}</p>}
                {text.quick ? <QuickHelp content={text.quick} />
                  : <div className="guide-body"><GuideContent chapter={c.key} markdown={text.markdown} englishMarkdown={text.english} levelOffset={0} /></div>}
              </article>
            )
          })}
        </main>
      </div>
    </div>
  )
}
