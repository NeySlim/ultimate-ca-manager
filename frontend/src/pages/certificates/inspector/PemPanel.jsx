/** The PEM panel (the product's, after the mockup's four): the text in the mockup's code preview, and Copier. */
import { useTranslation } from 'react-i18next'
import { Icon } from '../../../components/atelier'
import { useClipboard } from '../../../hooks/useClipboard'

export function PemPanel({ cert }) {
  const { t } = useTranslation()
  const { copy, isCopied } = useClipboard()
  if (!cert.pem) return <p className="muted small">{t('inspector.cert.noPem')}</p>
  const copied = isCopied('pem')
  return (
    <div>
      <pre className="code-preview" data-testid="certificate-pem">{cert.pem}</pre>
      <button type="button" className="btn" onClick={() => copy(cert.pem, 'pem')}>
        <Icon name={copied ? 'check' : 'copy'} />{copied ? t('common.copied') : t('details.copyPem')}
      </button>
    </div>
  )
}
