/**
 * UploadCACertModal — install the externally signed certificate on an
 * external-CSR CA (#298). Accepts pasted PEM or an uploaded file (PEM/DER).
 * Serves both the first activation of a pending CA and same-key renewals.
 */
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Certificate, UploadSimple, Warning } from '@phosphor-icons/react'
import { Modal } from '../../components/Modal'
import { Button } from '../../components/Button'
import { casService } from '../../services'
import { useNotification } from '../../contexts'
import { extractData } from '../../lib/utils'
import { crossAttachOffered, crossReplaceOffered } from '../../lib/crossCertificates'

const MAX_FILE_SIZE = 256 * 1024

export function UploadCACertModal({ open, onClose, ca, onSuccess }) {
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
            ? new Date(data.superseded_valid_to).toLocaleDateString()
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
    <Modal open={open} onOpenChange={(v) => !v && handleClose()} title={title} size="md">
      <form onSubmit={handleSubmit} className="p-4 space-y-4">
        <div className="flex items-start gap-3 p-3 rounded-md bg-accent-primary-op10 border border-accent-primary-op30">
          <Certificate size={20} className="text-accent-primary shrink-0 mt-0.5" />
          <p className="text-xs text-text-secondary">{t('cas.uploadCertHint')}</p>
        </div>

        <div className="space-y-1.5">
          <label className="block text-xs font-medium text-text-secondary">
            {t('cas.uploadCertPaste')}
          </label>
          <textarea
            className="w-full h-36 px-3 py-2 bg-bg-tertiary border border-border rounded-md text-xs font-mono text-text-primary resize-y focus:outline-none focus:border-accent-primary"
            placeholder="-----BEGIN CERTIFICATE-----"
            value={pemContent}
            onChange={(e) => { setPemContent(e.target.value); if (e.target.value) setCertFile(null) }}
            spellCheck={false}
          />
        </div>

        <div className="space-y-1.5">
          <label
            htmlFor="ucm-ca-cert-file"
            className="flex items-center gap-2 px-3 py-2 bg-bg-tertiary border border-border rounded-md cursor-pointer hover:border-text-tertiary transition-colors"
          >
            <UploadSimple size={16} className="text-text-tertiary" />
            <span className="text-sm text-text-primary truncate">
              {certFile ? certFile.name : t('cas.uploadCertPick')}
            </span>
          </label>
          <input
            id="ucm-ca-cert-file"
            type="file"
            accept=".pem,.crt,.cer,.der,application/x-pem-file,application/x-x509-ca-cert"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0] || null
              setCertFile(f)
              if (f) setPemContent('')
            }}
          />
          {fileTooLarge && (
            <p className="text-xs status-danger-text flex items-center gap-1">
              <Warning size={12} /> {t('cas.uploadCertTooLarge')}
            </p>
          )}
        </div>

        {crossOffer && (
          <div className="p-3 rounded-md bg-status-warning-op15 border border-status-warning-op40 space-y-2"
               data-testid="cross-offer">
            <p className="text-xs text-text-secondary">{crossOffer.message}</p>
            {crossOffer.attach && <p className="text-xs text-text-secondary">{t('crossCerts.offerHint')}</p>}
            {crossOffer.replace && <p className="text-xs text-text-secondary">{t('crossCerts.replaceHint')}</p>}
            <div className="flex gap-2">
              {crossOffer.attach && (
                <Button type="button" size="xs" variant="primary" onClick={handleAttachCross} loading={submitting}>
                  {t('crossCerts.attachAsCross')}
                </Button>
              )}
              {crossOffer.replace && (
                <Button type="button" size="xs" variant="secondary" onClick={() => install('replace')}
                        disabled={submitting}>
                  {t('crossCerts.replaceCurrent')}
                </Button>
              )}
            </div>
          </div>
        )}

        <div className="flex justify-end gap-2 pt-3 border-t border-border">
          <Button type="button" variant="secondary" onClick={handleClose} disabled={submitting}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" variant="primary" loading={submitting} disabled={!canSubmit}>
            {t('cas.uploadCertificate')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
