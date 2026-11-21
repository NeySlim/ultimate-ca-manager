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
import { helpContent as defaultHelpData } from '../../data/helpContent'
import { helpGuides as defaultHelpGuides } from '../../data/helpGuides'
import { HELP_TRANSLATED_LANGUAGES } from '../../data/helpLanguages'
import { loadHelpPage } from '../../data/helpLoader'

// English structure, translated text where the language has it
export function mergeHelpContent(en, tr) {
  if (!tr) return en
  return {
    ...en,
    title: tr.title || en.title,
    subtitle: tr.subtitle || en.subtitle,
    overview: tr.overview || en.overview,
    sections: en.sections?.map((sec, i) => ({
      ...sec,
      title: tr.sections?.[i]?.title || sec.title,
      content: tr.sections?.[i]?.content ?? sec.content,
      items: sec.items?.map((item, j) => {
        const trItem = tr.sections?.[i]?.items?.[j]
        if (!trItem) return item
        if (typeof item === 'string') return trItem
        return { ...item, label: trItem?.label || item.label, text: trItem?.text || item.text }
      }),
      definitions: sec.definitions?.map((def, j) => ({
        ...def,
        term: tr.sections?.[i]?.definitions?.[j]?.term || def.term,
        description: tr.sections?.[i]?.definitions?.[j]?.description || def.description,
      })),
      example: tr.sections?.[i]?.example ?? sec.example,
    })),
    tips: tr.tips || en.tips,
    warnings: tr.warnings || en.warnings,
    related: en.related,
  }
}

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

function Item({ item }) {
  const { t } = useTranslation()
  if (typeof item !== 'object') return <li>{item}</li>
  return <li>{item.label && <strong>{t('help.term', { term: item.label })}</strong>}{item.text}</li>
}

function QuickHelp({ content }) {
  const { t } = useTranslation()
  return (
    <div className="help-grid">
      {content.overview && <section><h3>{t('help.overview')}</h3><p>{content.overview}</p></section>}
      {content.sections?.map((section, i) => (
        <section key={i}>
          <h3>{section.title}</h3>
          {section.content && <p>{section.content}</p>}
          {section.items && <ul>{section.items.map((item, j) => <Item key={j} item={item} />)}</ul>}
          {section.definitions && (
            <dl className="props">{section.definitions.map((d, j) => [<dt key={`t${j}`}>{d.term}</dt>, <dd key={`d${j}`}>{d.description}</dd>])}</dl>
          )}
          {section.example && <pre className="code-preview">{section.example}</pre>}
        </section>
      ))}
      {content.tips?.length > 0 && <section><h3>{t('help.proTips')}</h3><ul>{content.tips.map((tip, i) => <li key={i}>{tip}</li>)}</ul></section>}
      {content.warnings?.length > 0 && <section><h3>{t('common.warnings')}</h3><ul>{content.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul></section>}
      {content.related?.length > 0 && <section><h3>{t('help.seeAlso')}</h3><ul>{content.related.map((r, i) => <li key={i}>{r}</li>)}</ul></section>}
    </div>
  )
}

// The guide's markdown: one section per `## ` heading (the whole text when it has none)
export function guideSections(md) {
  const sections = []
  let current = null
  for (const line of (md || '').split('\n')) {
    const h2 = line.match(/^## (.+)/)
    if (h2) {
      current = { title: h2[1].trim(), lines: [] }
      sections.push(current)
    } else if (current) current.lines.push(line)
  }
  return sections.length ? sections : [{ title: '', lines: (md || '').split('\n') }]
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

// Paragraphs, lists, sub-headings, quotes and code of the guide, in the mockup's help vocabulary
function renderLines(lines) {
  const out = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (line.trim() === '') { i++; continue }
    const sub = line.match(/^#{3,4} (.+)/)
    if (sub) { out.push(<p key={i}><strong>{inline(sub[1].trim())}</strong></p>); i++; continue }
    if (line.trim().startsWith('```')) {
      const code = []
      const at = i
      i++
      while (i < lines.length && !lines[i].trim().startsWith('```')) code.push(lines[i++])
      i++
      out.push(<pre key={`c${at}`} className="code-preview">{code.join('\n')}</pre>)
      continue
    }
    if (line.trim().startsWith('> ')) {
      const quote = []
      const at = i
      while (i < lines.length && lines[i].trim().startsWith('> ')) quote.push(lines[i++].trim().replace(/^>\s?/, ''))
      out.push(<Notice key={`q${at}`}>{inline(quote.join(' '))}</Notice>)
      continue
    }
    const list = [[/^\s*[-*]\s/, 'ul'], [/^\d+\.\s/, 'ol']].find(([re]) => re.test(line))
    if (list) {
      const [re, Tag] = list
      const items = []
      const at = i
      while (i < lines.length && re.test(lines[i])) items.push(lines[i++].replace(re, ''))
      out.push(<Tag key={`l${at}`}>{items.map((it, j) => <li key={j}>{inline(it)}</li>)}</Tag>)
      continue
    }
    out.push(<p key={i}>{inline(line)}</p>)
    i++
  }
  return out
}

// **bold**, `code` and *italic*
function inline(text) {
  const parts = []
  let rest = text
  let key = 0
  while (rest) {
    const found = [[/\*\*(.+?)\*\*/, 'b'], [/`([^`]+)`/, 'c'], [/(?<!\*)\*([^*]+)\*(?!\*)/, 'i']]
      .map(([re, kind]) => [rest.match(re), kind]).filter(([m]) => m).sort((a, b) => a[0].index - b[0].index)[0]
    if (!found) { parts.push(rest); break }
    const [m, kind] = found
    if (m.index > 0) parts.push(rest.slice(0, m.index))
    parts.push(kind === 'b' ? <strong key={key++}>{m[1]}</strong> : kind === 'c' ? <span key={key++} className="mono">{m[1]}</span> : <em key={key++}>{m[1]}</em>)
    rest = rest.slice(m.index + m[0].length)
  }
  return parts.length === 1 ? parts[0] : parts
}

export default HelpDialog
