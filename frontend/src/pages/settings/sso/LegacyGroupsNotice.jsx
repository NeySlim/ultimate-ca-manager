import { useTranslation } from 'react-i18next'
import { Warning } from '@phosphor-icons/react'
import { hiddenLegacyGroupRows } from './groupMapping'

/** Warns, without blocking, that legacy `groups -> attribute` rows are no longer read. */
export default function LegacyGroupsNotice({ mapping }) {
  const { t } = useTranslation()
  const hidden = hiddenLegacyGroupRows(mapping)
  if (!hidden.length) return null
  return (
    <div role="status" className="mt-2 p-3 rounded-lg bg-accent-warning-op10 border border-accent-warning-op30 text-xs status-warning-text flex gap-2">
      <Warning size={16} className="shrink-0 mt-0.5" />
      <span>{t('sso.legacyGroupsHidden', { attributes: hidden.join(', ') })}</span>
    </div>
  )
}
