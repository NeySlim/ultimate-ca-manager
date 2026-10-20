import { useTranslation } from 'react-i18next'
import { Lock } from '@phosphor-icons/react'

// Field label with a padlock when the setting needs admin:settings. Always an
// element, so the label never merges with the field's helper text.
export default function AdminLockLabel({ text, locked }) {
  const { t } = useTranslation()
  return (
    <span className="inline-flex items-center gap-1">
      {text}
      {locked && (
        <span
          role="img"
          aria-label={t('settings.adminFieldsLocked')}
          title={t('settings.adminFieldsLocked')}
          data-testid="admin-lock"
          className="inline-flex text-text-tertiary"
        >
          <Lock size={12} weight="fill" aria-hidden="true" />
        </span>
      )}
    </span>
  )
}
