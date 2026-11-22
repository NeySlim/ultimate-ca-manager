/**
 * CAs page: the product's details of an authority beyond the mockup's caSide(), each in a folded
 * section of the side panel: RFC 5280 constraints, X.509 extensions, fingerprints, PEM, metadata.
 * Each section is typed rows (Facts): digests and key identifiers in hex chips, URLs in url chips.
 */
import { CodeValue, Facts, Icon } from '../../components/atelier'
import { SideFold } from '../../components/cas/SideField'
import { useClipboard } from '../../hooks/useClipboard'
import { extensionRows } from '../../lib/certificateDetail'
import { formatDate } from '../../lib/utils'

const present = (v) => v !== null && v !== undefined
// The key identifiers of an extension are digests of a key, shown as the fingerprints are
const HEX_EXTENSIONS = new Set(['subject_key_identifier', 'authority_key_identifier'])
// « OCSP: http://… » or a bare URL: the prefix stays text, the URL goes in its chip
const URL_LINE = /^(?:([^:]+):\s+)?((?:https?|ldaps?|ftp):\/\/\S+)$/i

/** The values of an extension, one per line, each in the chip its kind calls for. */
function extensionValue(r) {
  return r.values.map((v, i) => {
    const text = String(v)
    const url = !r.hex && URL_LINE.exec(text)
    const shown = r.hex || HEX_EXTENSIONS.has(r.key) ? <CodeValue value={text} kind={HEX_EXTENSIONS.has(r.key) ? 'hex' : undefined} label={r.label} />
      : url ? <>{url[1] && <>{url[1]} </>}<CodeValue value={url[2]} kind="url" label={r.label} /></>
        : text
    return <div key={i}>{shown}</div>
  })
}

const absentOr = (label, value) => (value ? { label, value } : { label, absent: '—' })

export function CASideDetails({ ca, t }) {
  const { copy, isCopied } = useClipboard()
  const sia = ca.sia_enabled ? (ca.sia_urls || []).filter(Boolean) : []
  const constraints = [
    present(ca.path_length) && [t('cas.pathLength'), ca.path_length === 0 ? t('cas.pathLengthLeafOnly') : String(ca.path_length)],
    ca.name_constraints_permitted?.length > 0 && { label: t('cas.nameConstraintsPermitted'), value: ca.name_constraints_permitted.map((c) => `${c.type}:${c.value}`).join(', '), long: true },
    ca.name_constraints_excluded?.length > 0 && { label: t('cas.nameConstraintsExcluded'), value: ca.name_constraints_excluded.map((c) => `${c.type}:${c.value}`).join(', '), long: true },
    present(ca.policy_constraints_require) && [t('cas.policyConstraintsRequire'), String(ca.policy_constraints_require)],
    present(ca.policy_constraints_inhibit) && [t('cas.policyConstraintsInhibit'), String(ca.policy_constraints_inhibit)],
    present(ca.inhibit_any_policy) && [t('cas.inhibitAnyPolicy'), String(ca.inhibit_any_policy)],
    sia.length === 1 && { label: t('cas.siaUrls'), value: sia[0], kind: 'url', long: true, wide: true },
    sia.length > 1 && { label: t('cas.siaUrls'), value: sia.map((u) => <div key={u}><CodeValue value={u} kind="url" label={t('cas.siaUrls')} /></div>), long: true, wide: true },
  ].filter(Boolean)
  const extensions = extensionRows(ca.extensions)

  return (
    <>
      {constraints.length > 0 && (
        <SideFold id={`ca-constraints-${ca.id}`} title={t('cas.rfc5280Constraints')} testId="ca-constraints">
          <Facts items={constraints} />
        </SideFold>
      )}
      {ca.extensions && (
        <SideFold id={`ca-extensions-${ca.id}`} title={t('cas.side.extensions')} testId="ca-extensions">
          {extensions.length ? (
            <Facts items={extensions.map((r) => ({
              key: r.key, label: r.label, value: extensionValue(r), long: true,
              sub: <span className="mono">{r.oid}{r.critical ? ` · ${t('inspector.cert.critical')}` : ''}</span>,
            }))} />
          ) : <p className="muted small">{t('inspector.cert.noExtensions')}</p>}
        </SideFold>
      )}
      {(ca.thumbprint_sha256 || ca.thumbprint_sha1) && (
        <SideFold id={`ca-fingerprints-${ca.id}`} title={t('common.fingerprints')} testId="ca-fingerprints">
          <Facts items={[
            ca.thumbprint_sha256 ? { label: 'SHA-256', value: ca.thumbprint_sha256, kind: 'hex', long: true } : { label: 'SHA-256', absent: '—' },
            ca.thumbprint_sha1 ? { label: 'SHA-1', value: ca.thumbprint_sha1, kind: 'hex', long: true } : { label: 'SHA-1', absent: '—' },
          ]} />
        </SideFold>
      )}
      {ca.pem && (
        <SideFold id={`ca-pem-${ca.id}`} title={t('details.pemCertificate')} testId="ca-pem">
          <pre className="code-preview">{ca.pem}</pre>
          <div className="ca-side-tools">
            <button type="button" className="btn" onClick={() => copy(ca.pem, 'pem')}>
              <Icon name={isCopied('pem') ? 'check' : 'copy'} />{isCopied('pem') ? t('common.copied') : t('details.copyPem')}
            </button>
          </div>
        </SideFold>
      )}
      <SideFold id={`ca-metadata-${ca.id}`} title={t('details.metadata')} testId="ca-metadata">
        <Facts items={[
          absentOr(t('common.created'), ca.created_at && formatDate(ca.created_at)),
          absentOr(t('details.createdBy'), ca.created_by),
          absentOr(t('details.importedFrom'), ca.imported_from),
        ]} />
      </SideFold>
    </>
  )
}

export default CASideDetails
