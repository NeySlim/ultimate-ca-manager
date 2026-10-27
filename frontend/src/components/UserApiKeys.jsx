/**
 * Another user's API keys, for an administrator: revoke a leaked or unused one.
 */
import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Key, Prohibit, Trash } from '@phosphor-icons/react'
import { Badge, Button, CompactSection } from './index'
import { usersService } from '../services'
import { useNotification } from '../contexts'
import { formatDate } from '../lib/utils'

function keyStatus(key) {
  if (!key.is_active) return ['secondary', 'common.revoked']
  if (key.is_expired) return ['secondary', 'common.expired']
  return ['success', 'common.active']
}

export default function UserApiKeys({ user }) {
  const { t } = useTranslation()
  const { showSuccess, showError, showConfirm } = useNotification()
  const [keys, setKeys] = useState([])

  const load = useCallback(async () => {
    try {
      const response = await usersService.getApiKeys(user.id)
      setKeys(response.data || [])
    } catch (error) {
      setKeys([])
      showError(error.message || t('users.apiKeys.loadFailed'))
    }
  }, [user.id, showError, t])

  useEffect(() => { load() }, [load])

  // The server revokes a usable key and deletes a revoked or expired one.
  const handleRemove = async (key) => {
    const usable = key.is_active && !key.is_expired
    const confirmed = await showConfirm(
      t(usable ? 'users.apiKeys.revokeConfirm' : 'users.apiKeys.deleteConfirm', { key: key.name, name: user.username }),
      {
        title: t('users.apiKeys.title'),
        confirmText: t(usable ? 'common.revoke' : 'common.delete'),
        variant: 'danger'
      }
    )
    if (!confirmed) return
    try {
      await usersService.deleteApiKey(user.id, key.id)
      showSuccess(t(usable ? 'users.apiKeys.revoked' : 'users.apiKeys.deleted'))
    } catch (error) {
      showError(error.message || t('users.apiKeys.updateFailed'))
    }
    load()
  }

  return (
    <CompactSection title={t('users.apiKeys.title')} icon={Key} iconClass="icon-bg-purple">
      <div className="p-2">
        <p className="text-xs text-text-secondary mb-2">{t('users.apiKeys.description')}</p>
        {keys.length === 0 ? (
          <p className="text-xs text-text-tertiary py-2 text-center">{t('users.apiKeys.none')}</p>
        ) : (
          <div className="space-y-1.5">
            {keys.map(key => {
              const [variant, label] = keyStatus(key)
              const usable = key.is_active && !key.is_expired
              return (
                <div key={key.id} className="flex items-center justify-between p-2 bg-tertiary-50 border border-border rounded-lg">
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-medium text-text-primary truncate">
                      {key.name}
                      {key.key_prefix && <span className="ml-1 font-mono text-text-tertiary">{key.key_prefix}…</span>}
                    </p>
                    <p className="text-[10px] text-text-tertiary">
                      {t('common.expires')} {key.expires_at ? formatDate(key.expires_at) : t('common.never')}
                      {' · '}
                      {t('account.apiKeyLastUsed')} {key.last_used_at ? formatDate(key.last_used_at) : t('common.never')}
                    </p>
                  </div>
                  <div className="flex items-center gap-1 ml-2 flex-shrink-0">
                    <Badge variant={variant} size="sm">{t(label)}</Badge>
                    <Button
                      type="button"
                      size="xs"
                      variant="ghost"
                      onClick={() => handleRemove(key)}
                      aria-label={t(usable ? 'common.revoke' : 'common.delete')}
                    >
                      {usable
                        ? <Prohibit size={14} className="text-status-danger" />
                        : <Trash size={14} className="text-status-danger" />}
                    </Button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </CompactSection>
  )
}
