/**
 * CAs page: the product's details of an authority beyond the mockup's caSide(), each in a folded
 * section of the side panel: RFC 5280 constraints, X.509 extensions, fingerprints, PEM, metadata.
 */
import { Icon, IconBtn } from '../../components/atelier'
import { SideFold } from '../../components/cas/SideField'
import { useClipboard } from '../../hooks/useClipboard'
import { extensionRows } from '../../lib/certificateDetail'
import { truncateHex } from '../../lib/customExtensions'
import { formatDate } from '../../lib/utils'

const present = (v) => v !== null && v !== undefined

function Copy({ value, label, copyKey, copy, isCopied, t }) {
  if (!value) return null
  return <IconBtn icon={isCopied(copyKey) ? 'check' : 'copy'} quiet label={isCopied(copyKey) ? t('common.copied') : label} onClick={() => copy(value, copyKey)} />
}

export function CASideDetails({ ca, t }) {
  const { copy, isCopied } = useClipboard()
  const clip = { copy, isCopied, t }
  const constraints = [
    present(ca.path_length) && [t('cas.pathLength'), ca.path_length === 0 ? t('cas.pathLengthLeafOnly') : String(ca.path_length)],
    ca.name_constraints_permitted?.length > 0 && [t('cas.nameConstraintsPermitted'), ca.name_constraints_permitted.map((c) => `${c.type}:${c.value}`).join(', ')],
    ca.name_constraints_excluded?.length > 0 && [t('cas.nameConstraintsExcluded'), ca.name_constraints_excluded.map((c) => `${c.type}:${c.value}`).join(', ')],
    present(ca.policy_constraints_require) && [t('cas.policyConstraintsRequire'), String(ca.policy_constraints_require)],
    present(ca.policy_constraints_inhibit) && [t('cas.policyConstraintsInhibit'), String(ca.policy_constraints_inhibit)],
    present(ca.inhibit_any_policy) && [t('cas.inhibitAnyPolicy'), String(ca.inhibit_any_policy)],
    ca.sia_enabled && ca.sia_urls?.length > 0 && [t('cas.siaUrls'), ca.sia_urls.join(', ')],
  ].filter(Boolean)
  const extensions = extensionRows(ca.extensions)

  return (
    <>
      {constraints.length > 0 && (
        <SideFold id={`ca-constraints-${ca.id}`} title={t('cas.rfc5280Constraints')} testId="ca-constraints">
          <dl className="props">
            {constraints.map(([k, v]) => <Pair key={k} k={k} v={v} mono />)}
          </dl>
        </SideFold>
      )}
      {ca.extensions && (
        <SideFold id={`ca-extensions-${ca.id}`} title={t('cas.side.extensions')} testId="ca-extensions">
          {extensions.length ? (
            <dl className="props">
              {extensions.map((r) => (
                <Pair key={r.key} k={<>{r.label}<br /><span className="muted small mono">{r.oid}{r.critical ? ` · ${t('inspector.cert.critical')}` : ''}</span></>}
                  v={r.values.map((v, i) => <span key={i} title={r.hex ? v : undefined}>{i > 0 && <br />}{r.hex ? truncateHex(v) : v}</span>)} />
              ))}
            </dl>
          ) : <p className="muted small">{t('inspector.cert.noExtensions')}</p>}
        </SideFold>
      )}
      {(ca.thumbprint_sha256 || ca.thumbprint_sha1) && (
        <SideFold id={`ca-fingerprints-${ca.id}`} title={t('common.fingerprints')} testId="ca-fingerprints">
          <dl className="props">
            <Pair k="SHA-256" v={<>{ca.thumbprint_sha256}<Copy value={ca.thumbprint_sha256} label={t('cas.side.copyValue', { name: 'SHA-256' })} copyKey="sha256" {...clip} /></>} mono />
            <Pair k="SHA-1" v={<>{ca.thumbprint_sha1}<Copy value={ca.thumbprint_sha1} label={t('cas.side.copyValue', { name: 'SHA-1' })} copyKey="sha1" {...clip} /></>} mono />
          </dl>
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
        <dl className="props">
          <Pair k={t('common.created')} v={ca.created_at ? formatDate(ca.created_at) : '—'} />
          <Pair k={t('details.createdBy')} v={ca.created_by || '—'} />
          <Pair k={t('details.importedFrom')} v={ca.imported_from || '—'} />
        </dl>
      </SideFold>
    </>
  )
}

function Pair({ k, v, mono = false }) {
  return <><dt>{k}</dt><dd className={mono ? 'mono' : undefined}>{v}</dd></>
}

export default CASideDetails
