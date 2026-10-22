import { useTranslation } from 'react-i18next'
import { Warning } from '@phosphor-icons/react'
import { isBrainpool } from '../lib/keyAlgorithms'

/** Compatibility warning shown while a Brainpool key is selected (`label` is a registry label). */
export function BrainpoolNotice({ label }) {
  const { t } = useTranslation()
  if (!isBrainpool(label)) return null
  return (
    <p className="flex items-start gap-1.5 text-xs text-text-secondary" role="note">
      <Warning size={14} className="mt-0.5 shrink-0 text-accent-warning" />
      <span>{t('common.keyGroups.brainpoolWarning')}</span>
    </p>
  )
}

export default BrainpoolNotice
