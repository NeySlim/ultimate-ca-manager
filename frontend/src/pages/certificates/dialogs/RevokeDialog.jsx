/**
 * The mockup's revokeDialog(): the warning, the name, « Motif » (the RFC 5280 reasons), what the
 * reason means, Annuler and the danger button. The product asks about the other member of a hybrid
 * pair (RFC 9763). Same props as components/RevokeCertificateModal.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AtelierDialog, Icon } from '../../../components/atelier'
import { certificatesService } from '../../../services'
import { REVOCATION_REASONS } from '../../../components/RevokeCertificateModal'

export function RevokeDialog(props) {
  if (!props.open) return null
  return <RevokeBody {...props} />
}

function RevokeBody({ onClose, onConfirm, certificate, loading = false, count = 1, title, warning, allowHold = true }) {
  const { t } = useTranslation()
  const [reason, setReason] = useState('unspecified')
  const [revokeRelated, setRevokeRelated] = useState(true)
  // 'loading' | 'revocable' | 'none' | 'unknown' (the lookup failed: the server decides)
  const [related, setRelated] = useState('none')
  const relatedId = certificate?.related_certificate_id ?? null
  const certId = certificate?.id
  const hasRelated = related === 'revocable' || related === 'unknown'
  useEffect(() => {
    if (relatedId == null) return undefined
    let live = true
    setRelated('loading')
    certificatesService.getById(relatedId)
      .then((res) => {
        const other = res?.data ?? res
        if (live) setRelated(other && other.related_certificate_id === certId && !other.revoked && !other.archived ? 'revocable' : 'none')
      })
      .catch(() => { if (live) setRelated('unknown') })
    return () => { live = false }
  }, [relatedId, certId])
  const checking = related === 'loading'
  const name = certificate?.name || certificate?.common_name || certificate?.cn || certificate?.descr || ''
  const help = count > 1 ? t('revocation.bulkReasonHelp') : t(allowHold ? 'revocation.reasonHelp' : 'revocation.reasonHelpNoHold')
  const submit = () => {
    if (loading || checking) return
    if (hasRelated) onConfirm(reason, { revokeRelated })
    else onConfirm(reason)
  }
  return (
    <AtelierDialog title={title || t('revocation.dialogTitle')} size="narrow" onClose={onClose} testId="revoke-dialog">
      <>
        <div className="notice warn"><Icon name="warning" /><span>{warning || t('revocation.notice')}{certificate?.source === 'msca' && <> {t('certificates.revokeMscaWarning')}</>}</span></div>
        {name && <p style={{ marginBottom: 20, overflowWrap: 'anywhere' }}>{name}</p>}
        <label className="field">{t('revocation.reason')}
          <select id="revoke-reason" value={reason} onChange={(e) => setReason(e.target.value)} data-testid="revoke-reason">
            {REVOCATION_REASONS.filter((r) => allowHold || r !== 'certificateHold').map((r) => <option key={r} value={r}>{t(`revocation.reasons.${r}`)}</option>)}
          </select>
        </label>
        <p className="small muted" style={{ marginTop: 14 }}>{t(`revocation.hints.${reason}`)} {help}</p>
        {hasRelated && (
          <label className="checkbox-line" htmlFor="revoke-related">
            <input type="checkbox" id="revoke-related" checked={revokeRelated} onChange={(e) => setRevokeRelated(e.target.checked)} aria-describedby="revoke-related-hint" />
            <span>{t('revocation.revokeRelated')}<small id="revoke-related-hint" className="muted" style={{ display: 'block' }}>{t('revocation.revokeRelatedHint')}</small></span>
          </label>
        )}
        <div className="modal-actions">
          <button type="button" className="btn" data-action="close-modal" onClick={onClose} disabled={loading || undefined}>{t('common.cancel')}</button>
          <button type="button" className="btn danger" data-write="" data-confirm-revoke={certId} disabled={loading || checking || undefined} onClick={submit}>{t('revocation.confirm')}</button>
        </div>
      </>
    </AtelierDialog>
  )
}

export default RevokeDialog
