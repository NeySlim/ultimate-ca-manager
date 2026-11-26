/**
 * A page's quick help (helpContent.js) in the mockup's .help-grid.
 */
import { useTranslation } from 'react-i18next'
import { Link, useInRouterContext } from 'react-router-dom'
import { guideChapter, guideHref } from '../../navigation/guide'
import { Facts } from '../atelier/Detail'
import { highlightTree, markText } from './highlight'

// An item's text is in its props, out of the tree's reach: it marks its own
function Item({ item, highlight }) {
  const { t } = useTranslation()
  const mark = (text) => (highlight?.length && typeof text === 'string' ? markText(text, highlight) : text)
  if (typeof item !== 'object') return <li>{mark(item)}</li>
  return <li>{item.label && <strong>{mark(t('help.term', { term: item.label }))}</strong>}{mark(item.text)}</li>
}

// The help's « see also » entries name chapters in English: each is the chapter it names, under its title in the language
const RELATED = {
  Overview: 'dashboard', Certificates: 'certificates', CAs: 'cas', CSRs: 'csrs', Templates: 'templates', Settings: 'settings',
  settings: 'settings', 'CRL/OCSP': 'crlocsp', 'CRL & OCSP': 'crlocsp', Account: 'account', 'Microsoft CA': 'msca', SCEP: 'scep',
  ACME: 'acme', RBAC: 'rbac', 'Audit Logs': 'auditLogs', auditLogs: 'auditLogs', 'Users & Groups': 'usersGroups',
  Operations: 'operations', 'Import/Export': 'operations', Approvals: 'approvals', Policies: 'policies', Reports: 'reports',
  'SSH Certificates': 'sshCertificates', 'SSH CAs': 'sshCas', 'SSH Hosts': 'sshHosts',
}

function Related({ name, newTab }) {
  const { t } = useTranslation()
  const routed = useInRouterContext()
  const chapter = guideChapter(RELATED[name] || name)
  if (!chapter?.labelKey) return <li>{name}</li>
  const tab = newTab ? { target: '_blank', rel: 'noopener' } : {}
  const href = guideHref(chapter.key)
  return (
    <li>
      {routed && !newTab
        ? <Link className="text-link" to={href}>{t(chapter.labelKey)}</Link>
        : <a className="text-link" href={href} {...tab}>{t(chapter.labelKey)}</a>}
    </li>
  )
}

/** highlight: folded search terms marked in the rendered text; newTab: the « see also » chapters open in a tab of their own. */
export function QuickHelp({ content, highlight, newTab = false }) {
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
      {content.related?.length > 0 && <section><h3>{t('help.seeAlso')}</h3><ul>{content.related.map((r, i) => <Related key={i} name={r} newTab={newTab} />)}</ul></section>}
    </div>
  )
  return highlight?.length ? highlightTree(grid, highlight) : grid
}
