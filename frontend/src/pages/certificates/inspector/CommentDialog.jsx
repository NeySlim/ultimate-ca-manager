/**
 * The comment of a certificate (#454) in the product's dialog: a multiline field with its counter,
 * then Annuler and Enregistrer. The server keeps line feeds and tabs; an empty text removes it.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AtelierDialog, Btn, Notice, Textarea } from '../../../components/atelier'
// The modules themselves, not the barrels: the overview panel stays free of the auth context
import { useNotification } from '../../../contexts/NotificationContext'
import { certificatesService } from '../../../services/certificates.service'

export const COMMENT_MAX = 4000

export function CommentDialog({ cert, onClose, onSaved, returnTo }) {
  const { t } = useTranslation()
  const { showSuccess } = useNotification()
  const [text, setText] = useState(cert.comment || '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const save = async (event) => {
    event.preventDefault()
    if (saving) return
    setSaving(true)
    setError('')
    try {
      const res = await certificatesService.updateComment(cert.id, text)
      showSuccess(t('certificates.commentSaved'))
      onSaved(res?.data ?? { ...cert, comment: text })
    } catch (err) {
      setError(err?.message || t('certificates.commentFailed'))
      setSaving(false)
    }
  }

  return (
    <AtelierDialog size="narrow" title={t('certificates.editComment')} onClose={() => { if (!saving) onClose() }} returnTo={returnTo}>
      <form onSubmit={save}>
        <div className="form-fields">
          <Textarea id={`cert-comment-${cert.id}`} label={t('certificates.comment')} value={text} rows={6} maxLength={COMMENT_MAX}
            data-autofocus disabled={saving} onChange={(e) => setText(e.target.value)}
            hint={`${t('certificates.commentHint')} ${t('certificates.commentCount', { length: text.length, max: COMMENT_MAX })}`} />
          {error && <Notice tone="bad">{error}</Notice>}
        </div>
        <div className="modal-actions">
          <Btn onClick={onClose} disabled={saving}>{t('common.cancel')}</Btn>
          <Btn tone="primary" icon="check" type="submit" disabled={saving}>{t('common.save')}</Btn>
        </div>
      </form>
    </AtelierDialog>
  )
}
