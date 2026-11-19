/** PEM of the certificate, with a copy button. */
import { useTranslation } from 'react-i18next'
import { Copy, Check } from '@phosphor-icons/react'
import { useClipboard } from '../../../hooks/useClipboard'

export function CertificatePem({ certificate }) {
  const { t } = useTranslation()
  const { copy, isCopied } = useClipboard()
  if (!certificate.pem) return <p className="insp-foot">{t('inspector.cert.noPem')}</p>
  const copied = isCopied('pem')
  return (
    <>
      <pre className="insp-pem" tabIndex={0} aria-label={t('details.pemCertificate')}>{certificate.pem}</pre>
      <button type="button" className="insp-btn" onClick={() => copy(certificate.pem, 'pem')}>
        {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
        {copied ? t('common.copied') : t('details.copyPem')}
      </button>
    </>
  )
}
