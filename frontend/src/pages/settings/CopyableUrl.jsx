import { useTranslation } from 'react-i18next'
import { IconBtn, RecordRow } from '../../components/atelier'
import { useNotification } from '../../contexts'
import { useClipboard } from '../../hooks/useClipboard'

// One row of the mockup's record list (inside a RecordList): the name, the URL and its description, copy on the right
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
    <RecordRow title={label}
      meta={<span className="mono">{value}</span>}
      extra={description && <span className="rl-meta">{description}</span>}
      action={<IconBtn icon="copy" label={t('common.copy')} onClick={handleCopy} />} />
  )
}
