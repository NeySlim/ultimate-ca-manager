/**
 * Where an SSO sign-in test lands once the IdP answered: it says the test is over and never
 * shows the application, whoever signed in at the IdP. The result is read on the provider screen.
 */
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { CheckCircle, Warning } from '@phosphor-icons/react'
import { Card, Logo } from '../components'
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

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg-primary p-4">
      <Card className="w-full max-w-md p-6 space-y-4 text-center">
        <Logo />
        <div role="status" className="space-y-2">
          {done
            ? <CheckCircle size={32} className="mx-auto text-status-success" />
            : <Warning size={32} className="mx-auto text-status-warning" />}
          <h1 className="text-lg font-semibold text-text-primary">{t('sso.signInTestCompleteTitle')}</h1>
          <p className="text-sm text-text-secondary">{t(RESULTS[result])}</p>
          {stillOpen && <p className="text-sm text-text-secondary">{t('sso.signInTestCompleteClose')}</p>}
        </div>
        <Link to="/settings?tab=sso" className="text-sm text-accent-primary hover:underline">
          {t('sso.signInTestCompleteBack')}
        </Link>
      </Card>
    </div>
  )
}
