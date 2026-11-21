import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { Warning } from '@phosphor-icons/react'
import { Button } from '../Button'
import { dashboardService } from '../../services'
import { usePermission } from '../../hooks/usePermission'

// Private keys are stored unencrypted while no master key is loaded
export function KeyEncryptionBanner() {
  const { t } = useTranslation()
  const navigate = useNavigate()
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
    <div role="alert" className="flex items-center gap-3 rounded-lg border status-warning-bg status-warning-border px-4 py-2 text-xs">
      <Warning size={16} weight="duotone" className="text-status-warning shrink-0" />
      <div className="flex-1 min-w-0">
        <span className="font-semibold text-text-primary">{t('dashboard.keyEncryptionOffTitle')}</span>{' '}
        <span className="text-text-secondary">{t('dashboard.keyEncryptionOffDesc')}</span>
      </div>
      {hasPermission('admin:system') && (
        <Button type="button" size="sm" variant="secondary" onClick={() => navigate('/settings?tab=security')}>
          {t('settings.tabs.security')}
        </Button>
      )}
    </div>
  )
}
