/**
 * The search over the whole guide, in the guide page's masthead: the index of every section,
 * in the reading language with the English help where it has no translation, loaded at the
 * first focus of the field; results by chapter (a section's title, an excerpt, the terms marked),
 * the arrows to move through them, Enter or a click to open one, Escape to close.
 */
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Icon } from '../atelier/Icon'
import { loadGuideIndex } from './guideIndex'
import { markText } from './highlight'
import { excerpt, groupByChapter, queryTerms, searchIndex } from './search'

// At most this many results are drawn; the count announced is the whole of them
const SHOWN = 60

/** lang: the help language (null for English). */
export function GuideSearch({ lang }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [index, setIndex] = useState(null)
  const [open, setOpen] = useState(false)
  const inputRef = useRef(null)
  const listRef = useRef(null)
  const wrapRef = useRef(null)
  const asked = useRef(false)

  const load = () => {
    if (asked.current) return
    asked.current = true
    loadGuideIndex(lang).then(setIndex).catch(() => { asked.current = false })
  }

  // A click outside the search closes its results
  useEffect(() => {
    if (!open) return undefined
    const away = (e) => { if (!wrapRef.current?.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', away)
    return () => document.removeEventListener('mousedown', away)
  }, [open])

  const terms = queryTerms(query)
  const found = index && terms.length ? searchIndex(index, terms) : []
  const groups = groupByChapter(found.slice(0, SHOWN))
  const shown = open && terms.length > 0

  const go = (r) => {
    setOpen(false)
    const q = `?q=${encodeURIComponent(query.trim())}`
    navigate(`/guide/${r.chapter}${q}${r.id ? `#${r.id}` : ''}`)
  }

  const buttons = () => [...(listRef.current?.querySelectorAll('.guide-result') || [])]
  const onKeyDown = (e) => {
    const all = buttons()
    const i = all.indexOf(document.activeElement)
    if (e.key === 'ArrowDown') {
      if (!all.length) return
      e.preventDefault()
      setOpen(true)
      all[Math.min(i + 1, all.length - 1)].focus()
    } else if (e.key === 'ArrowUp' && i >= 0) {
      e.preventDefault()
      if (i === 0) inputRef.current?.focus()
      else all[i - 1].focus()
    } else if (e.key === 'Enter' && e.target === inputRef.current && found[0]) {
      e.preventDefault()
      go(found[0])
    } else if (e.key === 'Escape' && shown) {
      e.preventDefault()
      setOpen(false)
      inputRef.current?.focus()
    }
  }

  const status = !terms.length ? '' : !index ? t('guide.searchLoading')
    : found.length ? t('guide.results', { count: found.length }) : t('guide.noResults')

  return (
    <div className="guide-search" ref={wrapRef} onKeyDown={onKeyDown}>
      <label className="search">
        <Icon name="search" />
        <span className="sr-only">{t('guide.searchLabel')}</span>
        <input ref={inputRef} id="guide-search" type="search" name="guideSearch" autoComplete="off" spellCheck={false}
          placeholder={t('guide.searchPlaceholder')} value={query} aria-controls="guide-results"
          onFocus={() => { load(); setOpen(true) }} onChange={(e) => { setQuery(e.target.value); setOpen(true); load() }} />
      </label>
      <p className="sr-only" role="status" aria-live="polite">{status}</p>
      {shown && (
        <div className="guide-results" id="guide-results" ref={listRef} role="region" aria-label={t('guide.resultsLabel')} aria-busy={!index || undefined}>
          {!index ? <p className="muted guide-results-note">{t('guide.searchLoading')}</p>
            : !found.length ? <p className="muted guide-results-note">{t('guide.noResults')}</p> : (
              <>
                <p className="guide-results-count">{t('guide.results', { count: found.length })}{found.length > SHOWN && ` ${t('guide.resultsShown', { shown: SHOWN })}`}</p>
                {groups.map((g) => (
                  <section key={g.chapter} className="guide-results-group" aria-label={g.chapterTitle}>
                    <h2 className="guide-results-head">{g.chapterTitle}</h2>
                    <ul>
                      {g.results.map((r, i) => (
                        <li key={`${r.id}-${i}`}>
                          <button type="button" className="command-result guide-result" onClick={() => go(r)}>
                            <span className="name">{markText(r.title, terms)}</span>
                            <span className="guide-excerpt">{markText(excerpt(r.text, terms), terms)}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </section>
                ))}
              </>
            )}
        </div>
      )}
    </div>
  )
}
