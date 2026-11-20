import { useTranslation } from 'react-i18next'
import { Copy } from '@phosphor-icons/react'
import { Button } from '../../components'
import { useNotification } from '../../contexts'
import { useClipboard } from '../../hooks/useClipboard'

// One row of the mockup's record list: the name, the URL and its description under it, copy on the right
export default function CopyableUrl({ label, value, description }) {
  const { showInfo } = useNotification()
  const { t } = useTranslation()
  const { copy } = useClipboard()
  // Only confirm a copy that actually reached the clipboard: over plain HTTP
  // the async clipboard API is not there at all.
  const handleCopy = async () => {
    if (await copy(value)) showInfo(t('common.copiedToClipboard'))
  }
  return (
    <div className="sf-copy">
      <div className="sf-record-main">
        <strong>{label}</strong>
        <span className="sf-copy-value">{value}</span>
        {description && <span className="sf-record-meta">{description}</span>}
      </div>
      <div className="sf-record-actions">
        <Button variant="secondary" onClick={handleCopy} type="button" title={t('common.copy')} aria-label={t('common.copy')}>
          <Copy size={16} />
        </Button>
      </div>
    </div>
  )
}
