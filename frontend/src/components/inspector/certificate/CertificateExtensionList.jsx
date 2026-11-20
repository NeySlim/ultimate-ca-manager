/** X.509 extensions of a certificate: name and OID on the left, value on the right. */
import { useTranslation } from 'react-i18next'
import { extensionRows } from '../../../lib/certificateDetail'
import { truncateHex } from '../../../lib/customExtensions'

export function CertificateExtensionList({ cert, columns }) {
  const { t } = useTranslation()
  const rows = extensionRows(cert.extensions, cert.san_combined)
  if (!rows.length) return <p className="ins-muted">{t('inspector.cert.noExtensions')}</p>
  return (
    <dl className="ins-extensions" data-columns={columns} data-testid="certificate-extensions">
      {rows.map((r) => (
        <div key={r.key} className="ins-extension">
          <dt>
            {r.labelKey ? t(r.labelKey) : r.label}
            <small className="ins-mono">{r.oid}{r.critical ? ` · ${t('inspector.cert.critical')}` : ''}</small>
          </dt>
          <dd>
            {r.values.map((v, i) => (
              <span key={i} title={r.hex ? v : undefined}>{i > 0 && <br />}{r.hex ? truncateHex(v) : v}</span>
            ))}
          </dd>
        </div>
      ))}
    </dl>
  )
}
