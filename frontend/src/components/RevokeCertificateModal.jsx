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

  // The server revokes the other member only when it names this one back and is not revoked yet
  useEffect(() => {
    if (!open || relatedId == null) { setRelated('none'); return undefined }
    let live = true
    setRelated('loading')
    certificatesService.getById(relatedId)
      .then((res) => {
        const other = res?.data ?? res
        if (live) setRelated(other && other.related_certificate_id === certId && !other.revoked ? 'revocable' : 'none')
      })
      .catch(() => { if (live) setRelated('unknown') })
    return () => { live = false }
  }, [open, relatedId, certId])
  const checking = related === 'loading'

  const name = certificate?.name || certificate?.common_name || certificate?.cn || certificate?.descr || ''

  return (
    <Modal open={open} onClose={onClose} title={title || t('revocation.title')} size="sm">
      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (loading || checking) return
          if (hasRelated) onConfirm(reason, { revokeRelated })
          else onConfirm(reason)
        }}
        className="p-4 space-y-4"
        data-testid="revoke-form"
      >
        <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-bg-secondary text-sm text-text-secondary">
          <Warning size={16} className="mt-0.5 shrink-0 text-status-warning" />
          <div className="space-y-1">
            {name && <div className="font-medium text-text-primary truncate">{name}</div>}
            <div>{warning || t('certificates.revokeWarning')}</div>
            {certificate?.source === 'msca' && <div>{t('certificates.revokeMscaWarning')}</div>}
          </div>
        </div>

        <div className="space-y-1.5">
          <label htmlFor="revoke-reason" className="text-xs font-medium text-text-secondary uppercase tracking-wide">
            {t('revocation.reasonLabel')}
          </label>
          <select
            id="revoke-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="w-full px-3 py-2 rounded-lg border border-border bg-bg-primary text-sm text-text-primary"
            data-testid="revoke-reason"
          >
            {REVOCATION_REASONS.filter(r => allowHold || r !== 'certificateHold').map(r => (
              <option key={r} value={r}>{t(`revocation.reasons.${r}`)}</option>
            ))}
          </select>
          <p className="text-xs text-text-tertiary">{t(`revocation.hints.${reason}`)}</p>
          <p className="text-xs text-text-tertiary">
            {count > 1 ? t('revocation.bulkReasonHelp') : (allowHold ? t('revocation.reasonHelp') : t('revocation.reasonHelpNoHold'))}
          </p>
        </div>

        {/* Other member of a hybrid pair (RFC 9763): revoked too unless unchecked */}
        {hasRelated && (
          <div className="flex items-start gap-2.5">
            <input
              type="checkbox"
              id="revoke-related"
              checked={revokeRelated}
              onChange={(e) => setRevokeRelated(e.target.checked)}
              className="w-4 h-4 mt-0.5 rounded accent-accent-primary"
            />
            <div>
              <label htmlFor="revoke-related" className="text-sm text-text-primary cursor-pointer">
                {t('revocation.revokeRelated')}
              </label>
              <p className="text-xs text-text-tertiary">{t('revocation.revokeRelatedHint')}</p>
            </div>
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2 border-t border-border">
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
