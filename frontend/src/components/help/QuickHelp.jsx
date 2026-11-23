/**
 * A page's quick help (helpContent.js) in the mockup's .help-grid.
 */
import { useTranslation } from 'react-i18next'
import { Facts } from '../atelier/Detail'
import { highlightTree, markText } from './highlight'

// An item's text is in its props, out of the tree's reach: it marks its own
function Item({ item, highlight }) {
  const { t } = useTranslation()
  const mark = (text) => (highlight?.length && typeof text === 'string' ? markText(text, highlight) : text)
  if (typeof item !== 'object') return <li>{mark(item)}</li>
  return <li>{item.label && <strong>{mark(t('help.term', { term: item.label }))}</strong>}{mark(item.text)}</li>
}

/** highlight: folded search terms marked in the rendered text. */
export function QuickHelp({ content, highlight }) {
  const { t } = useTranslation()
  // A definition's term and sentence are props of Facts, out of the tree's reach: marked here
  const mark = (text) => (highlight?.length && typeof text === 'string' ? markText(text, highlight) : text)
  const grid = (
    <div className="help-grid">
      {content.overview && <section><h3>{t('help.overview')}</h3><p>{content.overview}</p></section>}
      {content.sections?.map((section, i) => (
        <section key={i}>
          <h3>{section.title}</h3>
          {section.content && <p>{section.content}</p>}
          {section.items && <ul>{section.items.map((item, j) => <Item key={j} item={item} highlight={highlight} />)}</ul>}
          {section.definitions && (
            <Facts items={section.definitions.map((d, j) => ({ key: j, label: mark(d.term), value: mark(d.description), long: true }))} />
          )}
          {section.example && <pre className="code-preview">{section.example}</pre>}
        </section>
      ))}
      {content.tips?.length > 0 && <section><h3>{t('help.proTips')}</h3><ul>{content.tips.map((tip, i) => <li key={i}>{tip}</li>)}</ul></section>}
      {content.warnings?.length > 0 && <section><h3>{t('common.warnings')}</h3><ul>{content.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul></section>}
      {content.related?.length > 0 && <section><h3>{t('help.seeAlso')}</h3><ul>{content.related.map((r, i) => <li key={i}>{r}</li>)}</ul></section>}
    </div>
  )
  return highlight?.length ? highlightTree(grid, highlight) : grid
}
