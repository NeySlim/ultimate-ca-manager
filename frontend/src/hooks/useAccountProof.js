import { useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useNotification } from '../contexts'
import { accountService } from '../services'

/**
 * Asks the signed-in user to prove the account is theirs before a change that adds a
 * sign-in credential or moves its e-mail: the password, or the authenticator code of an
 * account without one. Resolves to the body fields to send, or null when cancelled.
 */
export function useAccountProof() {
  const { t } = useTranslation()
  const { showPrompt } = useNotification()
  return useCallback(async () => {
    let profile = {}
    try {
      profile = (await accountService.getProfile())?.data || {}
    } catch { /* the server asks again and says why */ }
    if (profile.has_local_password !== false) {
      const password = await showPrompt(t('account.confirmWithPassword'), {
        title: t('account.confirmItIsYou'), type: 'password', confirmText: t('common.confirm'),
      })
      return password ? { password } : null
    }
    if (profile.two_factor_enabled) {
      const code = await showPrompt(t('account.confirmWithCode'), {
        title: t('account.confirmItIsYou'), placeholder: '123456', confirmText: t('common.confirm'),
      })
      return code ? { code } : null
    }
    return {}  // neither: the server refuses with its reason
  }, [t, showPrompt])
}
