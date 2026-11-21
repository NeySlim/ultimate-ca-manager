import { useRef, useState } from 'react'
import { certificatesService } from '../../services'
import { useNotification } from '../../contexts'
import { AtelierDialog, Icon } from '../../components/atelier'
import { Textarea, SecretInput } from '../../components/atelier/Form'

/** Add the private key of a certificate, in the mockup's modal(): the PEM, its password, Annuler and Téléverser. */
export function UploadKeyModal({ open, onOpenChange, selectedCert, onUploadComplete, t }) {
  if (!open) return null
  return <UploadKeyBody onOpenChange={onOpenChange} selectedCert={selectedCert} onUploadComplete={onUploadComplete} t={t} />
}

function UploadKeyBody({ onOpenChange, selectedCert, onUploadComplete, t }) {
  const [keyPem, setKeyPem] = useState('')
  const [keyPassphrase, setKeyPassphrase] = useState('')
  const inFlight = useRef(false)
  const { showSuccess, showError } = useNotification()
  const close = () => onOpenChange(false)

  const handleUpload = async (e) => {
    e?.preventDefault?.()
    if (inFlight.current) return
    if (!keyPem.trim()) {
      showError(t('validation.required'))
      return
    }
    if (!keyPem.includes('PRIVATE KEY')) {
      showError(t('validation.invalidFormat'))
      return
    }
    inFlight.current = true
    try {
      await certificatesService.uploadKey(selectedCert.id, keyPem.trim(), keyPassphrase || null)
      showSuccess(t('messages.success.other.keyUploaded'))
      const updated = await certificatesService.getById(selectedCert.id)
      onUploadComplete(updated.data || updated)
      onOpenChange(false)
    } catch (error) {
      showError(error.message || t('common.operationFailed'))
    } finally {
      inFlight.current = false
    }
  }

  return (
    <AtelierDialog title={t('common.upload')} subtitle={selectedCert?.cn || selectedCert?.common_name} size="narrow" onClose={close} testId="upload-key-dialog">
      <form onSubmit={handleUpload} noValidate>
        <div className="form-fields">
          <Textarea id="upload-key-pem" label={t('common.privateKeyPEM')} mono rows={8} value={keyPem} onChange={(e) => setKeyPem(e.target.value)} data-autofocus=""
            spellCheck={false} placeholder={'-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQE...\n-----END PRIVATE KEY-----'} />
          <SecretInput id="upload-key-password" label={t('common.password')} full value={keyPassphrase} onChange={(e) => setKeyPassphrase(e.target.value)}
            placeholder={t('common.optional')} />
        </div>
        <div className="modal-actions">
          <button type="button" className="btn" data-action="close-modal" onClick={close}>{t('common.cancel')}</button>
          <button type="submit" className="btn primary" disabled={!keyPem.trim() || undefined}><Icon name="upload" />{t('common.upload')}</button>
        </div>
      </form>
    </AtelierDialog>
  )
}
