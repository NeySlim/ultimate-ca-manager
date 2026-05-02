import { useState } from 'react'
import { UploadSimple } from '@phosphor-icons/react'
import { Modal, Button, Input, Textarea } from '../../components'
import { certificatesService } from '../../services'
import { useNotification } from '../../contexts'

export function UploadKeyModal({ open, onOpenChange, selectedCert, onUploadComplete, t }) {
  const [keyPem, setKeyPem] = useState('')
  const [keyPassphrase, setKeyPassphrase] = useState('')
  const { showSuccess, showError } = useNotification()

  const handleClose = () => {
    setKeyPem('')
    setKeyPassphrase('')
    onOpenChange(false)
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
    try {
      await certificatesService.uploadKey(selectedCert.id, keyPem.trim(), keyPassphrase || null)
      showSuccess(t('messages.success.other.keyUploaded'))
      const updated = await certificatesService.getById(selectedCert.id)
      setKeyPem('')
      setKeyPassphrase('')
      onUploadComplete(updated.data || updated)
      onOpenChange(false)
    } catch (error) {
      showError(error.message || t('common.operationFailed'))
    }
  }

  return (
    <Modal
      open={open}
      onOpenChange={(isOpen) => { if (!isOpen) handleClose() }}
      title={t('common.upload')}
    >
      <div className="p-4 space-y-4">
        <p className="text-sm text-text-secondary">
          {t('common.upload')} <strong>{selectedCert?.cn || selectedCert?.common_name}</strong>
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
          value={keyPassphrase}
          onChange={(e) => setKeyPassphrase(e.target.value)}
          placeholder={t('common.optional')}
        />
        <div className="flex justify-end gap-2 pt-2 border-t border-border">
          <Button type="button" variant="secondary" onClick={handleClose}>
            {t('common.cancel')}
          </Button>
          <Button type="button" onClick={handleUpload} disabled={!keyPem.trim()}>
            <UploadSimple size={16} /> {t('common.upload')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
