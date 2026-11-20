/** PEM of a certificate, with a copy button. */
import { useTranslation } from 'react-i18next'
import { Copy, CheckCircle } from '@phosphor-icons/react'
import { useClipboard } from '../../../hooks/useClipboard'

export function CertificatePem({ cert }) {
  const { t } = useTranslation()
  const { copy, isCopied } = useClipboard()
  if (!cert.pem) return <p className="ins-muted">{t('inspector.cert.noPem')}</p>
  const copied = isCopied('pem')
  return (
    <div>
      <pre className="ins-pem ins-mono" data-testid="certificate-pem">{cert.pem}</pre>
      <button type="button" className="lv-btn" onClick={() => copy(cert.pem, 'pem')}>
        {copied ? <CheckCircle size={14} aria-hidden="true" /> : <Copy size={14} aria-hidden="true" />}
        {copied ? t('common.copied') : t('details.copyPem')}
      </button>
    </div>
  )
}
