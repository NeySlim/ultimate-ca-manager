/**
 * Where an SSO sign-in test lands once the IdP answered: it says the test is over and never
 * shows the application, whoever signed in at the IdP. The result is read on the provider screen.
 */
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { CheckCircle, Warning } from '@phosphor-icons/react'
import { AuthFrame } from '../components/auth/AuthFrame'
import { openChannel } from './settings/sso/signInTestChannel'

export const CLOSE_DELAY_MS = 1500

const RESULTS = {
  done: 'sso.signInTestCompleteDone',
  used: 'sso.signInTestCompleteUsed',
  expired: 'sso.signInTestCompleteExpired',
  other_browser: 'sso.signInTestCompleteOtherBrowser',
}

export default function SsoTestCompletePage() {
  const { t } = useTranslation()
  const [params] = useSearchParams()
  const result = RESULTS[params.get('result')] ? params.get('result') : 'expired'
  const done = result === 'done'
  const [stillOpen, setStillOpen] = useState(false)

  useEffect(() => {
    // The provider screen learns the end on the same-origin channel: this window has no opener.
    const channel = openChannel()
    channel?.postMessage({ type: 'complete', result })
    channel?.close()
  }, [result])

  useEffect(() => {
    if (!done) return undefined
    // A browser may refuse to close a window that went through the IdP: then ask the user.
    const timer = setTimeout(() => {
      window.close()
      setTimeout(() => { if (!window.closed) setStillOpen(true) }, 300)
    }, CLOSE_DELAY_MS)
    return () => clearTimeout(timer)
  }, [done])

  // A window of its own: no theme, language or footer, the sign-in frame only
  return (
    <AuthFrame title={t('sso.signInTestCompleteTitle')} tools={false} footer={false}>
      <div role="status" className={`auth-result ${done ? 'is-good' : 'is-warn'}`}>
        {done ? <CheckCircle size={20} aria-hidden="true" /> : <Warning size={20} aria-hidden="true" />}
        <span className="auth-result-text">
          <span>{t(RESULTS[result])}</span>
          {stillOpen && <span>{t('sso.signInTestCompleteClose')}</span>}
        </span>
      </div>
      <Link to="/settings?tab=sso" className="auth-link">{t('sso.signInTestCompleteBack')}</Link>
    </AuthFrame>
  )
}
