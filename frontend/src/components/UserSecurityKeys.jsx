/**
 * Another user's security keys, for an administrator: disable or remove a lost one.
 */
import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Fingerprint, Trash } from '@phosphor-icons/react'
import { Badge, Button, CompactSection } from './index'
import { usersService } from '../services'
import { useNotification } from '../contexts'
import { formatDate } from '../lib/utils'

export default function UserSecurityKeys({ user }) {
  const { t } = useTranslation()
  const { showSuccess, showError, showConfirm } = useNotification()
  const [keys, setKeys] = useState([])

  const load = useCallback(async () => {
    try {
      const response = await usersService.getSecurityKeys(user.id)
      setKeys(response.data || [])
    } catch (error) {
      setKeys([])
      showError(error.message || t('users.securityKeys.loadFailed'))
    }
  }, [user.id, showError, t])

  useEffect(() => { load() }, [load])

  // A 409 means the key is the last factor of required 2FA: ask once more.
  const withLastFactorConfirmation = async (action) => {
    try {
      await action({})
      return true
    } catch (error) {
      if (error.status !== 409) throw error
      const confirmed = await showConfirm(t('users.securityKeys.lastFactorConfirm', { name: user.username }), {
        title: t('users.securityKeys.title'),
        confirmText: t('common.confirm'),
        variant: 'danger'
      })
      if (!confirmed) return false
      await action({ confirmLastFactor: true })
      return true
    }
  }

  const handleRemove = async (key) => {
    const confirmed = await showConfirm(t('users.securityKeys.removeConfirm', { key: key.name, name: user.username }), {
      title: t('users.securityKeys.title'),
      confirmText: t('common.delete'),
      variant: 'danger'
    })
    if (!confirmed) return
    try {
      if (await withLastFactorConfirmation(opts => usersService.deleteSecurityKey(user.id, key.id, opts))) {
        showSuccess(t('users.securityKeys.removed'))
      }
    } catch (error) {
      showError(error.message || t('users.securityKeys.updateFailed'))
    }
    load()
  }

  const handleToggle = async (key) => {
    try {
      const enabled = !key.enabled
      if (await withLastFactorConfirmation(opts => usersService.setSecurityKeyEnabled(user.id, key.id, enabled, opts))) {
        showSuccess(enabled ? t('users.securityKeys.enabled') : t('users.securityKeys.disabled'))
      }
    } catch (error) {
      showError(error.message || t('users.securityKeys.updateFailed'))
    }
    load()
  }

  return (
    <CompactSection title={t('users.securityKeys.title')} icon={Fingerprint} iconClass="icon-bg-teal">
      <div className="p-2">
        <p className="text-xs text-text-secondary mb-2">{t('users.securityKeys.description')}</p>
        {keys.length === 0 ? (
          <p className="text-xs text-text-tertiary py-2 text-center">{t('users.securityKeys.none')}</p>
        ) : (
          <div className="space-y-1.5">
            {keys.map(key => (
              <div key={key.id} className="flex items-center justify-between p-2 bg-tertiary-50 border border-border rounded-lg">
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium text-text-primary truncate">{key.name}</p>
                  <p className="text-[10px] text-text-tertiary">
                    {t('common.created')} {formatDate(key.created_at)}
                  </p>
                </div>
                <div className="flex items-center gap-1 ml-2 flex-shrink-0">
                  <Badge variant={key.enabled ? 'success' : 'warning'} size="sm">
                    {key.enabled ? t('common.active') : t('common.disabled')}
                  </Badge>
                  <Button type="button" size="xs" variant="ghost" onClick={() => handleToggle(key)}>
                    {key.enabled ? t('common.disable') : t('common.enable')}
                  </Button>
                  <Button type="button" size="xs" variant="ghost" onClick={() => handleRemove(key)} aria-label={t('common.delete')}>
                    <Trash size={14} className="text-status-danger" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </CompactSection>
  )
}
