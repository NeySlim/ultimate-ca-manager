/**
 * RestorePrimaryModal — put a self-signed certificate back on a CA record that
 * only holds a cross-certificate of its key (#400). The replaced certificate is
 * kept as a cross-certificate.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AtelierDialog, Icon } from '../atelier'
import { casService } from '../../services'
import { useNotification } from '../../contexts'
import { extractData } from '../../lib/utils'
import { certificateFileToPem } from '../../lib/crossCertificates'

export function RestorePrimaryModal(props) {
  if (!props.open) return null
  return <RestoreBody {...props} />
}

// The mockup's modal(): the hint, the PEM or a file, Annuler and the primary restore; not closed while it runs
function RestoreBody({ onClose, ca, onDone }) {
  const { t } = useTranslation()
  const { showSuccess, showError, showWarning } = useNotification()
  const [pem, setPem] = useState('')
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e?.preventDefault?.()
    setBusy(true)
    try {
      const certificate = file ? await certificateFileToPem(file) : pem.trim()
      const res = await casService.restorePrimary(ca.id, certificate)
      for (const w of extractData(res)?.warnings || []) showWarning(w)
      showSuccess(t('crossCerts.restored'))
      onDone?.()
      onClose()
    } catch (err) {
      showError(err?.message || t('crossCerts.restoreFailed'))
      setBusy(false)
    }
  }
  const close = () => { if (!busy) onClose() }

  return (
    <AtelierDialog title={`${t('crossCerts.restorePrimary')}: ${ca?.name || ca?.descr || ''}`} size="narrow" onClose={close} testId="restore-primary-dialog">
      <form onSubmit={submit}>
        <p className="notice"><Icon name="cert" /><span>{t('crossCerts.restoreHint')}</span></p>
        <div className="form-fields">
          <div className="field full">
            <label htmlFor="ucm-restore-primary-pem">{t('cas.uploadCertPaste')}</label>
            <textarea id="ucm-restore-primary-pem" className="mono" rows={6} spellCheck={false} placeholder="-----BEGIN CERTIFICATE-----" value={pem}
              onChange={(e) => { setPem(e.target.value); if (e.target.value) setFile(null) }} />
          </div>
          <div className="field full">
            <label htmlFor="ucm-restore-primary-file">{t('cas.uploadCertPick')}</label>
            <input id="ucm-restore-primary-file" type="file" accept=".pem,.crt,.cer,.der"
              onChange={(e) => { const f = e.target.files?.[0] || null; setFile(f); if (f) setPem('') }} />
          </div>
        </div>
        <div className="modal-actions">
          <button type="button" className="btn" onClick={close} disabled={busy || undefined}>{t('common.cancel')}</button>
          <button type="submit" className="btn primary" disabled={busy || (!pem.trim() && !file) || undefined}>{busy ? t('common.loading') : t('crossCerts.restorePrimary')}</button>
        </div>
      </form>
    </AtelierDialog>
  )
}
