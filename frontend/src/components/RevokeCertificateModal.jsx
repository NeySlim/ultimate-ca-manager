/**
 * RevokeCertificateModal — revocation confirm dialog with the RFC 5280 reason.
 *
 * The plain confirm dialog it replaces recorded every manual revocation as
 * `unspecified` (#334). The reason is a per-revocation choice, defaulting to
 * unspecified, with a one-line explanation of the selected code; revocation
 * is one-way (except a certificate hold), so the choice cannot be redone.
 *
 * Props: open, onClose, onConfirm(reason[, { revokeRelated }]), certificate ({ id, name, source,
 * related_certificate_id: the pair question is asked when the other member names this one back
 * and is still valid }), loading, count (bulk: number of certificates the reason applies to),
 * title / warning (overrides, used when revoking an intermediate CA, #343).
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Warning } from '@phosphor-icons/react'
import { Modal } from './Modal'
import { Button } from './Button'
import { certificatesService } from '../services'
import './certificateDialogs.css'

export const REVOCATION_REASONS = [
  'unspecified',
  'keyCompromise',
  'cACompromise',
  'affiliationChanged',
  'superseded',
  'cessationOfOperation',
  'certificateHold',
  'privilegeWithdrawn',
  'aACompromise',
]

export function RevokeCertificateModal({ open, onClose, onConfirm, certificate, loading = false, count = 1, title, warning, allowHold = true }) {
  const { t } = useTranslation()
  const [reason, setReason] = useState('unspecified')
  const [revokeRelated, setRevokeRelated] = useState(true)
  // 'loading' | 'revocable' | 'none' | 'unknown' (lookup failed: the server decides)
  const [related, setRelated] = useState('none')
  const relatedId = certificate?.related_certificate_id ?? null
  const certId = certificate?.id
  const hasRelated = related === 'revocable' || related === 'unknown'

  // A fresh choice for every revocation
  useEffect(() => {
    if (open) {
      setReason('unspecified')
      setRevokeRelated(true)
    }
  }, [open])

  // The server revokes the other member only when it names this one back and is neither revoked nor superseded
  useEffect(() => {
    if (!open || relatedId == null) { setRelated('none'); return undefined }
    let live = true
    setRelated('loading')
    certificatesService.getById(relatedId)
      .then((res) => {
        const other = res?.data ?? res
        if (live) setRelated(other && other.related_certificate_id === certId && !other.revoked && !other.archived ? 'revocable' : 'none')
      })
      .catch(() => { if (live) setRelated('unknown') })
    return () => { live = false }
  }, [open, relatedId, certId])
  const checking = related === 'loading'

  const name = certificate?.name || certificate?.common_name || certificate?.cn || certificate?.descr || ''

  // The reason's hint and what the choice commits to, in one muted note as the mockup
  const help = count > 1 ? t('revocation.bulkReasonHelp') : (allowHold ? t('revocation.reasonHelp') : t('revocation.reasonHelpNoHold'))

  return (
    <Modal open={open} onClose={onClose} title={title || t('revocation.dialogTitle')} size="sm" className="ui-revoke-dialog">
      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (loading || checking) return
          if (hasRelated) onConfirm(reason, { revokeRelated })
          else onConfirm(reason)
        }}
        data-testid="revoke-form"
      >
        <div className="ui-notice is-warn">
          <Warning size={14} aria-hidden="true" />
          <div className="ui-notice-body">
            <p>{warning || t('revocation.notice')}</p>
            {certificate?.source === 'msca' && <p>{t('certificates.revokeMscaWarning')}</p>}
          </div>
        </div>
        {name && <p className="ui-revoke-name">{name}</p>}

        <div className="ui-field">
          <label htmlFor="revoke-reason" className="ui-label">{t('revocation.reason')}</label>
          <select
            id="revoke-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="ui-control"
            data-testid="revoke-reason"
          >
            {REVOCATION_REASONS.filter(r => allowHold || r !== 'certificateHold').map(r => (
              <option key={r} value={r}>{t(`revocation.reasons.${r}`)}</option>
            ))}
          </select>
        </div>
        <p className="ui-revoke-note">
          <span>{t(`revocation.hints.${reason}`)}</span> <span>{help}</span>
        </p>

        {/* Other member of a hybrid pair (RFC 9763): revoked too unless unchecked */}
        {hasRelated && (
          <label className="ui-check-line has-desc" htmlFor="revoke-related">
            <input type="checkbox" id="revoke-related" checked={revokeRelated} onChange={(e) => setRevokeRelated(e.target.checked)}
              aria-labelledby="revoke-related-label" aria-describedby="revoke-related-hint" />
            <span className="ui-check-text">
              <span id="revoke-related-label">{t('revocation.revokeRelated')}</span>
              <small id="revoke-related-hint">{t('revocation.revokeRelatedHint')}</small>
            </span>
          </label>
        )}

        <div className="ui-dialog-actions">
          <Button type="button" variant="secondary" onClick={onClose} disabled={loading}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" variant="danger" loading={loading || checking} disabled={loading || checking}>
            {t('revocation.confirm')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

export default RevokeCertificateModal
