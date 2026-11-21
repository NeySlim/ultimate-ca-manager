/**
 * A page's quick help (helpContent.js) in the mockup's .help-grid.
 */
import { useTranslation } from 'react-i18next'

function Item({ item }) {
  const { t } = useTranslation()
  if (typeof item !== 'object') return <li>{item}</li>
  return <li>{item.label && <strong>{t('help.term', { term: item.label })}</strong>}{item.text}</li>
}

export function QuickHelp({ content }) {
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
