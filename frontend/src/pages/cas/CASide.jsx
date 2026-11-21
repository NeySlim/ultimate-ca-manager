/**
 * CAs page: the side panel of the selected authority, the mockup's caSide() (head, notices, Identité,
 * Clé, Émission, Révocation, actions) on the API's data. The product's own rows follow the mockup's
 * rows of each section; its other details and actions come after (folded sections, « Autres actions »).
 */
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { Icon, AtelierDialog } from '../../components/atelier'
import { usePermission } from '../../hooks'
import { useEntityActions } from '../../hooks/useEntityActions'
import { casService, certificatesService, crlService } from '../../services'
import { downloadExport } from '../../lib/exportDownload'
import { useNotification } from '../../contexts'
import { extractData, formatDate } from '../../lib/utils'
import { holdsNoKey, needsKeyImport } from '../../lib/caSelection'
import { keyAlgorithmLabel } from '../../lib/keyAlgorithms'
import { SignatureSchemeField } from '../../components/cas/SignatureSchemeField'
import { ComplianceProfileField } from '../../components/cas/ComplianceProfileField'
import { IssuanceVisibilityField } from '../../components/cas/IssuanceVisibilityField'
import { UniqueSubjectField } from '../../components/cas/UniqueSubjectField'
import { ParentConfirmationSection } from '../../components/cas/ParentConfirmationSection'
import { CrossCertificatesSection } from '../../components/cas/CrossCertificatesSection'
import { ChainUsageSection } from '../../components/cas/ChainUsageSection'
import { SideAction } from '../../components/cas/SideField'
import { UploadCRLModal } from './UploadCRLModal'
import { CASideDetails } from './CASideDetails'
import { CAStatePill, CAMarks } from './CAState'
import { nameOfCA, issueBlockReason } from './caTree'

const DAY = 86400000

// The icon of each action of « Autres actions » (useEntityActions ids)
const ACTION_ICONS = {
  export: 'download', downloadCsr: 'download', uploadCertificate: 'upload', renewCsr: 'refresh', pins: 'pin',
  revoke: 'block', offline: 'lock', restore: 'refresh', delete: 'close',
}
// Reading actions: the others write and wait in maintenance or offline (data-write)
const READS = new Set(['export', 'downloadCsr'])
const DANGER = new Set(['revoke', 'delete'])

/** The detail of the authority (extensions, fingerprints), its CRL and its revoked certificates. */
function useSideData(ca, { readCrl, readCerts }) {
  const [detail, setDetail] = useState(null)
  const [crl, setCrl] = useState(undefined)
  const [revoked, setRevoked] = useState(undefined)
  const [tick, setTick] = useState(0)
  const id = ca?.id

  useEffect(() => {
    const handler = (e) => { if (e.detail?.type === 'ca' || e.detail?.type === 'crl') setTick((n) => n + 1) }
    window.addEventListener('ucm:data-changed', handler)
    return () => window.removeEventListener('ucm:data-changed', handler)
  }, [])

  useEffect(() => {
    if (!id) return undefined
    let live = true
    setDetail((d) => (d?.id === id ? d : null))
    casService.getById(id).then((res) => { if (live) setDetail(extractData(res) || null) }).catch(() => {})
    if (readCrl) {
      crlService.getForCA(id).then((res) => {
        const data = extractData(res)
        if (live) setCrl(data && data.crl_number != null ? data : null)
      }).catch(() => { if (live) setCrl(null) })
    }
    if (readCerts) {
      certificatesService.getAll({ ca_id: id, status: 'revoked', per_page: 1 })
        .then((res) => { if (live) setRevoked(res?.meta?.total ?? res?.pagination?.total ?? (res?.data || []).length) })
        .catch(() => { if (live) setRevoked(null) })
    }
    return () => { live = false }
  }, [id, readCrl, readCerts, tick])

  return { detail: detail?.id === id ? detail : null, setDetail, crl, revoked }
}

export function CASide({ ca: listed, cas, forest, crossLinks = [], ocsp, onPick, onIssue, onCleared, asideRef }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { showSuccess, showError } = useNotification()
  const { canRead, canWrite, hasPermission } = usePermission()
  const readCrl = canRead('crl')
  const readCerts = canRead('certificates')
  const { detail, setDetail, crl, revoked } = useSideData(listed, { readCrl, readCerts })
  const ca = useMemo(() => ({ ...listed, ...(detail || {}) }), [listed, detail])
  const [menuOpen, setMenuOpen] = useState(false)
  const [crlUpload, setCrlUpload] = useState(false)

  const { actions, modals, handler } = useEntityActions({
    type: 'ca', entity: ca, entityId: ca.id, afterMutation: 'refresh',
    onChanged: (updated) => setDetail(updated), onClose: onCleared,
  })

  const byId = forest.byId
  const parent = ca.parent_id ? byId.get(ca.parent_id) || cas.find((c) => c.id === ca.parent_id) : null
  const kids = forest.allKids.get(ca.id) || []
  const level = forest.levelOf.get(ca.id) || 1
  const root = ca.type === 'root' || ca.is_root
  const name = nameOfCA(ca) || t('cas.unnamedCA')
  const crossFrom = crossLinks.filter((l) => l.to === ca.id).map((l) => byId.get(l.from)).filter(Boolean)
  const crossTo = crossLinks.filter((l) => l.from === ca.id).map((l) => byId.get(l.to)).filter(Boolean)
  const reason = issueBlockReason(ca, t)
  const revokedCa = ca.revoked || ca.status === 'Revoked'
  const nextAt = crl?.next_update ? Date.parse(crl.next_update) : null
  const crlDue = !revokedCa && nextAt && nextAt - Date.now() < DAY
  const ocspActive = !!(ca.ocsp_enabled && ocsp?.enabled)
  const crlEligible = !ca.pending && (ca.offline || !ca.has_private_key)
  const storage = ca.uses_hsm ? 'hsm' : ca.offline ? 'offline' : ca.has_private_key ? 'software' : 'none'
  const menu = actions.filter((a) => a.visible && a.inBar !== false)
  const pick = (id) => onPick?.(id)

  const downloadChain = async () => {
    try {
      await downloadExport(casService.export(ca.id, 'pem', { includeChain: true }), { format: 'pem', name: `${name}-chain` })
      showSuccess(t('cas.side.chainDownloaded'))
    } catch (error) {
      showError(error?.status ? error.message : t('messages.errors.exportFailed.generic'))
    }
  }

  const runAction = (action) => {
    setMenuOpen(false)
    // After the menu dialog gave the focus back: the action's own dialog then keeps it
    requestAnimationFrame(() => requestAnimationFrame(() => action.onClick()))
  }

  const importKey = handler('importKey')

  return (
    <aside className="panel ca-side" aria-labelledby="ca-side-title" data-testid="ca-side" ref={asideRef}>
      <header className="ca-side-head">
        <Icon name={root ? 'shield' : 'branch'} />
        <div>
          <h2 id="ca-side-title">{name}</h2>
          <p>{ca.organization || t(root ? 'common.rootCA' : 'common.intermediateCA')}</p>
          <div className="ca-badges"><CAStatePill ca={ca} t={t} /><CAMarks ca={ca} t={t} /></div>
        </div>
      </header>

      {(ca.pending || ca.status === 'Pending') && <p className="notice warn"><Icon name="clock" />{t('cas.awaitingBannerText')}</p>}
      {revokedCa && (
        <p className="notice bad"><Icon name="block" />{t('cas.revokedBanner', {
          date: ca.revoked_at ? formatDate(ca.revoked_at) : '-',
          reason: t(`revocation.reasons.${ca.revoke_reason || 'unspecified'}`),
        })}</p>
      )}
      {ca.revoked_in_chain && !revokedCa && <p className="notice bad"><Icon name="block" />{t('cas.chainRevokedBanner')}</p>}
      {ca.offline && <p className="notice warn"><Icon name="lock" />{t('cas.side.offlineNote')}</p>}
      <ParentConfirmationSection ca={ca} canWrite={canWrite('cas')} onChanged={setDetail} />
      {holdsNoKey(ca) && (
        <p className={needsKeyImport(ca) ? 'notice warn' : 'notice'}>
          <Icon name="key" />
          <span>
            {t(needsKeyImport(ca) ? 'cas.certificateOnlyBanner' : 'cas.noPrivateKeyBanner')}
            {importKey && <SideAction onClick={importKey}>{t('cas.importPrivateKey')}</SideAction>}
          </span>
        </p>
      )}

      <section className="ca-side-section">
        <h3 className="section-title">{t('cas.side.identity')}</h3>
        <dl className="props">
          <dt>{t('cas.side.typeLevel')}</dt>
          <dd>{t(root ? 'cas.side.root' : 'cas.side.intermediate')} · {t('cas.tree.level', { level })}</dd>
          <dt>{t('cas.side.issuer')}</dt>
          <dd>
            {parent ? <button type="button" className="text-link" data-ca-pick={parent.id} onClick={() => pick(parent.id)}>{nameOfCA(parent)}</button>
              : root ? t('cas.side.selfSigned') : (ca.issuer || '—')}
            {crossFrom.map((c) => (
              <span key={c.id}><br /><span className="muted">{t('cas.side.crossIssuedBy', { name: nameOfCA(c) })}</span></span>
            ))}
          </dd>
          <dt>{t('cas.side.expiry')}</dt>
          <dd>{ca.valid_to ? formatDate(ca.valid_to, { time: false }) : '—'}</dd>
          <dt>pathLen</dt>
          <dd>{ca.path_length ?? t('cas.side.pathLenNone')}</dd>
          <Extra k={t('cas.side.subject')} v={ca.subject || '—'} mono />
          <Extra k={t('cas.side.serial')} v={ca.serial_number || ca.serial || '—'} mono />
          <Extra k={t('cas.side.validFrom')} v={ca.valid_from ? formatDate(ca.valid_from, { time: false }) : '—'} />
        </dl>
      </section>

      <section className="ca-side-section">
        <h3 className="section-title">{t('cas.side.key')}</h3>
        <dl className="props">
          <dt>{t('cas.side.algorithm')}</dt>
          <dd>{keyAlgorithmLabel(ca.key_type, t, ca.security_level) || '—'}</dd>
          <dt>{t('cas.side.storage')}</dt>
          <dd>
            {t(`cas.side.storageKinds.${storage}`)}
            {ca.uses_hsm && (ca.hsm_provider_name || ca.hsm_key_label) && (
              <><br /><span className="muted">{[ca.hsm_provider_name, ca.hsm_key_label].filter(Boolean).join(' / ')}</span></>
            )}
          </dd>
          <Extra k={t('cas.side.signature')} v={ca.signature_algorithm || ca.hash_algorithm || '—'} />
          <SignatureSchemeField ca={ca} canWrite={canWrite('cas')} onChanged={setDetail} />
        </dl>
      </section>

      <section className="ca-side-section">
        <h3 className="section-title">{t('cas.side.issuance')}</h3>
        <dl className="props">
          <dt>{t('cas.side.issued')}</dt>
          <dd>{ca.certs || 0}</dd>
          {readCerts && <><dt>{t('cas.side.revokedOf')}</dt><dd>{revoked === undefined ? '…' : revoked === null ? '—' : revoked}</dd></>}
          <dt>{t('cas.side.subAuthorities')}</dt>
          <dd>
            {kids.length ? (
              <ul className="link-list">
                {kids.map((k) => <li key={k.id}><button type="button" className="text-link" data-ca-pick={k.id} onClick={() => pick(k.id)}>{nameOfCA(k)}</button></li>)}
              </ul>
            ) : t('cas.side.none')}
          </dd>
          {crossTo.length > 0 && (
            <>
              <dt>{t('cas.side.crossIssued')}</dt>
              <dd>
                <ul className="link-list">
                  {crossTo.map((k) => <li key={k.id}><button type="button" className="text-link" data-ca-pick={k.id} onClick={() => pick(k.id)}>{nameOfCA(k)}</button></li>)}
                </ul>
              </dd>
            </>
          )}
          <IssuanceVisibilityField ca={ca} canWrite={canWrite('cas')} onChanged={setDetail} />
          <UniqueSubjectField ca={ca} canWrite={canWrite('cas')} onChanged={setDetail} />
          <ComplianceProfileField ca={ca} canWrite={canWrite('cas')} canAttach={canWrite('cas') && hasPermission('admin:system')} onChanged={setDetail} />
        </dl>
      </section>

      {readCrl && (
        <section className="ca-side-section">
          <h3 className="section-title">{t('cas.side.revocation')}</h3>
          <dl className="props">
            <dt>{t('cas.side.crlPublished')}</dt>
            <dd>{crl === undefined ? '…' : crl ? formatDate(crl.this_update) : t('cas.crlNone')}</dd>
            <dt>{t('cas.side.crlNext')}</dt>
            <dd>{crl?.next_update ? formatDate(crl.next_update) : '—'}</dd>
            <dt>{t('cas.side.crlNumber')}</dt>
            <dd className="mono">{crl?.crl_number ?? '—'}</dd>
            <dt>{t('cas.side.ocsp')}</dt>
            <dd>{ocspActive
              ? <span className="badge good"><Icon name="check" />{t('cas.side.ocspActive')}</span>
              : <span className="badge muted"><Icon name="block" />{t('cas.side.ocspInactive')}</span>}</dd>
            {crl && <Extra k={t('cas.crlEntries')} v={<>{crl.revoked_count ?? 0}{crl.is_external && <span className="muted"> · {t('cas.crlExternal')}</span>}</>} />}
            {ca.cdp_enabled && ca.cdp_url && <Extra k={t('cas.side.cdp')} v={ca.cdp_url} mono />}
            {ca.ocsp_enabled && ca.ocsp_url && <Extra k={t('cas.side.ocspUrl')} v={ca.ocsp_url} mono />}
          </dl>
          {crlDue && <p className="notice warn crl-due"><Icon name="warning" /><span>{t('cas.side.crlDue')}</span></p>}
          {crl?.is_stale && !crlDue && <p className="notice warn"><Icon name="warning" /><span>{t('cas.crlStaleWarning')}</span></p>}
          {crlEligible && canWrite('crl') && (
            <div className="ca-side-tools">
              <button type="button" className="btn" data-write="" onClick={() => setCrlUpload(true)}><Icon name="upload" />{t('cas.uploadCrl')}</button>
            </div>
          )}
        </section>
      )}

      <div className="ca-actions">
        {readCerts && (
          <button type="button" className="btn primary" data-ca-certs={ca.id} onClick={() => navigate(`/certificates?ca_id=${ca.id}`)}>
            <Icon name="cert" />{t('cas.side.viewCertificates')}
          </button>
        )}
        {canWrite('certificates') && (
          <button type="button" className="btn" data-issue-ca={ca.id} data-write="" disabled={!!reason}
            aria-describedby={reason ? 'issue-blocked' : undefined} onClick={() => onIssue?.(ca)}>
            <Icon name="plus" />{t('cas.side.issueWith')}
          </button>
        )}
        {canWrite('certificates') && reason && <p className="notice" id="issue-blocked"><Icon name="help" />{reason}</p>}
        {!ca.pending && (
          <button type="button" className="btn" data-chain-download={ca.id} onClick={downloadChain}>
            <Icon name="download" />{t('cas.side.downloadChain')}
          </button>
        )}
        {menu.length > 0 && (
          <button type="button" className="btn" id="ca-more-actions" aria-haspopup="dialog" onClick={() => setMenuOpen(true)}>
            <Icon name="more" />{t('cas.side.moreActions')}
          </button>
        )}
      </div>

      <CrossCertificatesSection ca={ca} canWrite={canWrite('cas')} />
      <ChainUsageSection ca={ca} />
      <CASideDetails ca={ca} t={t} />

      {menuOpen && (
        <CAActionsDialog name={name} actions={menu} onRun={runAction} onClose={() => setMenuOpen(false)} t={t} />
      )}
      {crlUpload && <UploadCRLModal open onClose={() => setCrlUpload(false)} ca={ca}
        onSuccess={() => window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type: 'crl' } }))} />}
      {modals}
    </aside>
  )
}

/** A row the mockup's caSide() does not have (`data-product`, declared to the comparator). */
function Extra({ k, v, mono = false }) {
  return <><dt data-product="">{k}</dt><dd data-product="" className={mono ? 'mono' : undefined}>{v}</dd></>
}

/** « Actions de l'autorité », the mockup's certMenu(): the authority's name, then one button per action. */
function CAActionsDialog({ name, actions, onRun, onClose, t }) {
  return (
    <AtelierDialog title={t('cas.side.actionsTitle')} size="narrow" onClose={onClose} testId="ca-actions-dialog">
      <p className="muted" style={{ marginBottom: 20 }}>{name}</p>
      <div className="columns-list">
        {actions.map((a) => (
          <button key={a.id} type="button" className={DANGER.has(a.id) ? 'btn danger' : 'btn'} data-action={a.id}
            data-write={READS.has(a.id) ? undefined : ''} disabled={a.disabled} onClick={() => onRun(a)}>
            <Icon name={ACTION_ICONS[a.id] || 'more'} />{a.label}{DANGER.has(a.id) || a.id === 'offline' ? '…' : ''}
          </button>
        ))}
      </div>
    </AtelierDialog>
  )
}

export default CASide
