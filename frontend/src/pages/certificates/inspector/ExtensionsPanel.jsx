/**
 * The Extensions panel: the mockup's extensionsDetail(), each X.509 extension with its OID, criticality
 * and value. A raw extension (DER in hex, shortened) keeps the copy of its whole value, as the
 * mockup's copy buttons (icon-btn quiet). A decoded value wraps after its separators (a key identifier between its bytes).
 */
import { Fragment } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from '../../../components/atelier'
import { Breakable } from '../../../components/atelier/Breakable'
import { useClipboard } from '../../../hooks/useClipboard'
import { extensionRows } from '../../../lib/certificateDetail'
import { truncateHex } from '../../../lib/customExtensions'

export function ExtensionsPanel({ cert }) {
  const { t } = useTranslation()
  const { copy, isCopied } = useClipboard()
  const rows = extensionRows(cert.extensions, cert.san_combined)
  if (!rows.length) return <p className="muted small">{t('inspector.cert.noExtensions')}</p>
  return (
    <dl className="extensions" data-testid="certificate-extensions">
      {rows.map((r) => (
        <div key={r.key} className="extension">
          <dt>{r.label}<small className="mono">{r.oid}{r.critical ? ` · ${t('inspector.cert.critical')}` : ''}</small></dt>
          <dd title={r.hex ? r.values.join('\n') : undefined}>{r.values.map((v, i) => <Fragment key={i}>{i > 0 && <br />}{r.hex ? truncateHex(v) : <Breakable text={v} />}</Fragment>)}
            {r.hex && r.values.length > 0 && (
              <>{' '}<button type="button" className="icon-btn quiet" aria-label={t('details.ext.copyValue')} title={t('details.ext.copyValue')}
                onClick={() => copy(r.values.join('\n'), r.key)}><Icon name={isCopied(r.key) ? 'check' : 'copy'} /></button></>
            )}
          </dd>
        </div>
      ))}
    </dl>
  )
}
