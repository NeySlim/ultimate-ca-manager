/**
 * Another user's API keys, for an administrator, as the mockup's userKeysPanel() lists them:
 * the name, then prefix, scope, creation and last use; revoke a leaked or unused one.
 */
import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Btn, Pill, RecordList, RecordRow } from './atelier'
import { usersService } from '../services'
import { useNotification } from '../contexts'
import { apiKeyScopeLabel } from '../lib/apiKeyScopes'
import { dateOf, dateTimeOf } from '../pages/admin/adminDates'

function keyStatus(key) {
  if (!key.is_active) return ['muted', 'common.revoked']
  if (key.is_expired) return ['muted', 'common.expired']
  return ['good', 'common.active']
}

export default function UserApiKeys({ user, canRevoke = true }) {
  const { t, i18n } = useTranslation()
  const locale = i18n?.language || 'en'
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
      { title: t('users.apiKeys.title'), confirmText: t(usable ? 'common.revoke' : 'common.delete'), variant: 'danger' },
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
    <>
      <p className="small muted perm-intro">{t('users.apiKeys.description')}</p>
      <RecordList empty={t('users.apiKeys.none')}>
        {keys.map((key) => {
          const [tone, label] = keyStatus(key)
          const usable = key.is_active && !key.is_expired
          return (
            <RecordRow key={key.id} title={key.name}
              meta={<>
                {key.key_prefix && <><span className="mono">{key.key_prefix}…</span>{' · '}</>}
                {t('users.apiKeys.meta', {
                  scope: apiKeyScopeLabel(t, key.permissions), created: dateOf(key.created_at, locale) || '—',
                  used: key.last_used_at ? dateTimeOf(key.last_used_at, locale) : t('common.never'),
                  expires: key.expires_at ? dateOf(key.expires_at, locale) : t('common.never'),
                })}
              </>}
              badge={<Pill label={t(label)} tone={tone} />}
              action={canRevoke && (
                <Btn icon="block" write aria-label={t(usable ? 'common.revoke' : 'common.delete')} onClick={() => handleRemove(key)}>
                  {t(usable ? 'common.revoke' : 'common.delete')}
                </Btn>
              )} />
          )
        })}
      </RecordList>
    </>
  )
}
