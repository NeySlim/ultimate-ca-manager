import { useState } from 'react'
import { UploadSimple } from '@phosphor-icons/react'
import { Modal, Button, Input, Textarea } from '..'
import { casService } from '../../services'
import { useNotification } from '../../contexts'

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

  return (
    <Modal open={open} onOpenChange={(isOpen) => { if (!isOpen) handleClose() }} title={t('cas.importPrivateKey')}>
      <div className="p-4 space-y-4">
        <p className="text-sm text-text-secondary">
          {t('cas.importPrivateKey')} <strong>{ca?.common_name || ca?.descr}</strong>
        </p>
        <Textarea
          label={t('common.privateKeyPEM')}
          value={keyPem}
          onChange={(e) => setKeyPem(e.target.value)}
          placeholder={`-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQE...\n-----END PRIVATE KEY-----`}
          rows={8}
          className="font-mono text-xs"
        />
        <Input
          label={t('common.password')}
          type="password"
          noAutofill
          value={passphrase}
          onChange={(e) => setPassphrase(e.target.value)}
          placeholder={t('common.optional')}
        />
        <div className="flex justify-end gap-2 pt-2 border-t border-border">
          <Button type="button" variant="secondary" onClick={handleClose}>{t('common.cancel')}</Button>
          <Button type="button" onClick={handleUpload} disabled={busy || !keyPem.trim()}>
            <UploadSimple size={16} /> {t('common.upload')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
