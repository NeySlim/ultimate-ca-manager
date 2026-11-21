/** The Extensions panel: the mockup's extensionsDetail(), each X.509 extension with its OID, criticality and value. */
import { Fragment } from 'react'
import { useTranslation } from 'react-i18next'
import { extensionRows } from '../../../lib/certificateDetail'
import { truncateHex } from '../../../lib/customExtensions'

export function ExtensionsPanel({ cert }) {
  const { t } = useTranslation()
  const rows = extensionRows(cert.extensions, cert.san_combined)
  if (!rows.length) return <p className="muted small">{t('inspector.cert.noExtensions')}</p>
  return (
    <dl className="extensions" data-testid="certificate-extensions">
      {rows.map((r) => (
        <div key={r.key} className="extension">
          <dt>{r.label}<small className="mono">{r.oid}{r.critical ? ` · ${t('inspector.cert.critical')}` : ''}</small></dt>
          <dd title={r.hex ? r.values.join('\n') : undefined}>{r.values.map((v, i) => <Fragment key={i}>{i > 0 && <br />}{r.hex ? truncateHex(v) : v}</Fragment>)}</dd>
        </div>
      ))}
    </dl>
  )
}
