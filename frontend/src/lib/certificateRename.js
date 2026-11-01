import { certificatesService } from '../services'

/**
 * Asks for a certificate's display name (#286) and saves it. Resolves to the
 * updated certificate, or null when cancelled, unchanged or refused.
 */
export async function renameCertificate(cert, { showPrompt, showSuccess, showError, t }) {
  const answer = await showPrompt(t('certificates.renamePrompt'), {
    title: t('certificates.renameCertificate'),
    defaultValue: cert.descr || cert.cn || cert.common_name || '',
    confirmText: t('common.save'),
  })
  const name = typeof answer === 'string' ? answer.trim() : ''
  if (!name || name === cert.descr) return null
  try {
    const res = await certificatesService.rename(cert.id, name)
    showSuccess(t('certificates.renameSuccess'))
    return res?.data ?? { ...cert, descr: name }
  } catch (error) {
    showError(error?.message || t('certificates.renameFailed'))
    return null
  }
}
