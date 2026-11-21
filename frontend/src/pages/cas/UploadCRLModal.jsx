/**
 * UploadCRLModal — install an externally-generated CRL on a key-less/offline
 * CA (#302). The CRL is signed next to the offline key, validated here
 * (issuer, signature, monotonicity) and served at the CA's CDP endpoint.
 * Accepts pasted PEM or an uploaded file (PEM/DER).
 */
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { casService } from '../../services'
import { useNotification } from '../../contexts'
import { AtelierDialog, Icon } from '../../components/atelier'

const MAX_FILE_SIZE = 5 * 1024 * 1024

export function UploadCRLModal({ open, onClose, ca, onSuccess }) {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()

  const [pemContent, setPemContent] = useState('')
  const [crlFile, setCrlFile] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  const fileTooLarge = crlFile && crlFile.size > MAX_FILE_SIZE
  const canSubmit = !submitting && !fileTooLarge && (crlFile || pemContent.trim().length > 0)

  const reset = () => {
    setPemContent('')
    setCrlFile(null)
    setSubmitting(false)
  }

  const handleClose = () => {
    if (submitting) return
    reset()
    onClose?.()
  }

  const handleSubmit = async (e) => {
    e?.preventDefault?.()
    if (!canSubmit) return
    setSubmitting(true)
    try {
      await casService.uploadCrl(ca.id, {
        pemContent: crlFile ? undefined : pemContent.trim(),
        file: crlFile || undefined,
      })
      showSuccess(t('cas.crlInstalled'))
      window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type: 'ca' } }))
      onSuccess?.()
      reset()
      onClose?.()
    } catch (err) {
      showError(err?.message || t('cas.crlInstallFailed'))
      setSubmitting(false)
    }
  }

  const title = useMemo(
    () => `${t('cas.uploadCrlTitle')}: ${ca?.common_name || ca?.descr || `CA #${ca?.id}`}`,
    [t, ca]
  )

  if (!open) return null
  return (
    <AtelierDialog title={title} size="narrow" onClose={handleClose} testId="upload-crl-dialog">
      <form onSubmit={handleSubmit}>
        <p className="notice"><Icon name="crl" /><span>{t('cas.uploadCrlHint')}</span></p>
        <div className="form-fields">
          <div className="field full">
            <label htmlFor="ucm-ca-crl-pem">{t('cas.uploadCrlPaste')}</label>
            <textarea id="ucm-ca-crl-pem" className="mono" rows={6} spellCheck={false} placeholder="-----BEGIN X509 CRL-----" value={pemContent}
              onChange={(e) => { setPemContent(e.target.value); if (e.target.value) setCrlFile(null) }} />
          </div>
          <div className="field full">
            <label htmlFor="ucm-ca-crl-file">{t('cas.uploadCrlPick')}</label>
            <input id="ucm-ca-crl-file" type="file" accept=".crl,.pem,.der,application/pkix-crl,application/x-pem-file"
              onChange={(e) => {
                const f = e.target.files?.[0] || null
                setCrlFile(f)
                if (f) setPemContent('')
              }} />
            {fileTooLarge && <p className="field-error"><Icon name="warning" /><span>{t('cas.uploadCrlTooLarge')}</span></p>}
          </div>
        </div>
        <div className="modal-actions">
          <button type="button" className="btn" onClick={handleClose} disabled={submitting}>{t('common.cancel')}</button>
          <button type="submit" className="btn primary" data-write="" disabled={!canSubmit}>{t('cas.uploadCrl')}</button>
        </div>
      </form>
    </AtelierDialog>
  )
}
