/**
 * Another user's security keys, for an administrator, in the mockup's record rows: disable or
 * remove a lost one.
 */
import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Btn, Pill, RecordList, RecordRow, Section } from './atelier'
import { usersService } from '../services'
import { useNotification } from '../contexts'
import { dateOf } from '../pages/admin/adminDates'

export default function UserSecurityKeys({ user }) {
  const { t, i18n } = useTranslation()
  const locale = i18n?.language || 'en'
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
        title: t('users.securityKeys.title'), confirmText: t('common.confirm'), variant: 'danger',
      })
      if (!confirmed) return false
      await action({ confirmLastFactor: true })
      return true
    }
  }

  const handleRemove = async (key) => {
    const confirmed = await showConfirm(t('users.securityKeys.removeConfirm', { key: key.name, name: user.username }), {
      title: t('users.securityKeys.title'), confirmText: t('common.delete'), variant: 'danger',
    })
    if (!confirmed) return
    try {
      if (await withLastFactorConfirmation((opts) => usersService.deleteSecurityKey(user.id, key.id, opts))) {
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
      if (await withLastFactorConfirmation((opts) => usersService.setSecurityKeyEnabled(user.id, key.id, enabled, opts))) {
        showSuccess(enabled ? t('users.securityKeys.enabled') : t('users.securityKeys.disabled'))
      }
    } catch (error) {
      showError(error.message || t('users.securityKeys.updateFailed'))
    }
    load()
  }

  return (
    <Section title={t('users.securityKeys.title')}>
      <p className="small muted perm-intro">{t('users.securityKeys.description')}</p>
      <RecordList empty={t('users.securityKeys.none')}>
        {keys.map((key) => (
          <RecordRow key={key.id} title={key.name} meta={`${t('common.created')} ${dateOf(key.created_at, locale)}`}
            badge={<Pill label={key.enabled ? t('common.active') : t('common.disabled')} tone={key.enabled ? 'good' : 'muted'} />}
            action={<>
              <Btn write onClick={() => handleToggle(key)}>{key.enabled ? t('common.disable') : t('common.enable')}</Btn>
              <Btn icon="block" write aria-label={t('common.delete')} onClick={() => handleRemove(key)}>{t('common.delete')}</Btn>
            </>} />
        ))}
      </RecordList>
    </Section>
  )
}
