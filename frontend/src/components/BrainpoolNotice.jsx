import { useTranslation } from 'react-i18next'
import { Warning } from '@phosphor-icons/react'
import { isBrainpool, isUntestedOn } from '../lib/keyAlgorithms'
import { Icon } from './atelier/Icon'

// Inside a form of the mockup the note is the issue form's: a small line under its field (extensions.css .brainpool)
const AtelierNote = ({ children }) => <small className="brainpool" role="note"><Icon name="warning" /><span>{children}</span></small>

/** Compatibility warning shown while a Brainpool key is selected (`label` is a registry label). */
export function BrainpoolNotice({ label, atelier = false }) {
  const { t } = useTranslation()
  if (!isBrainpool(label)) return null
  if (atelier) return <AtelierNote>{t('common.keyGroups.brainpoolWarning')}</AtelierNote>
  return (
    <p className="flex items-start gap-1.5 text-xs text-text-secondary" role="note">
      <Warning size={14} className="mt-0.5 shrink-0 text-accent-warning" />
      <span>{t('common.keyGroups.brainpoolWarning')}</span>
    </p>
  )
}

/** Shown while an ML-DSA key is chosen on Google Cloud KMS, mapped but not yet tested there. */
export function UntestedKeyNotice({ label, provider, atelier = false }) {
  const { t } = useTranslation()
  if (!isUntestedOn(label, provider)) return null
  if (atelier) return <AtelierNote>{t('hsm.mldsaUntestedGoogleKms')}</AtelierNote>
  return (
    <p className="flex items-start gap-1.5 text-xs text-text-secondary" role="note">
      <Warning size={14} className="mt-0.5 shrink-0 text-accent-warning" />
      <span>{t('hsm.mldsaUntestedGoogleKms')}</span>
    </p>
  )
}

export default BrainpoolNotice
