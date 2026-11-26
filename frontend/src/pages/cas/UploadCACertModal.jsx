/**
 * UploadCACertModal — install the externally signed certificate on an
 * external-CSR CA (#298). Accepts pasted PEM or an uploaded file (PEM/DER).
 * Serves both the first activation of a pending CA and same-key renewals.
 */
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AtelierDialog, Icon } from '../../components/atelier'
import { casService } from '../../services'
import { useNotification } from '../../contexts'
import { extractData, formatDate } from '../../lib/utils'
import { crossAttachOffered, crossReplaceOffered } from '../../lib/crossCertificates'

const MAX_FILE_SIZE = 256 * 1024

export function UploadCACertModal(props) {
  if (!props.open) return null
  return <UploadBody {...props} />
}

// The mockup's modal(): the notice, the PEM, the file, the cross-certificate offer, Annuler and the primary install
function UploadBody({ onClose, ca, onSuccess }) {
  const { t } = useTranslation()
  const { showSuccess, showError, showWarning } = useNotification()

  const [pemContent, setPemContent] = useState('')
  const [certFile, setCertFile] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  // The certificate re-certifies this CA's key: offered as a cross-certificate instead (#400)
  const [crossOffer, setCrossOffer] = useState(null) // { message, attach, replace }

  const fileTooLarge = certFile && certFile.size > MAX_FILE_SIZE
  const canSubmit = !submitting && !fileTooLarge && (certFile || pemContent.trim().length > 0)

  const reset = () => {
    setPemContent('')
    setCertFile(null)
    setSubmitting(false)
    setCrossOffer(null)
  }

  const handleClose = () => {
    if (submitting) return
    reset()
    onClose?.()
  }

  const install = async (crossMode) => {
    setSubmitting(true)
    try {
      const response = await casService.uploadCertificate(ca.id, {
        pemContent: certFile ? undefined : pemContent.trim(),
        file: certFile || undefined,
        crossMode,
      })
      const data = extractData(response) || {}
      showSuccess(t('cas.certInstalled'))
      if (data.superseded_serial) {
        const notice = t('cas.certSupersededNotice', {
          serial: data.superseded_serial,
          date: data.superseded_valid_to
            ? formatDate(data.superseded_valid_to, { time: false })
            : '?',
        })
        showWarning ? showWarning(notice) : showError(notice)
      }
      for (const w of data.warnings || []) {
        showWarning ? showWarning(w) : showError(w)
      }
      window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type: 'ca' } }))
      onSuccess?.()
      reset()
      onClose?.()
    } catch (err) {
      if (crossAttachOffered(err) || crossReplaceOffered(err)) {
        setCrossOffer({
          message: err.message,
          attach: crossAttachOffered(err),
          replace: crossReplaceOffered(err),
        })
      } else showError(err?.message || t('cas.certInstallFailed'))
      setSubmitting(false)
    }
  }

  const handleSubmit = (e) => {
    e?.preventDefault?.()
    if (canSubmit) install()
  }

  const handleAttachCross = async () => {
    setSubmitting(true)
    try {
      const fd = new FormData()
      if (certFile) fd.append('file', certFile)
      else fd.append('pem_content', pemContent.trim())
      fd.append('cross_mode', 'attach')
      fd.append('import_key', 'false')
      const data = extractData(await casService.import(fd)) || {}
      showSuccess(t('crossCerts.attached'))
      for (const w of data.warnings || []) showWarning(w)
      window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type: 'ca' } }))
      onSuccess?.()
      reset()
      onClose?.()
    } catch (err) {
      showError(err?.message || t('crossCerts.attachFailed'))
      setSubmitting(false)
    }
  }

  const title = useMemo(
    () => `${t('cas.uploadCertTitle')}: ${ca?.common_name || ca?.descr || `CA #${ca?.id}`}`,
    [t, ca]
  )

  return (
    <AtelierDialog title={title} size="narrow" onClose={handleClose} testId="upload-ca-cert-dialog">
      <form onSubmit={handleSubmit}>
        <p className="notice"><Icon name="cert" /><span>{t('cas.uploadCertHint')}</span></p>
        <div className="form-fields">
          <div className="field full">
            <label htmlFor="ucm-ca-cert-pem">{t('cas.uploadCertPaste')}</label>
            <textarea id="ucm-ca-cert-pem" className="mono" rows={6} spellCheck={false} placeholder="-----BEGIN CERTIFICATE-----" value={pemContent}
              onChange={(e) => { setPemContent(e.target.value); if (e.target.value) setCertFile(null) }} />
          </div>
          <div className="field full">
            <label htmlFor="ucm-ca-cert-file">{t('cas.uploadCertPick')}</label>
            <input id="ucm-ca-cert-file" type="file" accept=".pem,.crt,.cer,.der,application/x-pem-file,application/x-x509-ca-cert"
              onChange={(e) => {
                const f = e.target.files?.[0] || null
                setCertFile(f)
                if (f) setPemContent('')
              }} />
            {fileTooLarge && <p className="field-error"><Icon name="warning" /><span>{t('cas.uploadCertTooLarge')}</span></p>}
          </div>
          {crossOffer && (
            <div className="field full" data-testid="cross-offer">
              <div className="notice warn" style={{ marginBottom: 0 }}><Icon name="warning" />
                <span>
                  <span>{crossOffer.message}</span>
                  {crossOffer.attach && <span> {t('crossCerts.offerHint')}</span>}
                  {crossOffer.replace && <span> {t('crossCerts.replaceHint')}</span>}
                </span>
              </div>
              <div className="actions">
                {crossOffer.attach && (
                  <button type="button" className="btn primary" data-write="" disabled={submitting || undefined} onClick={handleAttachCross}>{t('crossCerts.attachAsCross')}</button>
                )}
                {crossOffer.replace && (
                  <button type="button" className="btn" data-write="" disabled={submitting || undefined} onClick={() => install('replace')}>{t('crossCerts.replaceCurrent')}</button>
                )}
              </div>
            </div>
          )}
        </div>
        <div className="modal-actions">
          <button type="button" className="btn" onClick={handleClose} disabled={submitting || undefined}>{t('common.cancel')}</button>
          <button type="submit" className="btn primary" disabled={!canSubmit || undefined}>{submitting ? t('common.loading') : t('cas.uploadCertificate')}</button>
        </div>
      </form>
    </AtelierDialog>
  )
}
