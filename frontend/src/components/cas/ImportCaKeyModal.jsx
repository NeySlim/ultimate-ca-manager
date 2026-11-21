import { useState } from 'react'
import { casService } from '../../services'
import { useNotification } from '../../contexts'
import { AtelierDialog, Icon } from '../atelier'

/** Attach the private key of a CA that holds only its certificate (#348). */
export function ImportCaKeyModal({ open, onClose, ca, onSuccess, t }) {
  const [keyPem, setKeyPem] = useState('')
  const [passphrase, setPassphrase] = useState('')
  const [busy, setBusy] = useState(false)
  const { showSuccess, showError } = useNotification()

  const handleClose = () => {
    setKeyPem('')
    setPassphrase('')
    onClose()
  }

  const handleUpload = async () => {
    if (!keyPem.trim()) {
      showError(t('validation.required'))
      return
    }
    if (!keyPem.includes('PRIVATE KEY')) {
      showError(t('validation.invalidFormat'))
      return
    }
    setBusy(true)
    try {
      const response = await casService.uploadKey(ca.id, keyPem.trim(), passphrase || null)
      showSuccess(t('messages.success.other.keyUploaded'))
      setKeyPem('')
      setPassphrase('')
      onSuccess?.(response?.data || response)
      onClose()
    } catch (error) {
      showError(error.message || t('common.operationFailed'))
    } finally {
      setBusy(false)
    }
  }

  if (!open) return null
  return (
    <AtelierDialog title={t('cas.importPrivateKey')} size="narrow" onClose={handleClose} testId="import-ca-key-dialog">
      <p className="small muted" style={{ marginBottom: 20 }}>{ca?.common_name || ca?.descr}</p>
      <div className="form-fields">
        <div className="field full">
          <label htmlFor="ca-key-pem">{t('common.privateKeyPEM')}</label>
          <textarea id="ca-key-pem" className="mono" rows={8} spellCheck={false} value={keyPem} data-autofocus=""
            placeholder={`-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQE...\n-----END PRIVATE KEY-----`}
            onChange={(e) => setKeyPem(e.target.value)} />
        </div>
        <div className="field full">
          <label htmlFor="ca-key-passphrase">{t('common.password')} <span className="optional">{t('common.optional')}</span></label>
          <input id="ca-key-passphrase" type="password" autoComplete="off" value={passphrase} onChange={(e) => setPassphrase(e.target.value)} />
        </div>
      </div>
      <div className="modal-actions">
        <button type="button" className="btn" onClick={handleClose}>{t('common.cancel')}</button>
        <button type="button" className="btn primary" data-write="" onClick={handleUpload} disabled={busy || !keyPem.trim()}>
          <Icon name="upload" />{t('common.upload')}
        </button>
      </div>
    </AtelierDialog>
  )
}
