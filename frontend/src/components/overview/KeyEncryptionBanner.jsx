import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Btn, Icon } from '../atelier'
import { dashboardService } from '../../services'
import { usePermission } from '../../hooks/usePermission'

/** Private keys are stored unencrypted while no master key is loaded: the mockup's state banner says so. */
export function KeyEncryptionBanner() {
  const { t } = useTranslation()
  const { hasPermission } = usePermission()
  const [off, setOff] = useState(false)

  useEffect(() => {
    let live = true
    dashboardService.getSystemStatus()
      .then((res) => { if (live) setOff(res?.data?.key_encryption?.status === 'warning') })
      .catch(() => {})
    return () => { live = false }
  }, [])

  if (!off) return null
  return (
    <div role="alert" className="state-banner tone-warn" id="key-encryption-banner">
      <Icon name="warning" />
      <p><strong>{t('dashboard.keyEncryptionOffTitle')}</strong> {t('dashboard.keyEncryptionOffDesc')}</p>
      {hasPermission('admin:system') && (
        <Btn icon="lock" to="/settings?tab=security">{t('settings.tabs.security')}</Btn>
      )}
    </div>
  )
}
