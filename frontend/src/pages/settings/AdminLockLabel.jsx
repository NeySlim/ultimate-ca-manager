import { useTranslation } from 'react-i18next'
import { Lock } from '@phosphor-icons/react'
import { Icon } from '../../components/atelier/Icon'

// Field label with a padlock when the setting needs admin:settings. Always an
// element, so the label never merges with the field's helper text. `mockup`
// draws it in the Atelier vocabulary (the mockup's lock icon, `.lock-mark`).
export default function AdminLockLabel({ text, locked, mockup = false }) {
  const { t } = useTranslation()
  if (mockup) {
    return (
      <>
        {text}
        {locked && (
          <span className="lock-mark" role="img" aria-label={t('settings.adminFieldsLocked')} title={t('settings.adminFieldsLocked')} data-testid="admin-lock">
            <Icon name="lock" />
          </span>
        )}
      </>
    )
  }
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
