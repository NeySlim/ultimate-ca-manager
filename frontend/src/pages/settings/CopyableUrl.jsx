import { useTranslation } from 'react-i18next'
import { Copy } from '@phosphor-icons/react'
import { Button } from '../../components'
import { useNotification } from '../../contexts'

export default function CopyableUrl({ label, value, description }) {
  const { showInfo } = useNotification()
  const { t } = useTranslation()
  const copy = () => {
    navigator.clipboard.writeText(value)
    showInfo(t('common.copiedToClipboard'))
  }
  return (
    <div className="p-3 bg-bg-tertiary rounded-lg">
      <p className="text-xs text-text-secondary mb-1">{label}</p>
      {description && <p className="text-xs text-text-muted mb-1.5">{description}</p>}
      <div className="flex items-center gap-2">
        <code className="text-sm font-mono text-text-primary flex-1 break-all select-all">{value}</code>
        <Button size="sm" variant="ghost" onClick={copy} type="button" title={t('common.copy')} aria-label={t('common.copy')}>
          <Copy size={14} />
        </Button>
      </div>
    </div>
  )
}
