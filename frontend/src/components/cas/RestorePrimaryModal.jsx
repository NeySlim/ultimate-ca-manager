/**
 * RestorePrimaryModal — put a self-signed certificate back on a CA record that
 * only holds a cross-certificate of its key (#400). The replaced certificate is
 * kept as a cross-certificate.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { UploadSimple } from '@phosphor-icons/react'
import { Modal } from '../Modal'
import { Button } from '../Button'
import { casService } from '../../services'
import { useNotification } from '../../contexts'
import { extractData } from '../../lib/utils'
import { certificateFileToPem } from '../../lib/crossCertificates'

export function RestorePrimaryModal({ open, onClose, ca, onDone }) {
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
      setPem(''); setFile(null)
      onDone?.()
      onClose()
    } catch (err) {
      showError(err?.message || t('crossCerts.restoreFailed'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open={open} onOpenChange={(v) => !v && !busy && onClose()}
           title={`${t('crossCerts.restorePrimary')}: ${ca?.name || ca?.descr || ''}`} size="md">
      <form onSubmit={submit} className="p-4 space-y-3">
        <p className="text-xs text-text-secondary">{t('crossCerts.restoreHint')}</p>
        <textarea className="w-full h-32 px-3 py-2 bg-bg-tertiary border border-border rounded-md text-xs font-mono text-text-primary resize-y focus:outline-none focus:border-accent-primary"
                  spellCheck={false} placeholder="-----BEGIN CERTIFICATE-----" value={pem}
                  onChange={(e) => { setPem(e.target.value); if (e.target.value) setFile(null) }} />
        <label className="flex items-center gap-2 px-3 py-2 bg-bg-tertiary border border-border rounded-md cursor-pointer">
          <UploadSimple size={16} className="text-text-tertiary" />
          <span className="text-sm text-text-primary truncate">{file ? file.name : t('cas.uploadCertPick')}</span>
          <input type="file" className="hidden" accept=".pem,.crt,.cer,.der"
                 onChange={(e) => { const f = e.target.files?.[0] || null; setFile(f); if (f) setPem('') }} />
        </label>
        <div className="flex justify-end gap-2 pt-3 border-t border-border">
          <Button type="button" variant="secondary" onClick={onClose} disabled={busy}>{t('common.cancel')}</Button>
          <Button type="submit" variant="primary" loading={busy} disabled={!pem.trim() && !file}>
            {t('crossCerts.restorePrimary')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
